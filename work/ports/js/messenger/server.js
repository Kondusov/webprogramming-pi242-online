// Импортируем необходимые модули
const express = require('express');
const http = require('http');
const { Server } = require('socket.io');

const app = express();
const server = http.createServer(app); // Создаем HTTP-сервер на базе Express

// Инициализируем Socket.io, передавая ему наш HTTP-сервер
const io = new Server(server);

// Отдаем статическую HTML-страницу (клиентскую часть) при обращении к корню сайта
app.get('/', (req, res) => {
    res.sendFile(__dirname + '/index.html');
});

// Слушаем событие 'connection' — оно срабатывает каждый раз, когда к нам подключается новый пользователь
io.on('connection', (socket) => {
    const username = socket.handshake.auth.username; // Получаем имя

    socket.on('chat message', (msg) => {
        console.log(msg);
        // Рассылаем объект: имя + текст
        io.emit('chat message', { username, text: msg });
    });
    // Отправляет сообщение ВСЕМ, кроме самого подключившегося (broadcast)
    socket.broadcast.emit('system message', `${username} вошел в чат`);

    socket.on('disconnect', () => {
        io.emit('system message', `${username} покинул чат`);
    });
});

// Запускаем сервер на 3000 порту
const PORT = 3000;
server.listen(PORT, () => {
    console.log(`Сервер запущен на http://localhost:${PORT}`);
});
