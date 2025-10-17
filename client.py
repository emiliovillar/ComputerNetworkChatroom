import socket
import threading
from constants import SERVER_HOST, SERVER_PORT
from transport import TransportPacket

def receive_messages(sock):
    while True:
        try:
            data, _ = sock.recvfrom(4096)
            msg = data.decode('utf-8', errors='ignore')
            print(f"\n{msg}\n> ", end="", flush=True)
        except:
            break

def main():
    server_address = (SERVER_HOST, SERVER_PORT)
    seq = 1

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"✅ Connected to server at {SERVER_HOST}:{SERVER_PORT}")
    print("Type: JOIN <room>, LEAVE <room>, MSG <room> <text>, SHUTDOWN, or exit\n")

    # Background thread to listen for incoming messages
    threading.Thread(target=receive_messages, args=(sock,), daemon=True).start()

    while True:
        user_input = input("> ").strip()
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Client exiting.")
            break

        payload = user_input.encode('utf-8')
        packet = TransportPacket(seq=seq, payload=payload)
        sock.sendto(packet.pack(), server_address)
        seq += 1

    sock.close()

if __name__ == "__main__":
    main()
