import socket

HOST = "127.0.0.1"
PORT = 5000

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((HOST, PORT))

try:
    while True:
        message = input("Введите сообщение (или 'exit' для выхода): ")
        if message.lower() == "exit":
            break
        client_socket.sendall(message.encode("utf-8"))
        data = client_socket.recv(1024)
        print(f"Ответ сервера: {data.decode('utf-8')}")
finally:
    client_socket.close()
    print("Соединение закрыто")