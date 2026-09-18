<?php
/**
 * WebSocket-сервер для чата.
 * Запуск: php ws-server.php
 */

$host = '0.0.0.0';
$port = 8080;

$server = socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
if ($server === false) {
    die("socket_create: " . socket_strerror(socket_last_error()) . "\n");
}
socket_set_option($server, SOL_SOCKET, SO_REUSEADDR, 1);
if (!socket_bind($server, $host, $port)) {
    die("socket_bind: " . socket_strerror(socket_last_error($server)) . "\n");
}
if (!socket_listen($server, 10)) {
    die("socket_listen: " . socket_strerror(socket_last_error($server)) . "\n");
}
socket_set_nonblock($server);

echo "WebSocket-сервер запущен на ws://$host:$port\n";

$clients    = []; // id => ['sock' => socket, 'handshaked' => bool]
$handshakes = []; // id => socket

function sockId($sock): int {
    return is_object($sock) ? spl_object_id($sock) : (int)$sock;
}

while (true) {
    // ВАЖНО: в $read должны быть и клиенты, и те, кто ещё не прошёл handshake
    $read = [$server];
    foreach ($clients as $c)    $read[] = $c['sock'];
    foreach ($handshakes as $h) $read[] = $h;

    $write = $except = null;

    if (@socket_select($read, $write, $except, 1) === false) {
        continue;
    }

    // --- Новое подключение ---
    if (in_array($server, $read, true)) {
        $newClient = @socket_accept($server);
        if ($newClient !== false) {
            socket_set_nonblock($newClient);
            $handshakes[sockId($newClient)] = $newClient;
            echo "[+] Новое соединение\n";
        }
        $k = array_search($server, $read, true);
        if ($k !== false) unset($read[$k]);
    }

    // --- Обработка клиентов ---
    foreach ($read as $sock) {
        $id = sockId($sock);

        $data = @socket_read($sock, 8192, PHP_BINARY_READ);

        if ($data === false) {
            // Реальное отключение
            echo "[-] #$id: socket_read вернул false\n";
            disconnectClient($id);
            continue;
        }
        if ($data === '') {
            // Данных пока нет — нормальная ситуация в неблокирующем режиме
            continue;
        }

        // --- Handshake ---
        if (isset($handshakes[$id])) {
            echo "[~] #$id: получено " . strlen($data) . " байт заголовков\n";

            // Если заголовки пришли не целиком — накапливаем
            static $buf = [];
            $buf[$id] = ($buf[$id] ?? '') . $data;

            if (strpos($buf[$id], "\r\n\r\n") === false) {
                // Ещё не всё пришло
                continue;
            }

            $headers = $buf[$id];
            unset($buf[$id]);

            if (performHandshake($sock, $headers)) {
                unset($handshakes[$id]);
                $clients[$id] = ['sock' => $sock, 'handshaked' => true];
                echo "[✓] Handshake завершён для #$id\n";

                sendTo($sock, json_encode([
                    'type' => 'system',
                    'text' => 'Вы подключились к чату',
                ]));
                broadcast($clients, json_encode([
                    'type' => 'system',
                    'text' => "Пользователь #$id вошёл в чат",
                ]));
            } else {
                echo "[x] Handshake не удался для #$id\n";
                disconnectClient($id);
            }
            continue;
        }

        // --- Обычное сообщение ---
        if (isset($clients[$id])) {
            $message = decodeFrame($data);
            if ($message === null) continue;

            $payload = json_decode($message, true);
            if (!is_array($payload)) continue;

            $out = json_encode([
                'type' => 'message',
                'user' => $id,
                'text' => htmlspecialchars($payload['text'] ?? '', ENT_QUOTES, 'UTF-8'),
                'time' => date('H:i:s'),
            ]);

            echo "[msg] #$id: " . ($payload['text'] ?? '') . "\n";
            broadcast($clients, $out);
        }
    }
}

/* ==================== Функции ==================== */

function performHandshake($client, string $request): bool
{
    if (!preg_match('/Sec-WebSocket-Key:\s*(.+)\r\n/i', $request, $m)) {
        echo "    !! Sec-WebSocket-Key не найден\n";
        return false;
    }
    $key = trim($m[1]);
    $accept = base64_encode(sha1($key . '258EAFA5-E914-47DA-95CA-C5AB0DC85B11', true));

    $response =
        "HTTP/1.1 101 Switching Protocols\r\n" .
        "Upgrade: websocket\r\n" .
        "Connection: Upgrade\r\n" .
        "Sec-WebSocket-Accept: $accept\r\n\r\n";

    $written = @socket_write($client, $response, strlen($response));
    echo "    -> отправлен handshake (" . $written . " байт)\n";
    return $written !== false;
}

function decodeFrame(string $data): ?string
{
    if (strlen($data) < 2) return null;

    $bytes = unpack('C2', $data);
    $opcode = $bytes[1] & 0x0F;
    $masked = ($bytes[2] & 0x80) !== 0;
    $length = $bytes[2] & 0x7F;
    $offset = 2;

    if ($opcode === 0x8) return null; // close

    if ($length === 126) {
        $ext = unpack('n', substr($data, $offset, 2));
        $length = $ext[1];
        $offset += 2;
    } elseif ($length === 127) {
        $ext = unpack('J', substr($data, $offset, 8));
        $length = $ext[1];
        $offset += 8;
    }

    $mask = '';
    if ($masked) {
        $mask = substr($data, $offset, 4);
        $offset += 4;
    }

    $payload = substr($data, $offset, $length);

    if ($masked) {
        $unmasked = '';
        for ($i = 0; $i < $length; $i++) {
            $unmasked .= $payload[$i] ^ $mask[$i % 4];
        }
        $payload = $unmasked;
    }

    return $payload;
}

function encodeFrame(string $text): string
{
    $length = strlen($text);
    $frame = chr(0x81);

    if ($length <= 125) {
        $frame .= chr($length);
    } elseif ($length <= 65535) {
        $frame .= chr(126) . pack('n', $length);
    } else {
        $frame .= chr(127) . pack('J', $length);
    }

    return $frame . $text;
}

function sendTo($client, string $text): void
{
    $frame = encodeFrame($text);
    @socket_write($client, $frame, strlen($frame));
}

function broadcast(array $clients, string $text): void
{
    foreach ($clients as $c) {
        sendTo($c['sock'], $text);
    }
}

function disconnectClient(int $id): void
{
    global $clients, $handshakes;

    if (isset($clients[$id])) {
        @socket_close($clients[$id]['sock']);
        unset($clients[$id]);
        echo "[-] Клиент #$id отключился\n";

        broadcast($clients, json_encode([
            'type' => 'system',
            'text' => "Пользователь #$id покинул чат",
        ]));
    }

    if (isset($handshakes[$id])) {
        @socket_close($handshakes[$id]);
        unset($handshakes[$id]);
    }
}