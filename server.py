import socket
from collections import defaultdict
from constants import SERVER_BIND, SERVER_PORT
from transport import TransportPacket

def main():
    # Track room membership: room_name -> set of (ip, port)
    rooms = defaultdict(set)

    # Create UDP socket and bind
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((SERVER_BIND, SERVER_PORT))
        print(f"✅ Server listening on {SERVER_BIND}:{SERVER_PORT}\n")

        while True:
            try:
                print("Waiting to receive a packet...")
                data, addr = sock.recvfrom(4096)
                packet = TransportPacket.unpack(data)
                msg = packet.payload.decode('utf-8').strip()

                print(f"Received from {addr}: {msg}")

                # Parse command
                parts = msg.split(" ", 2)
                cmd = parts[0].upper()

                if cmd == "JOIN" and len(parts) >= 2:
                    room = parts[1]
                    rooms[room].add(addr)
                    notice = f"[presence] {addr} joined {room}"
                    print(notice)
                    broadcast(sock, rooms[room], notice.encode(), exclude=None)

                elif cmd == "LEAVE" and len(parts) >= 2:
                    room = parts[1]
                    if addr in rooms[room]:
                        rooms[room].remove(addr)
                        notice = f"[presence] {addr} left {room}"
                        print(notice)
                        broadcast(sock, rooms[room], notice.encode(), exclude=None)

                elif cmd == "MSG" and len(parts) >= 3:
                    room, text = parts[1], parts[2]
                    if addr in rooms[room]:
                        full_msg = f"[{room}] {addr}: {text}"
                        broadcast(sock, rooms[room], full_msg.encode(), exclude=None)
                    else:
                        warn = f"You are not in {room}. Use JOIN {room} first."
                        sock.sendto(warn.encode(), addr)

                elif cmd == "SHUTDOWN":
                    print("🛑 Shutdown command received. Exiting server.")
                    break

                else:
                    sock.sendto(b"Invalid command.", addr)

            except KeyboardInterrupt:
                print("\n🛑 Server interrupted manually.")
                break
            except Exception as e:
                print(f"Error: {e}")

def broadcast(sock, members, data, exclude=None):
    """Send data to all members in a room."""
    for m in members:
        if exclude and m == exclude:
            continue
        try:
            sock.sendto(data, m)
        except Exception as e:
            print(f"Failed to send to {m}: {e}")

if __name__ == "__main__":
    main()
