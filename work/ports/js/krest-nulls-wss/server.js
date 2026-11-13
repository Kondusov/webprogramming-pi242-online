import { WebSocketServer } from 'ws';

const wss = new WebSocketServer({ port: 8080 });
let players = [];

wss.on('connection', (ws) => {
  // Назначаем роль: первому игроку 'X', второму 'O'
  const role = players.length === 0 ? 'X' : 'O';
  players.push(ws);

  // Отправляем игроку его роль
  ws.send(JSON.stringify({ type: 'init', role }));

  // Когда кто-то делает ход, рассылаем его всем подключенным игрокам
  ws.on('message', (message) => {
    const data = message.toString();
    players.forEach((client) => {
      if (client.readyState === 1) { // 1 означает WebSocket.OPEN
        client.send(data);
      }
    });
  });

  // Очищаем список при выходе игрока
  ws.on('close', () => {
    players = players.filter((client) => client !== ws);
  });
});

console.log('Сервер для крестиков-ноликов запущен на ws://localhost:8080');
