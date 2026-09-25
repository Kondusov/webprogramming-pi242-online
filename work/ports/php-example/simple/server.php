<?php
// Параметры сервера
$host = '127.0.0.1';
$port = 8080;

// Создаём TCP-сокет
$socket = socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
if ($socket === false) {
    die("Не удалось создать сокет: " . socket_strerror(socket_last_error()) . "\n");
}

// Разрешаем повторное использование адреса
socket_set_option($socket, SOL_SOCKET, SO_REUSEADDR, 1);

// Привязываем сокет к адресу и порту
if (!socket_bind($socket, $host, $port)) {
    die("Не удалось привязать сокет: " . socket_strerror(socket_last_error($socket)) . "\n");
}

// Начинаем слушать входящие подключения
if (!socket_listen($socket, 5)) {
    die("Не удалось начать прослушивание: " . socket_strerror(socket_last_error($socket)) . "\n");
}

echo "Сервер запущен на $host:$port\n";
echo "Ожидание подключений...\n";

// Основной цикл сервера
while (true) {
    // Принимаем подключение клиента
    $client = socket_accept($socket);
    if ($client === false) {
        echo "Ошибка при принятии подключения: " . socket_strerror(socket_last_error($socket)) . "\n";
        continue;
    }

    // Читаем данные от клиента
    $input = socket_read($client, 1024, PHP_BINARY_READ);
    if ($input === false) {
        echo "Ошибка чтения: " . socket_strerror(socket_last_error($client)) . "\n";
        socket_close($client);
        continue;
    }

    $input = trim($input);
    echo "Получено от клиента: $input\n";

    // Формируем ответ
    $response = "Сервер получил ваше сообщение: \"$input\" в " . date('H:i:s') . "\n";

    // Отправляем ответ клиенту
    socket_write($client, $response, strlen($response));

    // Закрываем соединение с клиентом
    socket_close($client);
}

// Закрываем серверный сокет (недостижимо в данном цикле, но для полноты)
socket_close($socket);