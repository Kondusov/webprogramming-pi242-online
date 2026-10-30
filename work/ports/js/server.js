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
    console.log(`Пользователь подключился: ${socket.id}`);

    // Слушаем кастомное событие 'chat message' от конкретного клиента
    socket.on('chat message', (msg) => {
        console.log(`Получено сообщение: ${msg}`);
        
        // Рассылаем это сообщение ВСЕМ подключенным пользователям (включая отправителя)
        io.emit('chat message', msg);
    });

    // Слушаем системное событие отключения пользователя
    socket.on('disconnect', () => {
        console.log(`Пользователь отключился: ${socket.id}`);
    });
});

// Запускаем сервер на 3000 порту
const PORT = 3000;
server.listen(PORT, () => {
    console.log(`Сервер запущен на http://localhost:${PORT}`);
});
