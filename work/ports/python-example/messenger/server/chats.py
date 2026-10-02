from __future__ import annotations
from datetime import datetime
from typing import Optional, Iterable

from sqlalchemy import select, delete, update, or_, func, and_

from .config import settings
from .db import (
    db_session, User, Chat, ChatMember, Message, Reaction, DmPair,
)


class ChatError(Exception):
    pass


# ==================== Создание чатов ====================

def _create_named_chat(owner_id: int, name: str, chat_type: str) -> int:
    name = (name or "").strip()
    if not (2 <= len(name) <= 64):
        raise ChatError("Название: 2–64 символа")

    with db_session() as s:
        chat = Chat(type=chat_type, name=name, owner_id=owner_id)
        s.add(chat)
        s.flush()

        s.add(ChatMember(chat_id=chat.id, user_id=owner_id, role="owner"))
        s.commit()
        return chat.id


def create_group(owner_id: int, name: str) -> int:
    return _create_named_chat(owner_id, name, "group")


def create_channel(owner_id: int, name: str) -> int:
    return _create_named_chat(owner_id, name, "channel")


def get_or_create_dm(user_a: int, user_b: int) -> int:
    if user_a == user_b:
        raise ChatError("Нельзя DM с самим собой")
    a, b = sorted((user_a, user_b))

    with db_session() as s:
        pair = s.execute(
            select(DmPair).where(DmPair.user_a == a, DmPair.user_b == b)
        ).scalar_one_or_none()
        if pair:
            return pair.chat_id

        chat = Chat(type="dm", name=None, owner_id=None)
        s.add(chat)
        s.flush()

        s.add(ChatMember(chat_id=chat.id, user_id=a, role="member"))
        s.add(ChatMember(chat_id=chat.id, user_id=b, role="member"))
        s.add(DmPair(chat_id=chat.id, user_a=a, user_b=b))
        s.commit()
        return chat.id


# ==================== Чтение ====================

def list_chats(user_id: int) -> list[dict]:
    with db_session() as s:
        rows = s.execute(
            select(Chat, ChatMember).join(ChatMember, ChatMember.chat_id == Chat.id)
            .where(ChatMember.user_id == user_id)
            .order_by(Chat.id.desc())
        ).all()

        result = []
        for chat, member in rows:
            name = chat.name
            partner_id = None
            if chat.type == "dm":
                partner = s.execute(
                    select(User).join(ChatMember, ChatMember.user_id == User.id)
                    .where(ChatMember.chat_id == chat.id, User.id != user_id)
                    .limit(1)
                ).scalar_one_or_none()
                if partner:
                    name = partner.username
                    partner_id = partner.id

            cnt = s.execute(
                select(func.count(Message.id)).where(
                    Message.chat_id == chat.id, Message.deleted == False
                )
            ).scalar_one()

            result.append({
                "id": chat.id,
                "type": chat.type,
                "name": name,
                "owner_id": chat.owner_id,
                "myRole": member.role,
                "partner_id": partner_id,
                "messages_count": int(cnt),
            })
        return result


def chat_summary(chat_id: int, for_user_id: int) -> dict:
    with db_session() as s:
        row = s.execute(
            select(Chat, ChatMember).join(ChatMember, ChatMember.chat_id == Chat.id)
            .where(Chat.id == chat_id, ChatMember.user_id == for_user_id)
        ).first()
        if not row:
            raise ChatError("Чат недоступен")
        chat, member = row

        name = chat.name
        partner_id = None
        if chat.type == "dm":
            partner = s.execute(
                select(User).join(ChatMember, ChatMember.user_id == User.id)
                .where(ChatMember.chat_id == chat.id, User.id != for_user_id).limit(1)
            ).scalar_one_or_none()
            if partner:
                name = partner.username
                partner_id = partner.id

        return {
            "id": chat.id, "type": chat.type, "name": name,
            "owner_id": chat.owner_id, "myRole": member.role,
            "partner_id": partner_id,
        }


def is_member(chat_id: int, user_id: int) -> bool:
    with db_session() as s:
        return s.execute(
            select(ChatMember.id).where(
                ChatMember.chat_id == chat_id, ChatMember.user_id == user_id
            )
        ).first() is not None


def is_owner(chat_id: int, user_id: int) -> bool:
    with db_session() as s:
        chat = s.get(Chat, chat_id)
        return bool(chat and chat.owner_id == user_id)


def chat_info(chat_id: int) -> Optional[dict]:
    with db_session() as s:
        c = s.get(Chat, chat_id)
        if not c:
            return None
        return {"id": c.id, "type": c.type, "name": c.name, "owner_id": c.owner_id}


def chat_member_ids(chat_id: int) -> list[int]:
    with db_session() as s:
        rows = s.execute(
            select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)
        ).all()
        return [r[0] for r in rows]


def chat_members(chat_id: int) -> list[dict]:
    with db_session() as s:
        rows = s.execute(
            select(User.id, User.username, ChatMember.role)
            .join(ChatMember, ChatMember.user_id == User.id)
            .where(ChatMember.chat_id == chat_id)
            .order_by(ChatMember.role.desc(), User.username)
        ).all()
        return [{"id": r[0], "username": r[1], "role": r[2]} for r in rows]


# ==================== Сообщения ====================

def save_message(chat_id: int, user_id: int, text: str) -> dict:
    text = (text or "").strip()
    if not text or len(text) > 4000:
        raise ChatError("Пустое или слишком длинное сообщение")

    safe = (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

    time_str = datetime.now().strftime("%H:%M:%S")

    with db_session() as s:
        m = Message(chat_id=chat_id, user_id=user_id, text=safe, time=time_str)
        s.add(m)
        s.flush()
        result = {"id": m.id, "text": safe, "time": time_str}
        s.commit()
        return result


def delete_message(message_id: int, by_user_id: int) -> bool:
    with db_session() as s:
        m = s.get(Message, message_id)
        if not m:
            return False
        chat = s.get(Chat, m.chat_id)
        if m.user_id != by_user_id and (not chat or chat.owner_id != by_user_id):
            return False

        m.deleted = True
        s.execute(delete(Reaction).where(Reaction.message_id == message_id))
        s.commit()
        return True


def messages_for_chat(chat_id: int, limit: int = 50, before_id: int = 0) -> list[dict]:
    limit = max(1, min(200, limit))

    with db_session() as s:
        q = (
            select(Message, User.username)
            .join(User, User.id == Message.user_id)
            .where(Message.chat_id == chat_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        if before_id:
            q = q.where(Message.id < before_id)
        rows = s.execute(q).all()

        rows = list(reversed(rows))
        ids = [m.id for m, _ in rows]
        reactions = _reactions_for_messages(s, ids)

        return [{
            "id": m.id,
            "userId": m.user_id,
            "username": uname,
            "text": None if m.deleted else m.text,
            "time": m.time,
            "deleted": bool(m.deleted),
            "reactions": reactions.get(m.id, {}),
        } for m, uname in rows]


# ==================== Реакции ====================

def _reactions_for_messages(s, message_ids: list[int]) -> dict[int, dict[str, list[int]]]:
    if not message_ids:
        return {}
    rows = s.execute(
        select(Reaction.message_id, Reaction.emoji, Reaction.user_id)
        .where(Reaction.message_id.in_(message_ids))
        .order_by(Reaction.created_at)
    ).all()
    out: dict[int, dict[str, list[int]]] = {}
    for mid, emoji, uid in rows:
        out.setdefault(mid, {}).setdefault(emoji, []).append(uid)
    return out


def toggle_reaction(message_id: int, user_id: int, emoji: str) -> dict[str, list[int]]:
    if emoji not in settings.ALLOWED_EMOJI:
        raise ChatError("Недопустимая реакция")

    with db_session() as s:
        m = s.get(Message, message_id)
        if not m or m.deleted:
            raise ChatError("Сообщение недоступно")

        existing = s.execute(
            select(Reaction).where(
                Reaction.message_id == message_id,
                Reaction.user_id == user_id,
                Reaction.emoji == emoji,
            )
        ).scalar_one_or_none()

        if existing:
            s.delete(existing)
        else:
            s.add(Reaction(message_id=message_id, user_id=user_id, emoji=emoji))
        s.flush()

        rows = s.execute(
            select(Reaction.emoji, Reaction.user_id)
            .where(Reaction.message_id == message_id)
            .order_by(Reaction.created_at)
        ).all()
        out: dict[str, list[int]] = {}
        for e, uid in rows:
            out.setdefault(e, []).append(uid)
        s.commit()
        return out


def message_chat_id(message_id: int) -> Optional[int]:
    with db_session() as s:
        m = s.get(Message, message_id)
        return m.chat_id if m else None


# ==================== Участники ====================

def add_member(chat_id: int, user_id: int) -> None:
    with db_session() as s:
        exists = s.execute(
            select(ChatMember.id).where(
                ChatMember.chat_id == chat_id, ChatMember.user_id == user_id
            )
        ).first()
        if not exists:
            s.add(ChatMember(chat_id=chat_id, user_id=user_id, role="member"))
            s.commit()


def remove_member(chat_id: int, user_id: int, by_user_id: int) -> bool:
    with db_session() as s:
        chat = s.get(Chat, chat_id)
        if not chat or chat.owner_id != by_user_id:
            return False
        if chat.owner_id == user_id:
            return False

        res = s.execute(
            delete(ChatMember).where(
                ChatMember.chat_id == chat_id, ChatMember.user_id == user_id
            )
        )
        s.commit()
        return res.rowcount > 0


def search_users(query: str, exclude_id: int) -> list[dict]:
    query = (query or "").strip()
    if len(query) < 2:
        return []
    with db_session() as s:
        rows = s.execute(
            select(User.id, User.username)
            .where(User.username.ilike(f"%{query}%"), User.id != exclude_id)
            .limit(20)
        ).all()
        return [{"id": r[0], "username": r[1]} for r in rows]


def search_messages(chat_id: int, query: str) -> list[dict]:
    query = (query or "").strip()
    if len(query) < 2:
        return []
    with db_session() as s:
        rows = s.execute(
            select(Message, User.username)
            .join(User, User.id == Message.user_id)
            .where(
                Message.chat_id == chat_id,
                Message.deleted == False,
                Message.text.ilike(f"%{query}%"),
            )
            .order_by(Message.id.desc()).limit(50)
        ).all()
        return [{
            "id": m.id, "userId": m.user_id, "username": u,
            "text": m.text, "time": m.time,
        } for m, u in rows]