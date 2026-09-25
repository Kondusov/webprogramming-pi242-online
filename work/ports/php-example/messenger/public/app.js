/* ============================================================
   Мессенджер — клиент
   ============================================================ */

const API = 'api.php';
const WS_URL = 'ws://localhost:8080';

/* ---------- Состояние ---------- */
let ws = null;
let token = localStorage.getItem('token');
let currentUser = null;
let chats = {};           // id -> chat
let activeChatId = null;
let messagesCache = {};   // chatId -> [messages]
let membersCache = {};    // chatId -> { members, ownerId }
let reconnectTimer = null;
let typingTimers = {};

/* ---------- DOM ---------- */
const $ = id => document.getElementById(id);
const authScreen = $('authScreen');
const appEl      = $('app');
const chatList   = $('chatList');
const messagesEl = $('messages');
const chatName   = $('chatName');
const chatSub    = $('chatSub');
const composer   = $('composer');
const messageInput = $('messageInput');
const emptyState = $('emptyState');
const typingIndicator = $('typingIndicator');

/* ============================================================
   АВТОРИЗАЦИЯ
   ============================================================ */

let authMode = 'login';

document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        authMode = tab.dataset.tab;
        $('authSubmit').textContent = authMode === 'login' ? 'Войти' : 'Зарегистрироваться';
        $('authError').textContent = '';
    });
});

$('authForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = $('authUsername').value.trim();
    const password = $('authPassword').value;
    $('authError').textContent = '';

    try {
        const res = await fetch(`${API}?action=${authMode}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Ошибка');

        token = data.token;
        currentUser = { id: data.id, username: data.username };
        localStorage.setItem('token', token);

        authScreen.classList.add('hidden');
        appEl.classList.remove('hidden');
        $('meName').textContent = currentUser.username;
        connect();
    } catch (err) {
        $('authError').textContent = err.message;
    }
});

$('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('token');
    token = null;
    if (ws) ws.close();
    location.reload();
});

/* ============================================================
   WEBSOCKET
   ============================================================ */

function connect() {
    if (ws && ws.readyState <= 1) return;

    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'auth', token }));
    };

    ws.onmessage = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch { return; }
        handleServerMessage(msg);
    };

    ws.onclose = () => {
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(connect, 2000);
    };

    ws.onerror = () => {};
}

function wsSend(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(obj));
    }
}

function handleServerMessage(msg) {
    switch (msg.type) {
        case 'hello':
            break;

        case 'auth_ok':
            currentUser = { id: msg.userId, username: msg.username };
            $('meName').textContent = currentUser.username;
            chats = {};
            msg.chats.forEach(c => chats[c.id] = c);
            renderChats();
            break;

        case 'auth_failed':
            localStorage.removeItem('token');
            token = null;
            location.reload();
            break;

        case 'chats':
            msg.chats.forEach(c => {
                if (!chats[c.id]) chats[c.id] = c;
            });
            renderChats();
            break;

        case 'chat_created':
            chats[msg.chat.id] = msg.chat;
            renderChats();
            openChat(msg.chat.id);
            break;

        case 'history':
            messagesCache[msg.chatId] = msg.messages;
            if (msg.chatId === activeChatId) renderMessages();
            break;

        case 'message':
            appendMessage(msg);
            break;

        case 'message_deleted':
            if (messagesCache[msg.chatId]) {
                const m = messagesCache[msg.chatId].find(x => x.id === msg.messageId);
                if (m) { m.deleted = true; m.text = null; }
                if (msg.chatId === activeChatId) renderMessages();
            }
            break;

        case 'members':
            membersCache[msg.chatId] = { members: msg.members, ownerId: msg.ownerId };
            if (msg.chatId === activeChatId) renderMembers();
            break;

        case 'member_joined':
        case 'member_left':
            if (msg.chatId === activeChatId) wsSend({ type: 'members', chatId: msg.chatId });
            break;

        case 'kicked':
            delete chats[msg.chatId];
            if (activeChatId === msg.chatId) closeChat();
            renderChats();
            alert(msg.text);
            break;

        case 'typing':
            showTyping(msg);
            break;

        case 'online':
            // можно отображать онлайн-точки в списке
            break;

        case 'search_result':
            renderSearchResults(msg.users, 'dmSearchResults', (u) => {
                wsSend({ type: 'create_dm', userId: u.id });
                closeModal('dmModal');
            });
            break;

        case 'search_messages_result':
            renderSearchResults(
                msg.messages.map(m => ({ id: m.id, username: `${m.username} (${m.time})`, text: m.text })),
                'searchResults',
                null
            );
            break;

        case 'error':
            console.warn('Server error:', msg.text);
            alert(msg.text);
            break;
    }
}

/* ============================================================
   СПИСОК ЧАТОВ
   ============================================================ */

function renderChats() {
    const filter = $('chatFilter').value.toLowerCase();
    chatList.innerHTML = '';

    Object.values(chats)
        .sort((a, b) => b.id - a.id)
        .filter(c => c.name.toLowerCase().includes(filter))
        .forEach(c => {
            const li = document.createElement('li');
            li.className = c.id === activeChatId ? 'active' : '';

            const icon = { group: '👥', channel: '📢', dm: '💬' }[c.type] || '💬';
            const count = c.messages_count ? ` · ${c.messages_count}` : '';

            li.innerHTML = `
                <span class="type-icon">${icon}</span>
                <span class="name"></span>
                <span class="count">${count}</span>
            `;
            li.querySelector('.name').textContent = c.name;

            li.onclick = () => openChat(c.id);
            chatList.appendChild(li);
        });
}

$('chatFilter').addEventListener('input', renderChats);

/* ============================================================
   ОТКРЫТИЕ ЧАТА
   ============================================================ */

function openChat(chatId) {
    if (!chats[chatId]) return;
    activeChatId = chatId;
    const chat = chats[chatId];

    emptyState.classList.add('hidden');
    composer.classList.remove('hidden');

    const icon = { group: '👥', channel: '📢', dm: '💬' }[chat.type] || '💬';
    chatName.textContent = `${icon} ${chat.name}`;

    const role = chat.myRole === 'owner' ? 'владелец' : 'участник';
    chatSub.textContent = `${typeLabel(chat.type)} · ${role}`;

    $('membersBtn').classList.toggle('hidden', chat.type === 'dm');
    $('searchMsgBtn').classList.remove('hidden');

    // В канале писать может только владелец
    const canWrite = chat.type !== 'channel' || chat.myRole === 'owner';
    composer.classList.toggle('hidden', !canWrite);
    if (!canWrite) {
        chatSub.textContent += ' · только владелец может писать';
    }

    messagesEl.innerHTML = '<div class="msg system">Загрузка…</div>';
    wsSend({ type: 'history', chatId, limit: 50 });
    wsSend({ type: 'members', chatId });

    renderChats();
    messageInput.focus();
}

function closeChat() {
    activeChatId = null;
    messagesEl.innerHTML = '';
    chatName.textContent = 'Выберите чат';
    chatSub.textContent = '';
    composer.classList.add('hidden');
    emptyState.classList.remove('hidden');
}

function typeLabel(t) {
    return { group: 'группа', channel: 'канал', dm: 'личный чат' }[t] || t;
}

/* ============================================================
   СООБЩЕНИЯ
   ============================================================ */

function renderMessages() {
    const list = messagesCache[activeChatId] || [];
    messagesEl.innerHTML = '';

    list.forEach(m => renderMessage(m));
    scrollBottom();
}

function renderMessage(m) {
    const div = document.createElement('div');
    const own = m.userId === currentUser.id;
    div.className = 'msg ' + (own ? 'own' : 'other') + (m.deleted ? ' deleted' : '');
    div.dataset.id = m.id;

    if (!own) {
        const author = document.createElement('span');
        author.className = 'author';
        author.textContent = m.username;
        div.appendChild(author);
    }

    const text = document.createElement('span');
    text.className = 'text';
    text.textContent = m.deleted ? 'сообщение удалено' : (m.text || '');
    div.appendChild(text);

    const meta = document.createElement('div');
    meta.className = 'meta';
    const t = document.createElement('span');
    t.textContent = m.time || '';
    meta.appendChild(t);

    // Кнопка удаления: своё сообщение или если я владелец
    const chat = chats[activeChatId];
    const canDelete = !m.deleted && (
        own || (chat && chat.myRole === 'owner')
    );
    if (canDelete) {
        const del = document.createElement('button');
        del.className = 'del-btn';
        del.textContent = '🗑';
        del.onclick = () => {
            if (confirm('Удалить сообщение?')) {
                wsSend({ type: 'delete_message', chatId: activeChatId, messageId: m.id });
            }
        };
        meta.appendChild(del);
    }

    div.appendChild(meta);
    messagesEl.appendChild(div);
}

function appendMessage(msg) {
    if (!messagesCache[msg.chatId]) messagesCache[msg.chatId] = [];
    if (messagesCache[msg.chatId].some(m => m.id === msg.id)) return;

    messagesCache[msg.chatId].push({
        id: msg.id, userId: msg.userId, username: msg.username,
        text: msg.text, time: msg.time, deleted: false,
    });

    // Обновим счётчик в списке чатов
    if (chats[msg.chatId]) {
        chats[msg.chatId].messages_count = (chats[msg.chatId].messages_count || 0) + 1;
    }

    if (msg.chatId === activeChatId) {
        renderMessage(messagesCache[msg.chatId].slice(-1)[0]);
        scrollBottom();
    } else if (msg.userId !== currentUser.id) {
        // Уведомим о новом сообщении в другом чате
        flashChat(msg.chatId);
    }
    renderChats();
}

function flashChat(chatId) {
    const el = [...chatList.children].find(li => li.textContent.includes(chats[chatId]?.name));
    if (el) {
        el.style.background = '#fff3cd';
        setTimeout(() => el.style.background = '', 1000);
    }
}

function scrollBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

/* ============================================================
   ОТПРАВКА
   ============================================================ */

composer.addEventListener('submit', (e) => {
    e.preventDefault();
    sendMessage();
});

function sendMessage() {
    const text = messageInput.value.trim();
    if (!text || !activeChatId) return;
    wsSend({ type: 'message', chatId: activeChatId, text });
    messageInput.value = '';
    wsSend({ type: 'typing', chatId: activeChatId, state: false });
}

// Индикатор «печатает…»
let lastTypingSent = 0;
messageInput.addEventListener('input', () => {
    if (!activeChatId) return;
    const now = Date.now();
    if (now - lastTypingSent > 1000) {
        lastTypingSent = now;
        wsSend({ type: 'typing', chatId: activeChatId, state: true });
    }
});

function showTyping(msg) {
    if (msg.chatId !== activeChatId) return;

    if (msg.state) {
        typingIndicator.textContent = `${msg.username} печатает…`;
        typingIndicator.classList.remove('hidden');

        clearTimeout(typingTimers[msg.userId]);
        typingTimers[msg.userId] = setTimeout(() => {
            typingIndicator.classList.add('hidden');
        }, 3000);
    } else {
        typingIndicator.classList.add('hidden');
    }
}

/* ============================================================
   СОЗДАНИЕ ЧАТОВ
   ============================================================ */

$('newGroupBtn').addEventListener('click', () => {
    const name = prompt('Название группы:');
    if (name && name.trim()) wsSend({ type: 'create_group', name: name.trim() });
});

$('newChannelBtn').addEventListener('click', () => {
    const name = prompt('Название канала:');
    if (name && name.trim()) wsSend({ type: 'create_channel', name: name.trim() });
});

$('newDmBtn').addEventListener('click', () => openModal('dmModal'));

/* ============================================================
   МОДАЛКИ
   ============================================================ */

function openModal(id) { $(id).classList.remove('hidden'); }
function closeModal(id) { $(id).classList.add('hidden'); }

document.querySelectorAll('.modal').forEach(m => {
    m.addEventListener('click', (e) => {
        if (e.target === m || e.target.dataset.close !== undefined) {
            m.classList.add('hidden');
        }
    });
});

/* Участники */
$('membersBtn').addEventListener('click', () => {
    if (!activeChatId) return;
    wsSend({ type: 'members', chatId: activeChatId });
    openModal('membersModal');
});

function renderMembers() {
    const data = membersCache[activeChatId];
    if (!data) return;

    const list = $('membersList');
    list.innerHTML = '';

    data.members.forEach(m => {
        const li = document.createElement('li');

        const left = document.createElement('span');
        left.innerHTML = `<span class="name"></span>`;
        left.querySelector('.name').textContent = m.username;
        li.appendChild(left);

        if (m.role === 'owner') {
            const badge = document.createElement('span');
            badge.className = 'role-badge';
            badge.textContent = 'владелец';
            li.appendChild(badge);
        } else if (data.ownerId === currentUser.id) {
            const kick = document.createElement('button');
            kick.className = 'kick-btn';
            kick.textContent = 'Исключить';
            kick.onclick = () => {
                if (confirm(`Исключить ${m.username}?`)) {
                    wsSend({ type: 'kick_user', chatId: activeChatId, userId: m.id });
                    setTimeout(() => wsSend({ type: 'members', chatId: activeChatId }), 200);
                }
            };
            li.appendChild(kick);
        }

        list.appendChild(li);
    });
}

/* Добавление участника */
$('addMemberBtn').addEventListener('click', () => {
    const username = $('addMemberInput').value.trim();
    if (!username) return;
    wsSend({ type: 'search_users', q: username });
    // Найдём пользователя и добавим
    const handler = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'search_result' && msg.users.length > 0) {
            wsSend({ type: 'add_user', chatId: activeChatId, userId: msg.users[0].id });
            ws.removeEventListener('message', handler);
            $('addMemberInput').value = '';
            setTimeout(() => wsSend({ type: 'members', chatId: activeChatId }), 300);
        }
    };
    ws.addEventListener('message', handler);
});

/* Поиск DM */
$('dmSearchGo').addEventListener('click', () => {
    const q = $('dmSearchInput').value.trim();
    if (q.length >= 2) wsSend({ type: 'search_users', q });
});

function renderSearchResults(items, containerId, onClick) {
    const list = $(containerId);
    list.innerHTML = '';
    items.forEach(item => {
        const li = document.createElement('li');
        const name = document.createElement('span');
        name.textContent = item.username || item.name || '';
        li.appendChild(name);

        if (item.text) {
            const t = document.createElement('span');
            t.style.cssText = 'opacity:.6;font-size:12px;margin-left:8px;';
            t.textContent = item.text;
            li.appendChild(t);
        }

        if (onClick) li.onclick = () => onClick(item);
        list.appendChild(li);
    });
}

/* Поиск сообщений */
$('searchMsgBtn').addEventListener('click', () => {
    if (!activeChatId) return;
    $('searchResults').innerHTML = '';
    openModal('searchModal');
});

$('searchMsgGo').addEventListener('click', () => {
    const q = $('searchMsgInput').value.trim();
    if (q.length >= 2) wsSend({ type: 'search_messages', chatId: activeChatId, q });
});

/* ============================================================
   СТАРТ
   ============================================================ */

(async function init() {
    if (token) {
        try {
            const res = await fetch(`${API}?action=me`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token }),
            });
            const data = await res.json();
            if (data.ok && data.user) {
                currentUser = data.user;
                authScreen.classList.add('hidden');
                appEl.classList.remove('hidden');
                $('meName').textContent = currentUser.username;
                connect();
                return;
            }
        } catch {}
        localStorage.removeItem('token');
        token = null;
    }
    authScreen.classList.remove('hidden');
})();