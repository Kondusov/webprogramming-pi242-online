<?php
require_once __DIR__ . '/../server/auth.php';

header('Content-Type: application/json; charset=utf-8');

$action = $_GET['action'] ?? '';
$input  = json_decode(file_get_contents('php://input'), true) ?: [];

try {
    switch ($action) {
        case 'register':
            $result = register($input['username'] ?? '', $input['password'] ?? '');
            echo json_encode(['ok' => true] + $result, JSON_UNESCAPED_UNICODE);
            break;

        case 'login':
            $result = login($input['username'] ?? '', $input['password'] ?? '');
            echo json_encode(['ok' => true] + $result, JSON_UNESCAPED_UNICODE);
            break;

        case 'me':
            $token = $input['token'] ?? '';
            $uid = verifyToken($token);
            if (!$uid) throw new RuntimeException('Неверный токен');
            echo json_encode(['ok' => true, 'user' => userById($uid)], JSON_UNESCAPED_UNICODE);
            break;

        default:
            throw new RuntimeException('Неизвестное действие');
    }
} catch (Throwable $e) {
    http_response_code(400);
    echo json_encode(['ok' => false, 'error' => $e->getMessage()], JSON_UNESCAPED_UNICODE);
}