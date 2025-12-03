import threading
import time
from collections import defaultdict
from constants import SERVER_BIND, SERVER_PORT
from transport import TransportConnection

# Global state
rooms = defaultdict(set)  # room_name -> set of connection objects
clients = {}  # (ip, port) -> TransportConnection
client_names = {}  # (ip, port) -> client_name
lock = threading.Lock()

def handle_client_message(conn, addr, data):
    """Handle incoming messages from a client."""
    try:
        msg = data.decode('utf-8').strip()
        print(f"[{addr}] Received: {msg}")
        
        # Parse command
        parts = msg.split(" ", 2)
        cmd = parts[0].upper()
        
        if cmd == "JOIN" and len(parts) >= 2:
            room = parts[1]
            with lock:
                rooms[room].add(conn)
            client_name = client_names.get(addr, str(addr))
            notice = f"[presence] {client_name} joined {room}"
            print(notice)
            broadcast_to_room(room, notice.encode())
            
        elif cmd == "LEAVE" and len(parts) >= 2:
            room = parts[1]
            with lock:
                if conn in rooms[room]:
                    rooms[room].remove(conn)
            client_name = client_names.get(addr, str(addr))
            notice = f"[presence] {client_name} left {room}"
            print(notice)
            broadcast_to_room(room, notice.encode())
            
        elif cmd == "MSG" and len(parts) >= 3:
            room, text = parts[1], parts[2]
            with lock:
                if conn in rooms[room]:
                    client_name = client_names.get(addr, str(addr))
                    full_msg = f"[{room}] {client_name}: {text}"
                    broadcast_to_room(room, full_msg.encode())
                else:
                    conn.send_msg(f"You are not in {room}. Use JOIN {room} first.".encode())
                    
        elif cmd == "NAME" and len(parts) >= 2:
            # Allow clients to set their display name
            name = parts[1]
            with lock:
                client_names[addr] = name
            conn.send_msg(f"Name set to: {name}".encode())
            
        elif cmd == "SHUTDOWN":
            print("[SHUTDOWN] Server shutdown command received.")
            conn.send_msg(b"Server shutting down...")
            
        else:
            conn.send_msg(b"Invalid command. Use: JOIN <room>, LEAVE <room>, MSG <room> <text>, NAME <name>")
            
    except Exception as e:
        print(f"Error handling message from {addr}: {e}")

def broadcast_to_room(room, data):
    """Send data to all clients in a room."""
    with lock:
        members = list(rooms[room])
    
    for conn in members:
        try:
            conn.send_msg(data)
        except Exception as e:
            print(f"Failed to send to client: {e}")

def create_client_handler(port_offset):
    """Create a connection handler for a new client on a unique port."""
    client_port = SERVER_PORT + port_offset
    
    def on_message(data):
        # Placeholder - will be replaced once connection is established
        pass
    
    conn = TransportConnection(
        local_addr=(SERVER_BIND, client_port),
        remote_addr=None,
        on_message=on_message,
        is_server=True
    )
    
    # Wait for connection
    while not conn.connected and conn.running:
        time.sleep(0.1)
    
    if conn.connected:
        print(f"[CONNECTED] Client from {conn.remote_addr} on port {client_port}")
        
        # Store connection
        with lock:
            clients[conn.remote_addr] = conn
        
        # Update callback to handle commands
        conn.on_message = lambda data: handle_client_message(conn, conn.remote_addr, data)
        
        # Keep connection alive
        while conn.running and conn.connected:
            time.sleep(0.5)
        
        # Clean up when client disconnects
        print(f"[DISCONNECTED] Client {conn.remote_addr}")
        with lock:
            if conn.remote_addr in clients:
                del clients[conn.remote_addr]
            # Remove from all rooms
            for room in rooms.values():
                room.discard(conn)

def main():
    """Start the chat server with reliable transport."""
    print(f"[STARTING] Chat server on {SERVER_BIND}:{SERVER_PORT}")
    print("Accepting connections on ports {SERVER_PORT}, {SERVER_PORT+1}, {SERVER_PORT+2}...")
    print("Press Ctrl+C to stop.\n")
    
    try:
        # Create threads for multiple client handlers (up to 3 concurrent clients)
        client_threads = []
        for i in range(3):
            thread = threading.Thread(target=create_client_handler, args=(i,), daemon=True)
            thread.start()
            client_threads.append(thread)
            time.sleep(0.1)  # Small delay between starting handlers
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server interrupted.")
    finally:
        print("Server shutting down...")

if __name__ == "__main__":
    main()
