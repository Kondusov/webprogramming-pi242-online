from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask("API_Server")
# Явно разрешаем запросы со всех источников для демонстрации
CORS(app, resources={r"/*": {"origins": "*"}}) 

@app.route('/api', methods=['POST'])
def api_handler():
    data = request.get_json() or {}
    user_text = data.get('message', '')
    
    # Извлекаем динамический порт клиента
    client_port = request.environ.get('REMOTE_PORT', 'Не определен')
    print(f"[ЛОГ 5002] Получен запрос с клиентского порта {client_port}")
    
    return jsonify({
        "reversed": user_text[::-1],
        "client_port": client_port
    })

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5002)