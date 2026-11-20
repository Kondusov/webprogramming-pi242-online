import socket
import requests
import json

HOST = "127.0.0.1"
PORT = 5000

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen(1)

print(f"Сервер запущен на {HOST}:{PORT}")

def check_spelling_ru(text: str) -> list[dict]:
    url = "https://speller.yandex.net/services/spellservice.json/checkText"
    response = requests.post(url, data={"text": text, "lang": "ru"}, timeout=10)
    response.raise_for_status()
    return response.json()
def fix_text_ru(text: str) -> str:
    errors = check_spelling_ru(text)
    # Идем с конца, чтобы при замене не сбивались индексы (pos) следующих слов
    for err in reversed(errors):
        if err.get("s"):  # Если есть варианты исправления
            pos = err["pos"]
            length = err["len"]
            best_suggestion = err["s"][0]
            text = text[:pos] + best_suggestion + text[pos + length:]
    return text
while True:
    conn, address = server_socket.accept()
    print(f"Подключение от {address}")
    
    with conn:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            message = data.decode("utf-8")
            print(f"Получено: {message}")

            response = fix_text_ru(message)
            # response = message.upper()
            conn.sendall(response.encode("utf-8"))
            print(f"Отправлено: {response}")

server_socket.close()