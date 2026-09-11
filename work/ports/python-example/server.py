import socket
import threading

# Функция для обработки конкретного клиента
def handle_client(client_socket, port_type):
    try:
        # Принимаем данные от клиента (до 1024 байт)
        data = client_socket.recv(1024).decode('utf-8')
        print(f"[ЛОГ] Получены данные на порту для {port_type}: '{data}'")
        
        # Логика обработки зависит от того, на какой порт пришли данные
        if port_type == "ОБЫЧНЫЙ ТЕКСТ":
            response = f"Сервер принял (Порт 5001): {data}"
        elif port_type == "ПЕРЕВЕРНУТЫЙ ТЕКСТ":
            response = f"Сервер перевернул (Порт 5002): {data[::-1]}"
        
        # Отправляем ответ обратно клиенту
        client_socket.send(response.encode('utf-8'))
    except Exception as e:
        print(f"Ошибка при обработке: {e}")
    finally:
        client_socket.close()

# Функция запуска слушателя на конкретном порту
def start_port_listener(port, port_type):
    # Создаем TCP-сокет
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Позволяет повторно использовать порт сразу после закрытия программы
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Привязываем сокет к локальному адресу и порту
    server.bind(('127.0.0.1', port))
    server.listen(5)
    print(f"🚀 Сервер запущен! Слушает порт {port} ({port_type})...")
    
    while True:
        client_sock, addr = server.accept()
        # Запускаем отдельный поток для каждого подключившегося клиента
        client_thread = threading.Thread(target=handle_client, args=(client_sock, port_type))
        client_thread.start()

if __name__ == "__main__":
    # Запускаем два разных порта в параллельных потоках
    thread_normal = threading.Thread(target=start_port_listener, args=(5001, "ОБЫЧНЫЙ ТЕКСТ"))
    thread_reverse = threading.Thread(target=start_port_listener, args=(5002, "ПЕРЕВЕРНУТЫЙ ТЕКСТ"))
    
    thread_normal.start()
    thread_reverse.start()
