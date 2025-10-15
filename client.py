# client.py

import socket
from constants import SERVER_HOST, SERVER_PORT
from transport import TransportPacket

def main():
    # define the target server address
    server_address = ('127.0.0.1', SERVER_PORT)

    # create a new UDP socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        # define the message and encode it into bytes
        message = "hello, this is a test packet!"
        payload = message.encode('utf-8')

        # create a packet object with the payload
        packet_to_send = TransportPacket(seq=1, payload=payload)
        
        print("Packet to send:")
        print(packet_to_send)

        # serialize the packet object into bytes
        packed_data = packet_to_send.pack()

        # send the bytes to the server's address
        sock.sendto(packed_data, server_address)
        
        print(f"\nSent {len(packed_data)} bytes to {server_address}")

if __name__ == "__main__":
    main()