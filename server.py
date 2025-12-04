import socket
import threading
import time
from collections import defaultdict
from constants import SERVER_BIND, SERVER_PORT, HEADER_FORMAT, HEADER_LEN, ACK, SYN, FIN
from transport import TransportPacket

# Global state
rooms = defaultdict(set)  # room name -> set of conn_ids in that room
clients = {}  # conn_id -> ClientConnection object
addr_to_conn_id = {}  # (ip, port) -> conn_id for routing
client_names = {}  # conn_id -> display name
lock = threading.Lock()  # protects all global state

# Single UDP socket shared by all clients
server_sock = None

class ClientConnection:
    """Tracks per-client connection state"""
    def __init__(self, conn_id, addr):
        self.conn_id = conn_id  # unique connection identifier
        self.addr = addr  # client's (ip, port) tuple
        self.connected = False  # handshake completed?
        self.expected_seq = 0  # next seq number we expect to receive
        self.send_seq = 0  # next seq number to send
        self.recv_win = 10  # our receive window size
        self.peer_recv_win = 5  # client's advertised receive window
        
    def send_msg(self, data):

        pkt = TransportPacket(
            seq=self.send_seq,
            ack=self.expected_seq,
            conn_id=self.conn_id,
            payload=data,
            recv_win=self.recv_win
        )
        server_sock.sendto(pkt.pack(), self.addr)
        self.send_seq += 1

def handle_client_message(conn_id, data):
    """Parse and execute client commands (JOIN, LEAVE, MSG, NAME)"""
    try:
        msg = data.decode('utf-8').strip()
        client = clients.get(conn_id)
        # If client doesn't exist, ignore
        if not client:
            return
            
        print(f"[{client_names.get(conn_id, client.addr)}] {msg}")
        
        parts = msg.split(" ", 2)
        cmd = parts[0].upper()
        
       
        if cmd == "JOIN" and len(parts) >= 2:
            room = parts[1]
            with lock:
                rooms[room].add(conn_id)
            client_name = client_names.get(conn_id, str(client.addr))
            notice = f"[presence] {client_name} joined {room}"
            print(notice)
            broadcast_to_room(room, notice.encode())
            
        
        elif cmd == "LEAVE" and len(parts) >= 2:
            room = parts[1]
            with lock:
                if conn_id in rooms[room]:
                    rooms[room].remove(conn_id)
            client_name = client_names.get(conn_id, str(client.addr))
            notice = f"[presence] {client_name} left {room}"
            print(notice)
            broadcast_to_room(room, notice.encode())
            
        
        elif cmd == "MSG" and len(parts) >= 3:
            room, text = parts[1], parts[2]
            # Check if client is in the room
            with lock:
                in_room = conn_id in rooms[room]
            
            if in_room:
                client_name = client_names.get(conn_id, str(client.addr))
                full_msg = f"[{room}] {client_name}: {text}"
                broadcast_to_room(room, full_msg.encode())
            else:
                client.send_msg(f"You are not in {room}. Use JOIN {room} first.".encode())
                
        
        elif cmd == "NAME" and len(parts) >= 2:
            name = parts[1]
            with lock:
                client_names[conn_id] = name
            client.send_msg(f"Name set to: {name}".encode())
            
        elif cmd == "SHUTDOWN":
            print("[SHUTDOWN] Server shutdown command received.")
            client.send_msg(b"Server shutting down...")
            
        else:
            client.send_msg(b"Invalid command. Use: JOIN <room>, LEAVE <room>, MSG <room> <text>, NAME <name>")
            
    except Exception as e:
        print(f"Error handling message from conn_id {conn_id}: {e}")

def broadcast_to_room(room, data):
    """Send message to all clients in a room"""
    with lock:
        member_ids = list(rooms[room])
    
    # Send to each member
    for conn_id in member_ids:
        client = clients.get(conn_id)
        if client:
            try:
                client.send_msg(data)
            except Exception as e:
                print(f"Failed to send to client {conn_id}: {e}")

def handle_handshake(pkt, addr):
    """Process SYN and ACK packets for three-way handshake"""
    # Step 1: Receive SYN from client
    if (pkt.flags & SYN) and not (pkt.flags & ACK):
        conn_id = pkt.conn_id
        
        with lock:
            # Create new client connection if doesn't exist
            if conn_id not in clients:
                client = ClientConnection(conn_id, addr)
                clients[conn_id] = client
                addr_to_conn_id[addr] = conn_id
                print(f"[HANDSHAKE] New client from {addr} (conn_id={conn_id})")
        
        # Step 2: Send SYN-ACK back
        syn_ack = TransportPacket(
            flags=SYN|ACK,
            conn_id=conn_id,
            seq=0,
            ack=pkt.seq + 1,
            recv_win=10
        )
        server_sock.sendto(syn_ack.pack(), addr)
        
    # Step 3: Receive final ACK from client
    elif (pkt.flags & ACK) and not (pkt.flags & SYN):
        conn_id = pkt.conn_id
        with lock:
            client = clients.get(conn_id)
            # Mark connection as established
            if client and not client.connected:
                client.connected = True
                client.peer_recv_win = pkt.recv_win if pkt.recv_win > 0 else 1
                print(f"[CONNECTED] Client {client.addr} (conn_id={conn_id})")

def handle_data_packet(pkt, addr):
    """Process data packets and send ACKs"""
    conn_id = pkt.conn_id
    
    with lock:
        client = clients.get(conn_id)
    
    # Ignore packets from unknown or unconnected clients
    if not client or not client.connected:
        return
    
    # If packet is in order, deliver to application
    if pkt.payload and pkt.seq == client.expected_seq:
        client.expected_seq += 1
        handle_client_message(conn_id, pkt.payload)
    
    # send ACK with our expected sequence number
    ack_pkt = TransportPacket(
        seq=0,
        ack=client.expected_seq,
        conn_id=conn_id,
        flags=ACK,
        recv_win=client.recv_win
    )
    server_sock.sendto(ack_pkt.pack(), addr)

def handle_fin(pkt):
    """Handle client disconnection (FIN packet)"""
    conn_id = pkt.conn_id
    
    with lock:
        client = clients.get(conn_id)
        if client:
            print(f"[DISCONNECTED] Client {client.addr} (conn_id={conn_id})")
            client.connected = False
            
            # Remove client from all rooms
            for room in rooms.values():
                room.discard(conn_id)
            
            # Clean up all client state
            del clients[conn_id]
            if client.addr in addr_to_conn_id:
                del addr_to_conn_id[client.addr]
            if conn_id in client_names:
                del client_names[conn_id]

def receive_loop():
    """Main server loop - receives and routes all packets"""
    global server_sock
    
    while True:
        try:
            data, addr = server_sock.recvfrom(4096)
            pkt = TransportPacket.unpack(data)
            
            # Route packet based on flags and content
            if pkt.flags & SYN:  # Handshake request
                handle_handshake(pkt, addr)
            elif pkt.flags & FIN:  # Client disconnecting
                handle_fin(pkt)
            elif (pkt.flags & ACK) and not pkt.payload:  # ACK-only (handshake completion)
                handle_handshake(pkt, addr)
            elif pkt.payload:  # Data packet
                handle_data_packet(pkt, addr)
                
        except Exception as e:
            print(f"Error in receive loop: {e}")
            continue

def main():
    global server_sock
    
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind((SERVER_BIND, SERVER_PORT))
    
    print(f"[LISTENING] Chat server on {SERVER_BIND}:{SERVER_PORT}")
    print("Press Ctrl+C to stop.\n")
    
    recv_thread = threading.Thread(target=receive_loop, daemon=True)
    recv_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server interrupted.")
    finally:
        print("Shutting down...")
        server_sock.close()

if __name__ == "__main__":
    main()
