<?php
/**
 * Низкоуровневый WebSocket: handshake, decode/encode frame, ping.
 */

function performHandshake($client, string $request): bool
{
    if (!preg_match('/Sec-WebSocket-Key:\s*(.+)\r\n/i', $request, $m)) return false;
    $accept = base64_encode(sha1(trim($m[1]) . '258EAFA5-E914-47DA-95CA-C5AB0DC85B11', true));
    $resp =
        "HTTP/1.1 101 Switching Protocols\r\n" .
        "Upgrade: websocket\r\n" .
        "Connection: Upgrade\r\n" .
        "Sec-WebSocket-Accept: $accept\r\n\r\n";
    return @socket_write($client, $resp, strlen($resp)) !== false;
}

function decodeFrame(string $data): ?array
{
    if (strlen($data) < 2) return null;

    $b = unpack('C2', $data);
    $opcode = $b[1] & 0x0F;
    $masked = ($b[2] & 0x80) !== 0;
    $length = $b[2] & 0x7F;
    $offset = 2;

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
    if ($masked && strlen($mask) === 4) {
        $un = '';
        for ($i = 0; $i < $length; $i++) $un .= $payload[$i] ^ $mask[$i % 4];
        $payload = $un;
    }

    return ['opcode' => $opcode, 'payload' => $payload];
}

function encodeFrame(string $text, int $opcode = 0x1): string
{
    $length = strlen($text);
    $frame = chr(0x80 | $opcode);

    if ($length <= 125) {
        $frame .= chr($length);
    } elseif ($length <= 65535) {
        $frame .= chr(126) . pack('n', $length);
    } else {
        $frame .= chr(127) . pack('J', $length);
    }
    return $frame . $text;
}

function sendFrame($client, string $text, int $opcode = 0x1): void
{
    $frame = encodeFrame($text, $opcode);
    @socket_write($client, $frame, strlen($frame));
}

function sendJson($client, array $payload): void
{
    sendFrame($client, json_encode($payload, JSON_UNESCAPED_UNICODE), 0x1);
}

function sendPing($client): void
{
    sendFrame($client, '', 0x9);
}