# server.py

import socket
from constants import SERVER_HOST, SERVER_PORT, BUFFER_SIZE
from transport import TransportPacket

def main():
    # create a new UDP socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        # bind the socket to a public host and port
        sock.bind((SERVER_HOST, SERVER_PORT))
        print(f"✅ Server listening on {SERVER_HOST}:{SERVER_PORT}")

        print("\nWaiting to receive a packet...")
        
        # block execution until data is received
        # data contains the bytes, addr contains the source (ip, port)
        data, addr = sock.recvfrom(BUFFER_SIZE)
        
        print(f"Received {len(data)} bytes from {addr}")

        # attempt to parse the received bytes into a packet object
        try:
            received_packet = TransportPacket.unpack(data)
            print("Successfully unpacked packet:")
            print(received_packet)
        except ValueError as e:
            print(f"Error unpacking packet: {e}")

    print("\nServer shutting down.")

if __name__ == "__main__":
    main()