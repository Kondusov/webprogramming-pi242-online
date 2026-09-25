<?php
require_once __DIR__ . '/db.php';

/* ---------- Создание ---------- */

function createGroup(int $ownerId, string $name): int
{
    return createNamedChat($ownerId, $name, 'group');
}

function createChannel(int $ownerId, string $name): int
{
    return createNamedChat($ownerId, $name, 'channel');
}

function createNamedChat(int $ownerId, string $name, string $type): int
{
    $name = trim($name);
    if (mb_strlen($name) < 2 || mb_strlen($name) > 64) {
        throw new RuntimeException('Название: 2–64 символа');
    }

    $db = db();
    $db->beginTransaction();
    try {
        $stmt = $db->prepare(
            "INSERT INTO chats (type, name, owner_id, created_at) VALUES (?, ?, ?, ?)"
        );
        $stmt->execute([$type, $name, $ownerId, date('c')]);
        $chatId = (int)$db->lastInsertId();

        $stmt = $db->prepare(
            "INSERT INTO chat_members (chat_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)"
        );
        $stmt->execute([$chatId, $ownerId, date('c')]);

        $db->commit();
        return $chatId;
    } catch (Throwable $e) {
        $db->rollBack();
        throw $e;
    }
}

/**
 * Приватный чат 1-на-1. Если уже существует — возвращает его id.
 */
function getOrCreateDm(int $userA, int $userB): int
{
    if ($userA === $userB) throw new RuntimeException('Нельзя DM с самим собой');
    [$a, $b] = $userA < $userB ? [$userA, $userB] : [$userB, $userA];

    $db = db();
    $stmt = $db->prepare("SELECT chat_id FROM dm_pairs WHERE user_a = ? AND user_b = ?");
    $stmt->execute([$a, $b]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    if ($row) return (int)$row['chat_id'];

    $db->beginTransaction();
    try {
        $stmt = $db->prepare(
            "INSERT INTO chats (type, name, owner_id, created_at) VALUES ('dm', NULL, NULL, ?)"
        );
        $stmt->execute([date('c')]);
        $chatId = (int)$db->lastInsertId();

        $stmt = $db->prepare(
            "INSERT INTO chat_members (chat_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)"
        );
        $stmt->execute([$chatId, $a, date('c')]);
        $stmt->execute([$chatId, $b, date('c')]);

        $stmt = $db->prepare("INSERT INTO dm_pairs (chat_id, user_a, user_b) VALUES (?, ?, ?)");
        $stmt->execute([$chatId, $a, $b]);

        $db->commit();
        return $chatId;
    } catch (Throwable $e) {
        $db->rollBack();
        throw $e;
    }
}

/* ---------- Чтение ---------- */

function listChatsForUser(int $userId): array
{
    $stmt = db()->prepare("
        SELECT c.id, c.type, c.name, c.owner_id,
               cm.role,
               (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id AND m.deleted = 0) AS messages_count
        FROM chats c
        JOIN chat_members cm ON cm.chat_id = c.id
        WHERE cm.user_id = ?
        ORDER BY c.id DESC
    ");
    $stmt->execute([$userId]);

    $chats = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Для DM добавим имя собеседника
    foreach ($chats as &$c) {
        if ($c['type'] === 'dm') {
            $other = dmPartner((int)$c['id'], $userId);
            $c['name'] = $other['username'] ?? 'DM';
            $c['partner_id'] = $other['id'] ?? null;
        }
        $c['id'] = (int)$c['id'];
        $c['owner_id'] = $c['owner_id'] !== null ? (int)$c['owner_id'] : null;
    }
    return $chats;
}

function dmPartner(int $chatId, int $userId): ?array
{
    $stmt = db()->prepare("
        SELECT u.id, u.username
        FROM chat_members cm
        JOIN users u ON u.id = cm.user_id
        WHERE cm.chat_id = ? AND cm.user_id != ?
        LIMIT 1
    ");
    $stmt->execute([$chatId, $userId]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ? ['id' => (int)$row['id'], 'username' => $row['username']] : null;
}

function chatMembers(int $chatId): array
{
    $stmt = db()->prepare("
        SELECT u.id, u.username, cm.role
        FROM chat_members cm
        JOIN users u ON u.id = cm.user_id
        WHERE cm.chat_id = ?
        ORDER BY cm.role DESC, u.username
    ");
    $stmt->execute([$chatId]);
    return array_map(fn($r) => [
        'id'       => (int)$r['id'],
        'username' => $r['username'],
        'role'     => $r['role'],
    ], $stmt->fetchAll(PDO::FETCH_ASSOC));
}

function isMember(int $chatId, int $userId): bool
{
    $stmt = db()->prepare("SELECT 1 FROM chat_members WHERE chat_id = ? AND user_id = ?");
    $stmt->execute([$chatId, $userId]);
    return (bool)$stmt->fetch();
}

function isOwner(int $chatId, int $userId): bool
{
    $stmt = db()->prepare("SELECT 1 FROM chats WHERE id = ? AND owner_id = ?");
    $stmt->execute([$chatId, $userId]);
    return (bool)$stmt->fetch();
}

function chatInfo(int $chatId): ?array
{
    $stmt = db()->prepare("SELECT * FROM chats WHERE id = ?");
    $stmt->execute([$chatId]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ?: null;
}

function chatMembersIds(int $chatId): array
{
    $stmt = db()->prepare("SELECT user_id FROM chat_members WHERE chat_id = ?");
    $stmt->execute([$chatId]);
    return array_map(fn($r) => (int)$r['user_id'], $stmt->fetchAll(PDO::FETCH_ASSOC));
}

/* ---------- Сообщения ---------- */

function saveMessage(int $chatId, int $userId, string $text): array
{
    $text = trim($text);
    if ($text === '' || mb_strlen($text) > 4000) {
        throw new RuntimeException('Пустое или слишком длинное сообщение');
    }
    $safe = htmlspecialchars($text, ENT_QUOTES, 'UTF-8');
    $time = date('H:i:s');

    $db = db();
    $stmt = $db->prepare(
        "INSERT INTO messages (chat_id, user_id, text, time) VALUES (?, ?, ?, ?)"
    );
    $stmt->execute([$chatId, $userId, $safe, $time]);
    $id = (int)$db->lastInsertId();

    return ['id' => $id, 'text' => $safe, 'time' => $time];
}

function deleteMessage(int $messageId, int $byUserId): bool
{
    $db = db();
    $stmt = $db->prepare("SELECT chat_id, user_id FROM messages WHERE id = ?");
    $stmt->execute([$messageId]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$row) return false;

    $chatId = (int)$row['chat_id'];
    $authorId = (int)$row['user_id'];

    // Автор может удалить своё, владелец — любое
    if ($authorId !== $byUserId && !isOwner($chatId, $byUserId)) return false;

    $stmt = $db->prepare("UPDATE messages SET deleted = 1 WHERE id = ?");
    $stmt->execute([$messageId]);
    return true;
}

function messagesForChat(int $chatId, int $limit = 50, int $beforeId = 0): array
{
    $limit = max(1, min(200, $limit));
    if ($beforeId > 0) {
        $stmt = db()->prepare("
            SELECT m.id, m.user_id, u.username, m.text, m.time, m.deleted
            FROM messages m
            JOIN users u ON u.id = m.user_id
            WHERE m.chat_id = ? AND m.id < ?
            ORDER BY m.id DESC LIMIT ?
        ");
        $stmt->bindValue(1, $chatId, PDO::PARAM_INT);
        $stmt->bindValue(2, $beforeId, PDO::PARAM_INT);
        $stmt->bindValue(3, $limit, PDO::PARAM_INT);
    } else {
        $stmt = db()->prepare("
            SELECT m.id, m.user_id, u.username, m.text, m.time, m.deleted
            FROM messages m
            JOIN users u ON u.id = m.user_id
            WHERE m.chat_id = ?
            ORDER BY m.id DESC LIMIT ?
        ");
        $stmt->bindValue(1, $chatId, PDO::PARAM_INT);
        $stmt->bindValue(2, $limit, PDO::PARAM_INT);
    }
    $stmt->execute();
    $rows = array_reverse($stmt->fetchAll(PDO::FETCH_ASSOC));

    return array_map(fn($r) => [
        'id'       => (int)$r['id'],
        'userId'   => (int)$r['user_id'],
        'username' => $r['username'],
        'text'     => $r['deleted'] ? null : $r['text'],
        'time'     => $r['time'],
        'deleted'  => (bool)$r['deleted'],
    ], $rows);
}

/* ---------- Управление участниками ---------- */

function addMember(int $chatId, int $userId): void
{
    $stmt = db()->prepare(
        "INSERT OR IGNORE INTO chat_members (chat_id, user_id, role, joined_at)
         VALUES (?, ?, 'member', ?)"
    );
    $stmt->execute([$chatId, $userId, date('c')]);
}

function removeMember(int $chatId, int $userId, int $byUserId): bool
{
    if (!isOwner($chatId, $byUserId)) return false;
    if (isOwner($chatId, $userId)) return false; // владельца нельзя

    $stmt = db()->prepare("DELETE FROM chat_members WHERE chat_id = ? AND user_id = ?");
    $stmt->execute([$chatId, $userId]);
    return $stmt->rowCount() > 0;
}