<?php
// Параметры подключения
$host = '127.0.0.1';
$port = 8080;

// Сообщение для отправки (можно передать аргументом)
$message = $argv[1] ?? 'Привет, сервер!';

// Создаём TCP-сокет
$socket = socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
if ($socket === false) {
    die("Не удалось создать сокет: " . socket_strerror(socket_last_error()) . "\n");
}

// Подключаемся к серверу
if (!socket_connect($socket, $host, $port)) {
    die("Не удалось подключиться к $host:$port: " . socket_strerror(socket_last_error($socket)) . "\n");
}

echo "Подключено к $host:$port\n";

// Отправляем сообщение
socket_write($socket, $message, strlen($message));
echo "Отправлено: $message\n";

// Читаем ответ сервера
$response = '';
while ($chunk = socket_read($socket, 1024, PHP_BINARY_READ)) {
    $response .= $chunk;
    // Если сервер закрыл соединение — выходим
    if (strlen($chunk) < 1024) {
        break;
    }
}

echo "Ответ сервера: $response";

// Закрываем сокет
socket_close($socket);