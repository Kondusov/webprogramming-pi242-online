<?php
/**
 * Обёртка над SQLite через PDO.
 */

function db(): PDO
{
    static $pdo = null;
    if ($pdo !== null) return $pdo;

    $dir = __DIR__ . '/../data';
    if (!is_dir($dir)) mkdir($dir, 0777, true);

    $pdo = new PDO('sqlite:' . $dir . '/chat.db');
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $pdo->exec('PRAGMA journal_mode = WAL');
    $pdo->exec('PRAGMA foreign_keys = ON');

    migrate($pdo);
    return $pdo;
}

function migrate(PDO $db): void
{
    $db->exec("
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT    NOT NULL,          -- 'group' | 'channel' | 'dm'
            name        TEXT,                      -- для group/channel
            owner_id    INTEGER,                   -- для group/channel
            created_at  TEXT    NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS chat_members (
            chat_id   INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            role      TEXT    NOT NULL DEFAULT 'member',  -- 'owner' | 'member'
            joined_at TEXT    NOT NULL,
            PRIMARY KEY (chat_id, user_id),
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id   INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            text      TEXT    NOT NULL,
            time      TEXT    NOT NULL,
            deleted   INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_chat_time
            ON messages(chat_id, id DESC);

        CREATE TABLE IF NOT EXISTS dm_pairs (
            chat_id  INTEGER PRIMARY KEY,
            user_a   INTEGER NOT NULL,
            user_b   INTEGER NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
            UNIQUE (user_a, user_b)
        );
    ");
}