from flask import Flask, render_template_string

app = Flask("UI_Server")

HTML_INTERFACE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Демонстрация работы портов</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f4f6f9; color: #333; padding: 30px; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 25px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        h2 { color: #2c3e50; text-align: center; }
        .port-badge { background: #3498db; color: white; padding: 3px 8px; border-radius: 4px; font-family: monospace; }
        .port-badge.api { background: #e67e22; }
        .card { border: 1px solid #ddd; padding: 15px; margin: 15px 0; border-radius: 6px; background: #fafafa; }
        input[type="text"] { width: 100%; padding: 10px; margin: 10px 0; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; }
        button { background: #2ecc71; color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px; font-size: 16px; width: 100%; }
        button:hover { background: #27ae60; }
        .log-box { font-family: monospace; background: #2c3e50; color: #1abc9c; padding: 15px; border-radius: 4px; overflow-x: auto; min-height: 80px; margin-top: 15px; white-space: pre-line;}
    </style>
</head>
<body>
<div class="container">
    <h2>🔌 Демонстрация работы портов</h2>
    
    <div class="card">
        Вы открыли эту страницу на сервере: <span class="port-badge">Порт 5001 (Интерфейс)</span>
    </div>

    <div class="card">
        <h3>Отправить запрос на <span class="port-badge api">Порт 5002 (API)</span></h3>
        <input type="text" id="textInput" value="Привет, Сеть!" placeholder="Введите сообщение...">
        <button onclick="sendRequest()">Отправить AJAX-запрос</button>
    </div>

    <div class="card">
        <strong>Что произошло (Лог в реальном времени):</strong>
        <div id="log" class="log-box">Ожидание отправки запроса...</div>
    </div>
</div>

<script>
function sendRequest() {
    const text = document.getElementById('textInput').value;
    const logDiv = document.getElementById('log');
    
    logDiv.innerText = "Отполнение запроса на http://127.0.0 ...\\n";

    fetch('http://127.0.0', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
    })
    .then(response => {
        if (!response.ok) throw new Error('Ошибка сервера');
        return response.json();
    })
    .then(data => {
        logDiv.innerHTML = `
        ✅ <b>Успешно доставлено на Порт 5002!</b>
        
        <b>Данные:</b> сервер перевернул текст -> "${data.reversed}"
        <b>Магия портов:</b> Браузер выделил временный случайный <b>клиентский порт: ${data.client_port}</b>!
        `;
    })
    .catch(error => {
        console.error(error);
        logDiv.innerText = "❌ Ошибка соединения. Проверьте консоль браузера (F12) или терминал API-сервера.";
    });
}
</script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_INTERFACE)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001)
