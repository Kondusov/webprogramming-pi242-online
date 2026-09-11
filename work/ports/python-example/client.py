import socket

def send_message(port, message):
    # Создаем TCP-сокет клиента
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Подключаемся к локальному серверу на выбранный порт
        client.connect(('127.0.0.1', port))
        
        # Отправляем сообщение
        client.send(message.encode('utf-8'))
        
        # Получаем ответ
        response = client.recv(1024).decode('utf-8')
        print(f"📥 Ответ от сервера: {response}\n")
    except ConnectionRefusedError:
        print(f"❌ Ошибка: Не удалось подключиться к порту {port}. Сервер запущен?\n")
    finally:
        client.close()

if __name__ == "__main__":
    print("=== Демонстрация работы портов ===")
    while True:
        text = input("Введите текст для отправки (или 'exit' для выхода): ")
        if text.lower() == 'exit':
            break
            
        print("Куда отправить?")
        print("1 — На порт 5001 (Вернет текст как есть)")
        print("2 — На порт 5002 (Перевернет текст задом наперед)")
        choice = input("Ваш выбор (1 или 2): ")
        
        if choice == '1':
            send_message(5001, text)
        elif choice == '2':
            send_message(5002, text)
        else:
            print("Неверный выбор, попробуйте снова.\n")
