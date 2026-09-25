<?php
require_once __DIR__ . '/db.php';

const TOKEN_SECRET = 'change-me-to-a-long-random-string';

function register(string $username, string $password): array
{
    $username = trim($username);
    if (!preg_match('/^[\p{L}\p{N}_\- ]{3,32}$/u', $username)) {
        throw new RuntimeException('Имя: 3–32 символа, буквы/цифры/пробел');
    }
    if (mb_strlen($password) < 6) {
        throw new RuntimeException('Пароль минимум 6 символов');
    }

    $db = db();
    $stmt = $db->prepare("SELECT 1 FROM users WHERE username = ?");
    $stmt->execute([$username]);
    if ($stmt->fetch()) throw new RuntimeException('Имя уже занято');

    $hash = password_hash($password, PASSWORD_DEFAULT);
    $stmt = $db->prepare(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)"
    );
    $stmt->execute([$username, $hash, date('c')]);

    $userId = (int)$db->lastInsertId();
    return ['id' => $userId, 'username' => $username, 'token' => issueToken($userId)];
}

function login(string $username, string $password): array
{
    $db = db();
    $stmt = $db->prepare("SELECT * FROM users WHERE username = ?");
    $stmt->execute([trim($username)]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$user || !password_verify($password, $user['password_hash'])) {
        throw new RuntimeException('Неверное имя или пароль');
    }
    return [
        'id'       => (int)$user['id'],
        'username' => $user['username'],
        'token'    => issueToken((int)$user['id']),
    ];
}

function issueToken(int $userId): string
{
    $payload = base64_encode(json_encode([
        'uid' => $userId,
        'exp' => time() + 86400 * 30,
    ]));
    $sig = hash_hmac('sha256', $payload, TOKEN_SECRET);
    return $payload . '.' . $sig;
}

function verifyToken(string $token): ?int
{
    $parts = explode('.', $token);
    if (count($parts) !== 2) return null;

    [$payload, $sig] = $parts;
    $expected = hash_hmac('sha256', $payload, TOKEN_SECRET);
    if (!hash_equals($expected, $sig)) return null;

    $data = json_decode(base64_decode($payload), true);
    if (!is_array($data) || ($data['exp'] ?? 0) < time()) return null;

    return (int)($data['uid'] ?? 0) ?: null;
}

function userById(int $id): ?array
{
    $stmt = db()->prepare("SELECT id, username FROM users WHERE id = ?");
    $stmt->execute([$id]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    return $row ?: null;
}