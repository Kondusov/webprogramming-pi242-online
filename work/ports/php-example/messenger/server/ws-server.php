<?php
/**
 * Мессенджер WebSocket-сервер.
 * Запуск: php server/ws-server.php
 */

require_once __DIR__ . '/ws.php';
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/chats.php';

$host = '0.0.0.0';
$port = 8080;
$pingInterval = 30;
$pongTimeout = 90;

/* ---------- Сокет ---------- */
$server = socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
socket_set_option($server, SOL_SOCKET, SO_REUSEADDR, 1);
socket_bind($server, $host, $port);
socket_listen($server, 20);
socket_set_nonblock($server);

echo "Мессенджер запущен на ws://$host:$port\n";
echo "HTTP API для логина: http://localhost:8000/api.php\n";

/* ---------- Состояние ---------- */
$clients = [];      // sockId => ['sock','userId','username','lastPong','typing']
$handshakes = [];   // sockId => ['sock','buffer']
$userSockets = [];  // userId => [sockId1, sockId2, ...] — один пользователь может иметь несколько вкладок
$lastPing = time();

function sockId($sock): int {
    return is_object($sock) ? spl_object_id($sock) : (int)$sock;
}

function sendToUser(int $userId, array $payload): void {
    global $userSockets, $clients;
    if (empty($userSockets[$userId])) return;
    foreach ($userSockets[$userId] as $sid) {
        if (isset($clients[$sid])) sendJson($clients[$sid]['sock'], $payload);
    }
}

function broadcastToChat(int $chatId, array $payload, ?int $exceptUserId = null): void {
    foreach (chatMembersIds($chatId) as $uid) {
        if ($exceptUserId !== null && $uid === $exceptUserId) continue;
        sendToUser($uid, $payload);
    }
}

/* ---------- Главный цикл ---------- */
while (true) {
    $read = [$server];
    foreach ($clients as $c)    $read[] = $c['sock'];
    foreach ($handshakes as $h) $read[] = $h['sock'];

    $write = $except = null;
    if (@socket_select($read, $write, $except, 1) === false) continue;

    // Новое подключение
    if (in_array($server, $read, true)) {
        $new = @socket_accept($server);
        if ($new !== false) {
            socket_set_nonblock($new);
            $handshakes[sockId($new)] = ['sock' => $new, 'buffer' => ''];
        }
        $k = array_search($server, $read, true);
        if ($k !== false) unset($read[$k]);
    }

    foreach ($read as $sock) {
        $id = sockId($sock);
        $data = @socket_read($sock, 32768, PHP_BINARY_READ);

        if ($data === false) { handleDisconnect($id); continue; }
        if ($data === '')    { continue; }

        // Handshake
        if (isset($handshakes[$id])) {
            $handshakes[$id]['buffer'] .= $data;
            if (strpos($handshakes[$id]['buffer'], "\r\n\r\n") === false) continue;

            $headers = $handshakes[$id]['buffer'];
            unset($handshakes[$id]);

            if (performHandshake($sock, $headers)) {
                $clients[$id] = [
                    'sock'      => $sock,
                    'userId'    => null,
                    'username'  => null,
                    'lastPong'  => time(),
                    'typing'    => false,
                ];
                sendJson($sock, ['type' => 'hello', 'text' => 'Добро пожаловать! Авторизуйтесь.']);
            }
            continue;
        }

        if (!isset($clients[$id])) continue;

        // Любая активность сбрасывает pong-таймер
        $clients[$id]['lastPong'] = time();

        $frame = decodeFrame($data);
        if ($frame === null) continue;

        // ping/pong от клиента — игнорируем (браузер сам отвечает)
        if (in_array($frame['opcode'], [0x9, 0xA], true)) continue;
        if ($frame['opcode'] !== 0x1) continue; // только текст

        $msg = json_decode($frame['payload'], true);
        if (!is_array($msg)) continue;

        try {
            handleClientMessage($id, $msg);
        } catch (Throwable $e) {
            sendJson($clients[$id]['sock'], [
                'type' => 'error',
                'text' => $e->getMessage(),
            ]);
        }
    }

    // Ping/Pong
    if (time() - $lastPing >= $pingInterval) {
        $lastPing = time();
        foreach ($clients as $cid => $c) {
            sendPing($c['sock']);
            if (time() - $c['lastPong'] > $pongTimeout) {
                echo "[-] #$cid не отвечает — disconnect\n";
                handleDisconnect($cid);
            }
        }
    }
}

/* ==================== Обработка сообщений клиента ==================== */

function handleClientMessage(int $sid, array $msg): void
{
    global $clients, $userSockets;

    $type = $msg['type'] ?? '';
    $c = &$clients[$sid];

    // Первое сообщение должно быть auth
    if ($type === 'auth') {
        $userId = verifyToken((string)($msg['token'] ?? ''));
        if (!$userId) {
            sendJson($c['sock'], ['type' => 'auth_failed', 'text' => 'Неверный токен']);
            return;
        }
        $user = userById($userId);
        if (!$user) {
            sendJson($c['sock'], ['type' => 'auth_failed', 'text' => 'Пользователь не найден']);
            return;
        }

        // Если этот userId уже был привязан к другому сокету — не рвём, мультивкладки разрешены
        $c['userId']   = $user['id'];
        $c['username'] = $user['username'];
        $userSockets[$user['id']][] = $sid;

        sendJson($c['sock'], [
            'type'     => 'auth_ok',
            'userId'   => $user['id'],
            'username' => $user['username'],
            'chats'    => listChatsForUser($user['id']),
        ]);

        broadcastOnline();
        return;
    }

    // Всё остальное требует авторизации
    if (!$c['userId']) {
        sendJson($c['sock'], ['type' => 'error', 'text' => 'Сначала авторизуйтесь']);
        return;
    }

    $userId = $c['userId'];

    switch ($type) {
        /* ---------- Чаты ---------- */
        case 'create_group':
            $chatId = createGroup($userId, (string)($msg['name'] ?? ''));
            sendJson($c['sock'], ['type' => 'chat_created', 'chat' => chatSummary($chatId, $userId)]);
            broadcastOnline();
            break;

        case 'create_channel':
            $chatId = createChannel($userId, (string)($msg['name'] ?? ''));
            sendJson($c['sock'], ['type' => 'chat_created', 'chat' => chatSummary($chatId, $userId)]);
            broadcastOnline();
            break;

        case 'create_dm':
            $toUserId = (int)($msg['userId'] ?? 0);
            $chatId = getOrCreateDm($userId, $toUserId);
            $summary = chatSummary($chatId, $userId);
            sendJson($c['sock'], ['type' => 'chat_created', 'chat' => $summary]);
            // Уведомим собеседника
            sendToUser($toUserId, [
                'type' => 'chat_created',
                'chat' => chatSummary($chatId, $toUserId),
            ]);
            break;

        case 'join_chat':
            $chatId = (int)($msg['chatId'] ?? 0);
            if (chatInfo($chatId)) {
                addMember($chatId, $userId);
                sendJson($c['sock'], ['type' => 'chat_created', 'chat' => chatSummary($chatId, $userId)]);
            }
            break;

        case 'list_chats':
            sendJson($c['sock'], ['type' => 'chats', 'chats' => listChatsForUser($userId)]);
            break;

        /* ---------- Сообщения ---------- */
        case 'history':
            $chatId = (int)($msg['chatId'] ?? 0);
            if (!isMember($chatId, $userId)) throw new RuntimeException('Нет доступа');
            $limit    = (int)($msg['limit'] ?? 50);
            $beforeId = (int)($msg['beforeId'] ?? 0);
            sendJson($c['sock'], [
                'type'     => 'history',
                'chatId'   => $chatId,
                'messages' => messagesForChat($chatId, $limit, $beforeId),
            ]);
            break;

        case 'message':
            $chatId = (int)($msg['chatId'] ?? 0);
            $text   = (string)($msg['text'] ?? '');
            if (!isMember($chatId, $userId)) throw new RuntimeException('Нет доступа');

            $chat = chatInfo($chatId);
            if (!$chat) throw new RuntimeException('Чат не найден');

            // В канале пишет только владелец
            if ($chat['type'] === 'channel' && !isOwner($chatId, $userId)) {
                throw new RuntimeException('В канале может писать только владелец');
            }

            $saved = saveMessage($chatId, $userId, $text);
            $payload = [
                'type'     => 'message',
                'chatId'   => $chatId,
                'id'       => $saved['id'],
                'userId'   => $userId,
                'username' => $c['username'],
                'text'     => $saved['text'],
                'time'     => $saved['time'],
            ];
            broadcastToChat($chatId, $payload);
            break;

        case 'delete_message':
            $messageId = (int)($msg['messageId'] ?? 0);
            $chatId    = (int)($msg['chatId'] ?? 0);
            if (!isMember($chatId, $userId)) throw new RuntimeException('Нет доступа');
            if (deleteMessage($messageId, $userId)) {
                broadcastToChat($chatId, [
                    'type'      => 'message_deleted',
                    'chatId'    => $chatId,
                    'messageId' => $messageId,
                ]);
            }
            break;

        /* ---------- Управление участниками ---------- */
        case 'members':
            $chatId = (int)($msg['chatId'] ?? 0);
            if (!isMember($chatId, $userId)) throw new RuntimeException('Нет доступа');
            sendJson($c['sock'], [
                'type'    => 'members',
                'chatId'  => $chatId,
                'members' => chatMembers($chatId),
                'ownerId' => (int)(chatInfo($chatId)['owner_id'] ?? 0),
            ]);
            break;

        case 'kick_user':
            $chatId   = (int)($msg['chatId'] ?? 0);
            $targetId = (int)($msg['userId'] ?? 0);
            if (!removeMember($chatId, $targetId, $userId)) {
                throw new RuntimeException('Нельзя исключить этого пользователя');
            }
            sendToUser($targetId, [
                'type'   => 'kicked',
                'chatId' => $chatId,
                'text'   => 'Вас исключили из чата',
            ]);
            broadcastToChat($chatId, [
                'type'   => 'member_left',
                'chatId' => $chatId,
                'userId' => $targetId,
            ]);
            break;

        case 'add_user':
            $chatId   = (int)($msg['chatId'] ?? 0);
            $targetId = (int)($msg['userId'] ?? 0);
            if (!isOwner($chatId, $userId) && !isMember($chatId, $userId)) {
                throw new RuntimeException('Нет доступа');
            }
            addMember($chatId, $targetId);
            sendToUser($targetId, [
                'type' => 'chat_created',
                'chat' => chatSummary($chatId, $targetId),
            ]);
            broadcastToChat($chatId, [
                'type'   => 'member_joined',
                'chatId' => $chatId,
                'userId' => $targetId,
            ]);
            break;

        /* ---------- Разное ---------- */
        case 'typing':
            $chatId = (int)($msg['chatId'] ?? 0);
            if (!isMember($chatId, $userId)) return;
            broadcastToChat($chatId, [
                'type'     => 'typing',
                'chatId'   => $chatId,
                'userId'   => $userId,
                'username' => $c['username'],
                'state'    => (bool)($msg['state'] ?? false),
            ], $userId);
            break;

        case 'search_users':
            $q = trim((string)($msg['q'] ?? ''));
            if (mb_strlen($q) < 2) {
                sendJson($c['sock'], ['type' => 'search_result', 'users' => []]);
                return;
            }
            $stmt = db()->prepare("
                SELECT id, username FROM users
                WHERE username LIKE ? AND id != ?
                LIMIT 20
            ");
            $stmt->execute(['%' . $q . '%', $userId]);
            sendJson($c['sock'], [
                'type'  => 'search_result',
                'users' => array_map(fn($r) => ['id' => (int)$r['id'], 'username' => $r['username']],
                                     $stmt->fetchAll(PDO::FETCH_ASSOC)),
            ]);
            break;

        case 'search_messages':
            $chatId = (int)($msg['chatId'] ?? 0);
            $q = trim((string)($msg['q'] ?? ''));
            if (!isMember($chatId, $userId) || mb_strlen($q) < 2) return;
            $stmt = db()->prepare("
                SELECT m.id, m.user_id, u.username, m.text, m.time
                FROM messages m JOIN users u ON u.id = m.user_id
                WHERE m.chat_id = ? AND m.deleted = 0 AND m.text LIKE ?
                ORDER BY m.id DESC LIMIT 50
            ");
            $stmt->execute([$chatId, '%' . $q . '%']);
            sendJson($c['sock'], [
                'type'   => 'search_messages_result',
                'chatId' => $chatId,
                'messages' => array_map(fn($r) => [
                    'id' => (int)$r['id'], 'userId' => (int)$r['user_id'],
                    'username' => $r['username'], 'text' => $r['text'], 'time' => $r['time'],
                ], $stmt->fetchAll(PDO::FETCH_ASSOC)),
            ]);
            break;
    }
}

/* ==================== Служебное ==================== */

function chatSummary(int $chatId, int $forUserId): array
{
    $stmt = db()->prepare("
        SELECT c.id, c.type, c.name, c.owner_id, cm.role
        FROM chats c JOIN chat_members cm ON cm.chat_id = c.id
        WHERE c.id = ? AND cm.user_id = ?
    ");
    $stmt->execute([$chatId, $forUserId]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$row) throw new RuntimeException('Чат недоступен');

    $name = $row['name'];
    if ($row['type'] === 'dm') {
        $other = dmPartner($chatId, $forUserId);
        $name = $other['username'] ?? 'DM';
        $row['partner_id'] = $other['id'] ?? null;
    }

    return [
        'id'        => (int)$row['id'],
        'type'      => $row['type'],
        'name'      => $name,
        'owner_id'  => $row['owner_id'] !== null ? (int)$row['owner_id'] : null,
        'myRole'    => $row['role'],
        'partner_id'=> $row['partner_id'] ?? null,
    ];
}

function broadcastOnline(): void
{
    global $clients;
    // userId => [username]
    $online = [];
    foreach ($clients as $c) {
        if ($c['userId']) $online[$c['userId']] = $c['username'];
    }
    $payload = json_encode([
        'type'   => 'online',
        'users'  => array_map(
            fn($id, $name) => ['id' => $id, 'username' => $name],
            array_keys($online),
            array_values($online)
        ),
    ], JSON_UNESCAPED_UNICODE);

    foreach ($clients as $c) {
        if (!$c['sock']) continue;
        sendFrame($c['sock'], $payload);
    }
}

function handleDisconnect(int $sid): void
{
    global $clients, $handshakes, $userSockets;

    if (isset($clients[$sid])) {
        $c = $clients[$sid];
        @socket_close($c['sock']);

        if ($c['userId'] && isset($userSockets[$c['userId']])) {
            $userSockets[$c['userId']] = array_values(array_filter(
                $userSockets[$c['userId']], fn($x) => $x !== $sid
            ));
            if (empty($userSockets[$c['userId']])) unset($userSockets[$c['userId']]);
        }
        unset($clients[$sid]);
        broadcastOnline();
    }

    if (isset($handshakes[$sid])) {
        @socket_close($handshakes[$sid]['sock']);
        unset($handshakes[$sid]);
    }
}