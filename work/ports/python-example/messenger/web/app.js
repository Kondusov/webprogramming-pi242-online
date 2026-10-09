/* ============================================================
   Мессенджер — клиент (Python/FastAPI-версия)
   ============================================================ */

const API = '/api';
const WS_URL = `ws://${location.hostname}:${parseInt(location.port || 80) + 1}`;

/* ============================================================
   СОСТОЯНИЕ
   ============================================================ */

let ws = null;
let token = localStorage.getItem('token');
let currentUser = null;
let chats = {};             // id -> chat
let activeChatId = null;
let messagesCache = {};     // chatId -> [messages]
let membersCache = {};      // chatId -> { members, ownerId }
let reconnectTimer = null;
let typingTimers = {};

/* WebRTC */
const ICE_SERVERS = [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
];
let pc = null;
let localStream = null;
let remoteStream = null;
let callState = 'idle';     // idle | calling | incoming | active
let callPeerId = null;
let callIsVideo = false;
let incomingCallData = null;

const ALLOWED_EMOJI = ['👍','❤️','😂','😮','😢','🔥','🎉','👀'];

/* ============================================================
   DOM
   ============================================================ */

const $ = id => document.getElementById(id);

const authScreen     = $('authScreen');
const appEl          = $('app');
const chatList       = $('chatList');
const messagesEl     = $('messages');
const chatName       = $('chatName');
const chatSub        = $('chatSub');
const composer       = $('composer');
const messageInput   = $('messageInput');
const emptyState     = $('emptyState');
const typingIndicator = $('typingIndicator');

/* ============================================================
   HTTP API
   ============================================================ */

async function api(action, body) {
    const res = await fetch(`${API}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Ошибка запроса');
    return data;
}

/* ============================================================
   АВТОРИЗАЦИЯ
   ============================================================ */

let authMode = 'login';
let pendingLogin = null;

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
    $('authError').textContent = '';

    const usernameInput = $('authUsername').value.trim();
    const password      = $('authPassword').value;
    const emailInput    = $('authEmail') ? $('authEmail').value.trim() : '';

    try {
        let data;
        if (authMode === 'register') {
            data = await api('register', {
                username: usernameInput,
                email: emailInput,
                password,
            });
            if (data.needsVerify) {
                pendingLogin = usernameInput;
                if ($('verifyEmailLabel')) $('verifyEmailLabel').textContent = emailInput;
                showAuthScreen('verify');
                return;
            }
        } else {
            data = await api('login', { login: usernameInput, password });
            if (!data.verified) {
                pendingLogin = usernameInput;
                if ($('verifyEmailLabel')) $('verifyEmailLabel').textContent = data.email || '';
                showAuthScreen('verify');
                return;
            }
        }

        finishAuth(data);
    } catch (err) {
        $('authError').textContent = err.message;
    }
});

$('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('token');
    token = null;
    if (ws) try { ws.close(); } catch {}
    location.reload();
});

/* --- Переключение экранов авторизации --- */
function showAuthScreen(name) {
    const main   = $('authMain');
    const verify = $('verifyScreen');
    const reset  = $('resetScreen');
    if (main)   main.classList.toggle('hidden', name !== 'main');
    if (verify) verify.classList.toggle('hidden', name !== 'verify');
    if (reset)  reset.classList.toggle('hidden', name !== 'reset');
    if (name === 'verify' && $('verifyCode')) setTimeout(() => $('verifyCode').focus(), 50);
}

/* --- Верификация email --- */
const verifyForm = $('verifyForm');
if (verifyForm) {
    verifyForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        $('verifyError').textContent = '';
        try {
            const code = $('verifyCode').value.trim();
            const data = await api('verify_email', { login: pendingLogin, code });
            finishAuth(data);
        } catch (err) {
            $('verifyError').textContent = err.message;
        }
    });
}

const resendBtn = $('resendBtn');
if (resendBtn) {
    resendBtn.addEventListener('click', async () => {
        $('verifyError').textContent = '';
        try {
            await api('resend_code', { login: pendingLogin });
            $('verifyError').style.color = '#2ecc71';
            $('verifyError').textContent = 'Код отправлен повторно';
            setTimeout(() => { $('verifyError').style.color = ''; }, 3000);
        } catch (err) {
            $('verifyError').textContent = err.message;
        }
    });
}

const backBtn = $('backBtn');
if (backBtn) backBtn.addEventListener('click', () => showAuthScreen('main'));

/* --- Сброс пароля --- */
const forgotBtn = $('forgotBtn');
if (forgotBtn) {
    forgotBtn.addEventListener('click', () => {
        const reset = $('resetScreen');
        if (!reset) return;
        reset.querySelectorAll('form').forEach(f => {
            f.classList.toggle('hidden', f.id !== 'resetRequestForm');
        });
        showAuthScreen('reset');
    });
}

document.querySelectorAll('[data-back]').forEach(b => {
    b.addEventListener('click', () => showAuthScreen('main'));
});

const resetReqForm = $('resetRequestForm');
if (resetReqForm) {
    resetReqForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        $('resetError').textContent = '';
        try {
            const email = $('resetEmail').value.trim();
            await api('request_reset', { email });
            $('resetRequestForm').classList.add('hidden');
            $('resetConfirmForm').classList.remove('hidden');
        } catch (err) {
            $('resetError').textContent = err.message;
        }
    });
}

const resetConfForm = $('resetConfirmForm');
if (resetConfForm) {
    resetConfForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        $('resetError').textContent = '';
        try {
            await api('reset_password', {
                email:    $('resetEmail').value.trim(),
                code:     $('resetCode').value.trim(),
                password: $('resetPassword').value,
            });
            alert('Пароль обновлён. Войдите с новым паролем.');
            showAuthScreen('main');
            $('resetCode').value = '';
            $('resetPassword').value = '';
        } catch (err) {
            $('resetError').textContent = err.message;
        }
    });
}

function finishAuth(data) {
    token = data.token;
    currentUser = { id: data.id, username: data.username };
    localStorage.setItem('token', token);

    authScreen.classList.add('hidden');
    appEl.classList.remove('hidden');
    $('meName').textContent = currentUser.username;
    connect();
}

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
    // WebRTC-сообщения — отдельным потоком
    const webrtcTypes = [
        'call_incoming','call_ringing','call_accepted','call_rejected',
        'call_ended','webrtc_offer','webrtc_answer','webrtc_ice',
    ];
    if (webrtcTypes.includes(msg.type)) {
        handleWebRTC(msg);
        return;
    }

    switch (msg.type) {
        case 'hello':
            break;

        case 'auth_ok':
            currentUser = { id: msg.userId, username: msg.username };
            $('meName').textContent = currentUser.username;
            chats = {};
            (msg.chats || []).forEach(c => chats[c.id] = c);
            renderChats();
            break;

        case 'auth_failed':
            localStorage.removeItem('token');
            token = null;
            location.reload();
            break;

        case 'chats':
            (msg.chats || []).forEach(c => { if (!chats[c.id]) chats[c.id] = c; });
            renderChats();
            break;

        case 'chat_created':
            chats[msg.chat.id] = msg.chat;
            renderChats();
            openChat(msg.chat.id);
            break;

        case 'history':
            messagesCache[msg.chatId] = msg.messages || [];
            if (msg.chatId === activeChatId) renderMessages();
            break;

        case 'message':
            appendMessage(msg);
            break;

        case 'message_deleted':
            if (messagesCache[msg.chatId]) {
                const m = messagesCache[msg.chatId].find(x => x.id === msg.messageId);
                if (m) { m.deleted = true; m.text = null; m.reactions = {}; }
                if (msg.chatId === activeChatId) renderMessages();
            }
            break;

        case 'reactions':
            applyReactions(msg);
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
            alert(msg.text || 'Вас исключили из чата');
            break;

        case 'typing':
            showTyping(msg);
            break;

        case 'online':
            break;

        case 'search_result':
            renderSearchResults(msg.users, 'dmSearchResults', (u) => {
                wsSend({ type: 'create_dm', userId: u.id });
                closeModal('dmModal');
            });
            break;

        case 'search_messages_result':
            renderSearchResults(
                (msg.messages || []).map(m => ({
                    id: m.id,
                    username: `${m.username} (${m.time})`,
                    text: m.text,
                })),
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
    const filter = ($('chatFilter')?.value || '').toLowerCase();
    chatList.innerHTML = '';

    Object.values(chats)
        .sort((a, b) => b.id - a.id)
        .filter(c => (c.name || '').toLowerCase().includes(filter))
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
            li.querySelector('.name').textContent = c.name || '—';

            li.onclick = () => openChat(c.id);
            chatList.appendChild(li);
        });
}

$('chatFilter')?.addEventListener('input', renderChats);

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

    const isDm = chat.type === 'dm';

    $('membersBtn').classList.toggle('hidden', isDm);
    $('searchMsgBtn').classList.remove('hidden');
    if ($('voiceCallBtn')) $('voiceCallBtn').classList.toggle('hidden', !isDm);
    if ($('videoCallBtn')) $('videoCallBtn').classList.toggle('hidden', !isDm);

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

    if (!m.deleted) {
        div.appendChild(buildReactionsBar(m));
    }

    const meta = document.createElement('div');
    meta.className = 'meta';
    const t = document.createElement('span');
    t.textContent = m.time || '';
    meta.appendChild(t);

    const chat = chats[activeChatId];
    const canDelete = !m.deleted && (own || (chat && chat.myRole === 'owner'));
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

    const m = {
        id: msg.id, userId: msg.userId, username: msg.username,
        text: msg.text, time: msg.time, deleted: false,
        reactions: msg.reactions || {},
    };
    messagesCache[msg.chatId].push(m);

    if (chats[msg.chatId]) {
        chats[msg.chatId].messages_count = (chats[msg.chatId].messages_count || 0) + 1;
    }

    if (msg.chatId === activeChatId) {
        renderMessage(m);
        scrollBottom();
    } else if (msg.userId !== currentUser.id) {
        flashChat(msg.chatId);
    }
    renderChats();
}

function flashChat(chatId) {
    const el = [...chatList.children].find(li =>
        li.textContent.includes(chats[chatId]?.name)
    );
    if (el) {
        el.style.background = '#fff3cd';
        setTimeout(() => el.style.background = '', 1000);
    }
}

function scrollBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

/* ============================================================
   РЕАКЦИИ
   ============================================================ */

function buildReactionsBar(m) {
    const bar = document.createElement('div');
    bar.className = 'reactions-bar';
    bar.dataset.messageId = m.id;

    const reactions = m.reactions || {};
    for (const [emoji, users] of Object.entries(reactions)) {
        if (!users || !users.length) continue;
        const chip = document.createElement('button');
        chip.className = 'reaction-chip' + (users.includes(currentUser.id) ? ' mine' : '');
        chip.textContent = `${emoji} ${users.length}`;
        chip.onclick = () => wsSend({ type: 'react', messageId: m.id, emoji });
        bar.appendChild(chip);
    }

    const addBtn = document.createElement('button');
    addBtn.className = 'add-reaction';
    addBtn.textContent = '😊+';
    addBtn.onclick = (e) => {
        e.stopPropagation();
        openEmojiPicker(addBtn, m.id);
    };
    bar.appendChild(addBtn);

    return bar;
}

function openEmojiPicker(anchor, messageId) {
    document.querySelectorAll('.emoji-picker').forEach(el => el.remove());

    const picker = document.createElement('div');
    picker.className = 'emoji-picker';

    ALLOWED_EMOJI.forEach(e => {
        const b = document.createElement('button');
        b.textContent = e;
        b.onclick = () => {
            wsSend({ type: 'react', messageId, emoji: e });
            picker.remove();
        };
        picker.appendChild(b);
    });

    document.body.appendChild(picker);

    const rect = anchor.getBoundingClientRect();
    picker.style.left = (rect.left + window.scrollX) + 'px';
    picker.style.top  = (rect.top - 44 + window.scrollY) + 'px';

    setTimeout(() => {
        const close = (ev) => {
            if (!picker.contains(ev.target)) {
                picker.remove();
                document.removeEventListener('click', close);
            }
        };
        document.addEventListener('click', close);
    }, 0);
}

function applyReactions(msg) {
    const list = messagesCache[msg.chatId];
    if (list) {
        const m = list.find(x => x.id === msg.messageId);
        if (m) m.reactions = msg.reactions || {};
    }
    if (msg.chatId !== activeChatId) return;

    const el = messagesEl.querySelector(`.msg[data-id="${msg.messageId}"]`);
    if (!el) return;

    const m = (messagesCache[msg.chatId] || []).find(x => x.id === msg.messageId);
    if (!m) return;

    const oldBar = el.querySelector('.reactions-bar');
    const newBar = buildReactionsBar(m);
    if (oldBar) el.replaceChild(newBar, oldBar);
    else el.insertBefore(newBar, el.querySelector('.meta'));
}

/* ============================================================
   ОТПРАВКА
   ============================================================ */

composer?.addEventListener('submit', (e) => {
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

let lastTypingSent = 0;
messageInput?.addEventListener('input', () => {
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

$('newGroupBtn')?.addEventListener('click', () => {
    const name = prompt('Название группы:');
    if (name && name.trim()) wsSend({ type: 'create_group', name: name.trim() });
});

$('newChannelBtn')?.addEventListener('click', () => {
    const name = prompt('Название канала:');
    if (name && name.trim()) wsSend({ type: 'create_channel', name: name.trim() });
});

$('newDmBtn')?.addEventListener('click', () => openModal('dmModal'));

/* ============================================================
   МОДАЛКИ
   ============================================================ */

function openModal(id) { const el = $(id); if (el) el.classList.remove('hidden'); }
function closeModal(id) { const el = $(id); if (el) el.classList.add('hidden'); }

document.querySelectorAll('.modal').forEach(m => {
    m.addEventListener('click', (e) => {
        if (e.target === m || e.target.dataset.close !== undefined) {
            m.classList.add('hidden');
        }
    });
});

/* Участники */
$('membersBtn')?.addEventListener('click', () => {
    if (!activeChatId) return;
    wsSend({ type: 'members', chatId: activeChatId });
    openModal('membersModal');
});

function renderMembers() {
    const data = membersCache[activeChatId];
    if (!data) return;

    const list = $('membersList');
    if (!list) return;
    list.innerHTML = '';

    data.members.forEach(m => {
        const li = document.createElement('li');

        const left = document.createElement('span');
        const nameEl = document.createElement('span');
        nameEl.className = 'name';
        nameEl.textContent = m.username;
        left.appendChild(nameEl);
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
$('addMemberBtn')?.addEventListener('click', () => {
    const username = $('addMemberInput').value.trim();
    if (!username) return;

    wsSend({ type: 'search_users', q: username });

    const handler = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch { return; }
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
$('dmSearchGo')?.addEventListener('click', () => {
    const q = $('dmSearchInput').value.trim();
    if (q.length >= 2) wsSend({ type: 'search_users', q });
});

function renderSearchResults(items, containerId, onClick) {
    const list = $(containerId);
    if (!list) return;
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
$('searchMsgBtn')?.addEventListener('click', () => {
    if (!activeChatId) return;
    const sr = $('searchResults');
    if (sr) sr.innerHTML = '';
    openModal('searchModal');
});

$('searchMsgGo')?.addEventListener('click', () => {
    const q = $('searchMsgInput').value.trim();
    if (q.length >= 2) wsSend({ type: 'search_messages', chatId: activeChatId, q });
});

/* ============================================================
   ЗВОНКИ (WebRTC)
   ============================================================ */

const callScreen = $('callScreen');
const remoteVideo = $('remoteVideo');
const localVideo = $('localVideo');
const callInfo = $('callInfo');

async function setupPeerConnection() {
    pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });

    remoteStream = new MediaStream();
    if (remoteVideo) remoteVideo.srcObject = remoteStream;

    pc.ontrack = (e) => {
        e.streams[0].getTracks().forEach(t => {
            if (!remoteStream.getTracks().some(x => x.id === t.id)) {
                remoteStream.addTrack(t);
            }
        });
    };

    pc.onicecandidate = (e) => {
        if (e.candidate && callPeerId) {
            wsSend({
                type: 'webrtc_ice',
                toUserId: callPeerId,
                data: e.candidate.toJSON(),
            });
        }
    };

    pc.onconnectionstatechange = () => {
        if (callInfo) callInfo.textContent = 'Состояние: ' + pc.connectionState;
        if (['failed', 'disconnected', 'closed'].includes(pc.connectionState)) {
            endCall();
        }
    };

    if (localStream) {
        localStream.getTracks().forEach(t => pc.addTrack(t, localStream));
    }
}

async function getLocalMedia(video) {
    if (localStream) return localStream;
    try {
        localStream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: video ? { width: 1280, height: 720 } : false,
        });
        if (localVideo) localVideo.srcObject = localStream;
        return localStream;
    } catch (err) {
        alert('Не удалось получить доступ к камере/микрофону: ' + err.message);
        throw err;
    }
}

async function startCall(toUserId, video) {
    if (callState !== 'idle') { alert('Вы уже в звонке'); return; }

    callPeerId = toUserId;
    callIsVideo = video;
    callState = 'calling';

    try {
        await getLocalMedia(video);
    } catch {
        callState = 'idle';
        return;
    }

    callScreen?.classList.remove('hidden');
    if (localVideo) localVideo.classList.toggle('hidden', !video);
    if (callInfo) callInfo.textContent = 'Вызов…';

    wsSend({ type: 'call_invite', toUserId, video });
}

async function acceptIncomingCall() {
    if (!incomingCallData) return;
    callPeerId = incomingCallData.fromUserId;
    callIsVideo = incomingCallData.video;
    callState = 'active';

    $('incomingCallModal')?.classList.add('hidden');

    try {
        await getLocalMedia(callIsVideo);
    } catch {
        callState = 'idle';
        return;
    }

    await setupPeerConnection();

    callScreen?.classList.remove('hidden');
    if (localVideo) localVideo.classList.toggle('hidden', !callIsVideo);
    if (callInfo) callInfo.textContent = 'Соединение…';

    wsSend({ type: 'call_accept', toUserId: callPeerId });
}

function rejectIncomingCall() {
    if (!incomingCallData) return;
    wsSend({ type: 'call_reject', toUserId: incomingCallData.fromUserId });
    incomingCallData = null;
    $('incomingCallModal')?.classList.add('hidden');
    callState = 'idle';
}

async function handleWebRTC(msg) {
    switch (msg.type) {
        case 'call_incoming':
            if (callState !== 'idle') {
                wsSend({ type: 'call_reject', toUserId: msg.fromUserId });
                return;
            }
            incomingCallData = msg;
            callState = 'incoming';
            if ($('incomingFrom')) $('incomingFrom').textContent = `📞 ${msg.fromName}`;
            if ($('incomingType')) $('incomingType').textContent = msg.video ? 'Видеозвонок' : 'Голосовой звонок';
            $('incomingCallModal')?.classList.remove('hidden');
            setTimeout(() => {
                if (callState === 'incoming') rejectIncomingCall();
            }, 30000);
            break;

        case 'call_ringing':
            if (callInfo) callInfo.textContent = 'Идёт вызов…';
            break;

        case 'call_accepted':
            callState = 'active';
            if (callInfo) callInfo.textContent = 'Соединение…';
            await setupPeerConnection();

            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            wsSend({ type: 'webrtc_offer', toUserId: callPeerId, data: offer });
            break;

        case 'call_rejected':
            alert(`${msg.fromName} отклонил звонок`);
            cleanupCall();
            break;

        case 'call_ended':
            if (callInfo) callInfo.textContent = 'Звонок завершён';
            setTimeout(cleanupCall, 500);
            break;

        case 'webrtc_offer':
            if (!pc) await setupPeerConnection();
            await pc.setRemoteDescription(new RTCSessionDescription(msg.data));
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            wsSend({ type: 'webrtc_answer', toUserId: callPeerId, data: answer });
            break;

        case 'webrtc_answer':
            if (!pc) return;
            await pc.setRemoteDescription(new RTCSessionDescription(msg.data));
            break;

        case 'webrtc_ice':
            if (!pc) return;
            try {
                await pc.addIceCandidate(new RTCIceCandidate(msg.data));
            } catch (e) {
                console.warn('ICE error:', e);
            }
            break;
    }
}

function endCall() {
    if (callPeerId) wsSend({ type: 'call_end', toUserId: callPeerId });
    cleanupCall();
}

function cleanupCall() {
    if (pc) { try { pc.close(); } catch {} pc = null; }
    if (localStream) {
        localStream.getTracks().forEach(t => t.stop());
        localStream = null;
    }
    remoteStream = null;
    callPeerId = null;
    callState = 'idle';
    callIsVideo = false;
    incomingCallData = null;

    callScreen?.classList.add('hidden');
    $('incomingCallModal')?.classList.add('hidden');
    if (remoteVideo) remoteVideo.srcObject = null;
    if (localVideo) localVideo.srcObject = null;
}

$('toggleMic')?.addEventListener('click', () => {
    if (!localStream) return;
    const t = localStream.getAudioTracks()[0];
    if (!t) return;
    t.enabled = !t.enabled;
    $('toggleMic').classList.toggle('muted', !t.enabled);
});

$('toggleCam')?.addEventListener('click', () => {
    if (!localStream) return;
    const t = localStream.getVideoTracks()[0];
    if (!t) return;
    t.enabled = !t.enabled;
    $('toggleCam').classList.toggle('muted', !t.enabled);
});

$('hangupBtn')?.addEventListener('click', endCall);
$('acceptCall')?.addEventListener('click', acceptIncomingCall);
$('rejectCall')?.addEventListener('click', rejectIncomingCall);

$('voiceCallBtn')?.addEventListener('click', () => {
    const chat = chats[activeChatId];
    if (!chat) return;
    if (chat.type !== 'dm' || !chat.partner_id) {
        alert('Звонок доступен только в личном чате');
        return;
    }
    startCall(chat.partner_id, false);
});

$('videoCallBtn')?.addEventListener('click', () => {
    const chat = chats[activeChatId];
    if (!chat) return;
    if (chat.type !== 'dm' || !chat.partner_id) {
        alert('Видеозвонок доступен только в личном чате');
        return;
    }
    startCall(chat.partner_id, true);
});

/* ============================================================
   СТАРТ
   ============================================================ */

(async function init() {
    if (token) {
        try {
            const data = await api('me', { token });
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
    showAuthScreen('main');
})();