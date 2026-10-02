from __future__ import annotations
import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any

from websockets.asyncio.server import serve, ServerConnection

from .auth import verify_token, get_user
from .config import settings
from . import chats

log = logging.getLogger("ws")


class Client:
    def __init__(self, ws: ServerConnection):
        self.ws = ws
        self.user_id: int | None = None
        self.username: str | None = None
        self.last_pong: float = time.time()


class Hub:
    def __init__(self):
        # sock_id -> Client
        self.clients: dict[int, Client] = {}
        # user_id -> set[sock_id]
        self.user_sockets: dict[int, set[int]] = defaultdict(set)
        # user_id -> peer_user_id  (активные звонки)
        self.active_calls: dict[int, int] = {}

    # ---------- Управление соединениями ----------

    def add(self, ws: ServerConnection) -> Client:
        c = Client(ws)
        self.clients[id(ws)] = c
        return c

    def drop(self, ws: ServerConnection) -> None:
        sid = id(ws)
        c = self.clients.pop(sid, None)
        if not c:
            return
        if c.user_id is not None:
            self.user_sockets[c.user_id].discard(sid)
            if not self.user_sockets[c.user_id]:
                del self.user_sockets[c.user_id]
                # если пользователь отключился — завершаем его звонок
                peer = self.active_calls.pop(c.user_id, None)
                if peer is not None:
                    self.active_calls.pop(peer, None)
                    asyncio.create_task(self.send_to_user(peer, {
                        "type": "call_ended",
                        "fromUserId": c.user_id,
                        "fromName": c.username,
                    }))
            asyncio.create_task(self.broadcast_online())

    # ---------- Отправка ----------

    async def send(self, ws: ServerConnection, payload: dict) -> None:
        try:
            await ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    async def send_to_user(self, user_id: int, payload: dict) -> None:
        for sid in list(self.user_sockets.get(user_id, ())):
            c = self.clients.get(sid)
            if c:
                await self.send(c.ws, payload)

    async def broadcast_to_chat(self, chat_id: int, payload: dict,
                                except_user_id: int | None = None) -> None:
        for uid in chats.chat_member_ids(chat_id):
            if except_user_id is not None and uid == except_user_id:
                continue
            await self.send_to_user(uid, payload)

    async def broadcast_online(self) -> None:
        online = []
        for uid, socks in self.user_sockets.items():
            for sid in socks:
                c = self.clients.get(sid)
                if c and c.username:
                    online.append({"id": uid, "username": c.username})
                    break
        payload = {"type": "online", "users": online}
        for sid in list(self.clients.keys()):
            c = self.clients.get(sid)
            if c:
                await self.send(c.ws, payload)

    # ---------- Ping ----------

    async def ping_loop(self) -> None:
        while True:
            await asyncio.sleep(settings.PING_INTERVAL)
            now = time.time()
            for sid, c in list(self.clients.items()):
                if c.user_id is None:
                    continue
                try:
                    pong_waiter = await c.ws.ping()
                    # ждём pong не дольше 5 секунд
                    await asyncio.wait_for(pong_waiter, timeout=5)
                    c.last_pong = now
                except Exception:
                    log.info("Клиент #%s не ответил на ping — отключаю", sid)
                    await c.ws.close()


hub = Hub()


# ==================== Обработка сообщений ====================

async def handler(ws: ServerConnection) -> None:
    client = hub.add(ws)
    await hub.send(ws, {"type": "hello", "text": "Авторизуйтесь"})

    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue

            # сбрасываем pong-таймер при любой активности
            client.last_pong = time.time()

            try:
                await handle_message(client, msg)
            except chats.ChatError as e:
                await hub.send(ws, {"type": "error", "text": str(e)})
            except Exception as e:
                log.exception("Ошибка обработки: %s", e)
                await hub.send(ws, {"type": "error", "text": "Внутренняя ошибка"})
    finally:
        hub.drop(ws)


async def handle_message(c: Client, msg: dict) -> None:
    t = msg.get("type", "")

    # ---- Первое сообщение — auth ----
    if t == "auth":
        uid = verify_token(msg.get("token", ""))
        if not uid:
            await hub.send(c.ws, {"type": "auth_failed", "text": "Неверный токен"})
            return
        user = get_user(uid)
        if not user:
            await hub.send(c.ws, {"type": "auth_failed", "text": "Пользователь не найден"})
            return
        c.user_id = user["id"]
        c.username = user["username"]
        hub.user_sockets[user["id"]].add(id(c.ws))
        await hub.send(c.ws, {
            "type": "auth_ok",
            "userId": user["id"],
            "username": user["username"],
            "chats": chats.list_chats(user["id"]),
        })
        await hub.broadcast_online()
        return

    # ---- Всё остальное требует auth ----
    if c.user_id is None:
        await hub.send(c.ws, {"type": "error", "text": "Сначала авторизуйтесь"})
        return

    uid = c.user_id

    # ================= ЧАТЫ =================
    if t == "create_group":
        cid = chats.create_group(uid, msg.get("name", ""))
        await hub.send(c.ws, {"type": "chat_created", "chat": chats.chat_summary(cid, uid)})
        await hub.broadcast_online()

    elif t == "create_channel":
        cid = chats.create_channel(uid, msg.get("name", ""))
        await hub.send(c.ws, {"type": "chat_created", "chat": chats.chat_summary(cid, uid)})
        await hub.broadcast_online()

    elif t == "create_dm":
        to_uid = int(msg.get("userId", 0))
        cid = chats.get_or_create_dm(uid, to_uid)
        await hub.send(c.ws, {"type": "chat_created", "chat": chats.chat_summary(cid, uid)})
        await hub.send_to_user(to_uid, {
            "type": "chat_created", "chat": chats.chat_summary(cid, to_uid),
        })

    elif t == "join_chat":
        cid = int(msg.get("chatId", 0))
        if chats.chat_info(cid):
            chats.add_member(cid, uid)
            await hub.send(c.ws, {"type": "chat_created",
                                  "chat": chats.chat_summary(cid, uid)})

    elif t == "list_chats":
        await hub.send(c.ws, {"type": "chats", "chats": chats.list_chats(uid)})

    # ================= СООБЩЕНИЯ =================
    elif t == "history":
        cid = int(msg.get("chatId", 0))
        if not chats.is_member(cid, uid):
            raise chats.ChatError("Нет доступа")
        limit = int(msg.get("limit", 50))
        before = int(msg.get("beforeId", 0))
        await hub.send(c.ws, {
            "type": "history", "chatId": cid,
            "messages": chats.messages_for_chat(cid, limit, before),
        })

    elif t == "message":
        cid = int(msg.get("chatId", 0))
        if not chats.is_member(cid, uid):
            raise chats.ChatError("Нет доступа")
        cinfo = chats.chat_info(cid)
        if not cinfo:
            raise chats.ChatError("Чат не найден")
        if cinfo["type"] == "channel" and not chats.is_owner(cid, uid):
            raise chats.ChatError("В канале может писать только владелец")

        saved = chats.save_message(cid, uid, msg.get("text", ""))
        payload = {
            "type": "message", "chatId": cid,
            "id": saved["id"], "userId": uid, "username": c.username,
            "text": saved["text"], "time": saved["time"],
        }
        await hub.broadcast_to_chat(cid, payload)

    elif t == "delete_message":
        mid = int(msg.get("messageId", 0))
        cid = int(msg.get("chatId", 0))
        if not chats.is_member(cid, uid):
            raise chats.ChatError("Нет доступа")
        if chats.delete_message(mid, uid):
            await hub.broadcast_to_chat(cid, {
                "type": "message_deleted", "chatId": cid, "messageId": mid,
            })
            await hub.broadcast_to_chat(cid, {
                "type": "reactions", "chatId": cid, "messageId": mid,
                "reactions": {},
            })

    # ================= РЕАКЦИИ =================
    elif t == "react":
        mid = int(msg.get("messageId", 0))
        emoji = msg.get("emoji", "")
        cid = chats.message_chat_id(mid)
        if cid is None or not chats.is_member(cid, uid):
            raise chats.ChatError("Нет доступа")
        reactions = chats.toggle_reaction(mid, uid, emoji)
        await hub.broadcast_to_chat(cid, {
            "type": "reactions", "chatId": cid,
            "messageId": mid, "reactions": reactions or {},
        })

    # ================= УЧАСТНИКИ =================
    elif t == "members":
        cid = int(msg.get("chatId", 0))
        if not chats.is_member(cid, uid):
            raise chats.ChatError("Нет доступа")
        info = chats.chat_info(cid) or {}
        await hub.send(c.ws, {
            "type": "members", "chatId": cid,
            "members": chats.chat_members(cid),
            "ownerId": info.get("owner_id", 0),
        })

    elif t == "kick_user":
        cid = int(msg.get("chatId", 0))
        target = int(msg.get("userId", 0))
        if not chats.remove_member(cid, target, uid):
            raise chats.ChatError("Нельзя исключить этого пользователя")
        await hub.send_to_user(target, {
            "type": "kicked", "chatId": cid, "text": "Вас исключили из чата",
        })
        await hub.broadcast_to_chat(cid, {
            "type": "member_left", "chatId": cid, "userId": target,
        })

    elif t == "add_user":
        cid = int(msg.get("chatId", 0))
        target = int(msg.get("userId", 0))
        if not chats.is_member(cid, uid):
            raise chats.ChatError("Нет доступа")
        chats.add_member(cid, target)
        await hub.send_to_user(target, {
            "type": "chat_created", "chat": chats.chat_summary(cid, target),
        })
        await hub.broadcast_to_chat(cid, {
            "type": "member_joined", "chatId": cid, "userId": target,
        })

    # ================= ПОИСК =================
    elif t == "search_users":
        users = chats.search_users(msg.get("q", ""), uid)
        await hub.send(c.ws, {"type": "search_result", "users": users})

    elif t == "search_messages":
        cid = int(msg.get("chatId", 0))
        if not chats.is_member(cid, uid):
            raise chats.ChatError("Нет доступа")
        msgs = chats.search_messages(cid, msg.get("q", ""))
        await hub.send(c.ws, {
            "type": "search_messages_result", "chatId": cid, "messages": msgs,
        })

    # ================= TYPING =================
    elif t == "typing":
        cid = int(msg.get("chatId", 0))
        if not chats.is_member(cid, uid):
            return
        await hub.broadcast_to_chat(cid, {
            "type": "typing", "chatId": cid,
            "userId": uid, "username": c.username,
            "state": bool(msg.get("state", False)),
        }, except_user_id=uid)

    # ================= ЗВОНКИ =================
    elif t == "call_invite":
        to_uid = int(msg.get("toUserId", 0))
        video = bool(msg.get("video", True))
        if to_uid == uid:
            raise chats.ChatError("Нельзя звонить себе")
        if hub.active_calls.get(to_uid) or hub.active_calls.get(uid):
            raise chats.ChatError("Абонент уже в звонке")
        if not hub.user_sockets.get(to_uid):
            raise chats.ChatError("Абонент не в сети")

        hub.active_calls[uid] = to_uid
        hub.active_calls[to_uid] = uid
        await hub.send_to_user(to_uid, {
            "type": "call_incoming", "fromUserId": uid,
            "fromName": c.username, "video": video,
        })
        await hub.send(c.ws, {
            "type": "call_ringing", "toUserId": to_uid, "video": video,
        })

    elif t == "call_accept":
        to_uid = int(msg.get("toUserId", 0))
        if hub.active_calls.get(uid) != to_uid:
            raise chats.ChatError("Нет активного звонка")
        await hub.send_to_user(to_uid, {
            "type": "call_accepted", "fromUserId": uid, "fromName": c.username,
        })

    elif t == "call_reject":
        to_uid = int(msg.get("toUserId", 0))
        await hub.send_to_user(to_uid, {
            "type": "call_rejected", "fromUserId": uid, "fromName": c.username,
        })
        _end_call(uid)

    elif t == "call_end":
        peer = hub.active_calls.get(uid)
        if peer is not None:
            await hub.send_to_user(peer, {
                "type": "call_ended", "fromUserId": uid, "fromName": c.username,
            })
            _end_call(uid)

    # ================= WEBRTC-СИГНАЛИНГ =================
    elif t in ("webrtc_offer", "webrtc_answer", "webrtc_ice"):
        to_uid = int(msg.get("toUserId", 0))
        await hub.send_to_user(to_uid, {
            "type": t, "fromUserId": uid, "fromName": c.username,
            "data": msg.get("data"),
        })

    else:
        log.debug("Неизвестный тип сообщения: %s", t)


def _end_call(user_id: int) -> None:
    peer = hub.active_calls.pop(user_id, None)
    if peer is not None:
        hub.active_calls.pop(peer, None)


# ==================== Точка входа WebSocket ====================

async def start_ws_server(host: str, port: int):
    async with serve(handler, host, port, max_size=2**20) as server:
        log.info("WebSocket запущен на ws://%s:%s", host, port)
        # запускаем ping/pong в фоне
        asyncio.create_task(hub.ping_loop())
        await asyncio.Future()  # ждём вечно