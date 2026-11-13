const congratulation = document.getElementById('congratulation');
const table = document.querySelector('table');
let combinations = [
    [1,2,3], [4,5,6],[7,8,9],
    [1,4,7], [2,5,8],[3,6,9],
    [1,5,9], [3,5,7]
];


let myRole = null;       // Кем играем мы ('X' или 'O'), назначит сервер
let switcher = 'X';      // Чей сейчас ход
let isGameOver = false;
let currentCombinationsX = [];
let currentCombinationsO = [];

// 1. Подключаемся к локальному WebSocket-серверу
const socket = new WebSocket('ws://localhost:8080');

// 2. Слушаем команды от сервера
socket.addEventListener('message', (event) => {
  const data = JSON.parse(event.data);

  // Сервер сообщает нам нашу роль при входе
  if (data.type === 'init') {
    myRole = data.role;
    congratulation.textContent = `Вы играете за ${myRole}. Сейчас ход: ${switcher}`;
  }

  // Сервер прислал ход (наш или соперника)
  if (data.type === 'move') {
    applyMove(data.cellId, data.player);
  }
});

// 3. Обработка клика по таблице (только отправка на сервер)
table.addEventListener('click', (event) => {
  const cell = event.target;
  const cellId = cell.getAttribute('id');

  // Защита: клик не по ячейке, игра окончена, не назначена роль, не наш ход или клетка занята
  if (!cellId || isGameOver || !myRole || switcher !== myRole || cell.textContent !== '') {
    return;
  }

  // Отправляем координаты хода на сервер
  socket.send(JSON.stringify({
    type: 'move',
    cellId: cellId,
    player: myRole
  }));
});

// 4. Функция применения хода на доске (вызывается для обоих игроков)
function applyMove(cellId, player) {
  const cell = document.getElementById(cellId);
  if (!cell || cell.textContent !== '') return;

  // Ставим символ в ячейку
  cell.textContent = player;
  const numId = Number(cellId);

  // Записываем ход в массив нужного игрока
  const currentMoves = player === 'O' ? currentCombinationsO : currentCombinationsX;
  currentMoves.push(numId);

  // Исправленная проверка победы: проверяем, есть ли ВСЕ 3 числа комбинации в ходах игрока
  const isWin = combinations.some((combo) =>
    combo.every((num) => currentMoves.includes(num))
  );

  if (isWin) {
    congratulation.textContent = `Победил ${player}!`;
    isGameOver = true;
    return;
  }

  // Проверка на ничью
  if (currentCombinationsX.length + currentCombinationsO.length === 9) {
    congratulation.textContent = 'Ничья!';
    isGameOver = true;
    return;
  }

  // Передаем ход следующему игроку
  switcher = player === 'X' ? 'O' : 'X';
  congratulation.textContent = `Вы: ${myRole}. Сейчас ход: ${switcher}`;
}
