import socket
import threading
import time
from collections import defaultdict, deque
from queue import PriorityQueue
from constants import SERVER_BIND, SERVER_PORT, HEADER_FORMAT, HEADER_LEN, ACK, SYN, FIN
from transport import TransportPacket

# Configuration
MESSAGE_HISTORY_SIZE = 50  # Number of messages to keep per room

# Global state
rooms = defaultdict(set)  # room name -> set of conn_ids in that room
clients = {}  # conn_id -> ClientConnection object
addr_to_conn_id = {}  # (ip, port) -> conn_id for routing
client_names = {}  # conn_id -> display name
username_to_conn_id = {}  # username -> conn_id (for unique usernames and DM)
logged_in_users = set()  # conn_ids that have logged in
room_history = defaultdict(lambda: deque(maxlen=MESSAGE_HISTORY_SIZE))  # room -> deque of messages
lock = threading.Lock()  # protects all global state

# Priority message queues (priority: 0 = high, 1 = normal)
priority_queue = PriorityQueue()  # (priority, timestamp, conn_id, data)
message_processor_running = False

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
        self.logged_in = False  # whether client has logged in with unique username
        self.username = None  # unique username (None if not logged in)
        
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

def handle_client_message(conn_id, data, is_priority=False):
    """Parse and execute client commands (LOGIN, LOGOUT, JOIN, LEAVE, MSG, DM, NAME)"""
    try:
        msg = data.decode('utf-8').strip()
        client = clients.get(conn_id)
        # If client doesn't exist, ignore
        if not client:
            return
            
        display_name = client.username if client.username else client_names.get(conn_id, str(client.addr))
        print(f"[{display_name}] {msg}")
        
        parts = msg.split(" ", 2)
        cmd = parts[0].upper()
        
        # LOGIN command - requires unique username
        if cmd == "LOGIN" and len(parts) >= 2:
            username = parts[1].strip()
            if not username:
                client.send_msg("Error: Username cannot be empty.".encode())
                return
            
            with lock:
                # Check if username is already taken
                if username in username_to_conn_id:
                    existing_conn_id = username_to_conn_id[username]
                    if existing_conn_id != conn_id:
                        client.send_msg(f"Error: Username '{username}' is already taken.".encode())
                        return
                
                # Set username and mark as logged in
                username_to_conn_id[username] = conn_id
                client.logged_in = True
                client.username = username
                client_names[conn_id] = username
                logged_in_users.add(conn_id)
            
            client.send_msg(f"Logged in as '{username}'. Welcome!".encode())
            print(f"[LOGIN] {username} (conn_id={conn_id})")
            return
        
        # LOGOUT command
        elif cmd == "LOGOUT":
            with lock:
                if client.logged_in and client.username:
                    username = client.username
                    if username in username_to_conn_id:
                        del username_to_conn_id[username]
                    client.logged_in = False
                    client.username = None
                    logged_in_users.discard(conn_id)
                    client.send_msg("Logged out successfully.".encode())
                    print(f"[LOGOUT] {username} (conn_id={conn_id})")
                else:
                    client.send_msg("You are not logged in.".encode())
            return
        
        # Check if logged in for other commands (except NAME for backward compatibility)
        if cmd != "NAME" and not client.logged_in:
            client.send_msg("Error: You must LOGIN <username> first before using other commands.".encode())
            return
        
        # JOIN command - with message history
        if cmd == "JOIN" and len(parts) >= 2:
            room = parts[1]
            with lock:
                rooms[room].add(conn_id)
            
            # Send message history first (before presence notification)
            with lock:
                history = list(room_history[room])
            
            if history:
                client.send_msg(f"[history] Last {len(history)} messages in {room}:".encode())
                for hist_msg in history:
                    client.send_msg(hist_msg)
            
            # Then send presence update (priority message - processed before chat messages)
            client_name = client.username if client.username else client_names.get(conn_id, str(client.addr))
            notice = f"[presence] {client_name} joined {room}"
            print(notice)
            # Queue as priority message (priority 0 = high)
            queue_message(0, room, notice.encode(), is_presence=True)
            
        # LEAVE command
        elif cmd == "LEAVE" and len(parts) >= 2:
            room = parts[1]
            with lock:
                if conn_id in rooms[room]:
                    rooms[room].remove(conn_id)
            client_name = client.username if client.username else client_names.get(conn_id, str(client.addr))
            notice = f"[presence] {client_name} left {room}"
            print(notice)
            # Queue as priority message (priority 0 = high)
            queue_message(0, room, notice.encode(), is_presence=True)
            
        # MSG command - regular chat message
        elif cmd == "MSG" and len(parts) >= 3:
            room, text = parts[1], parts[2]
            # Check if client is in the room
            with lock:
                in_room = conn_id in rooms[room]
            
            if in_room:
                client_name = client.username if client.username else client_names.get(conn_id, str(client.addr))
                full_msg = f"[{room}] {client_name}: {text}"
                # Store in history
                with lock:
                    room_history[room].append(full_msg.encode())
                # Queue as normal priority message (priority 1 = normal)
                queue_message(1, room, full_msg.encode(), is_presence=False)
            else:
                client.send_msg(f"You are not in {room}. Use JOIN {room} first.".encode())
        
        # DM command - private message
        elif cmd == "DM" and len(parts) >= 3:
            target_username, text = parts[1], parts[2]
            sender_name = client.username if client.username else client_names.get(conn_id, str(client.addr))
            
            with lock:
                target_conn_id = username_to_conn_id.get(target_username)
            
            if target_conn_id and target_conn_id in clients:
                target_client = clients[target_conn_id]
                dm_msg = f"[DM from {sender_name}] {text}"
                target_client.send_msg(dm_msg.encode())
                client.send_msg(f"[DM to {target_username}] {text}".encode())
                print(f"[DM] {sender_name} -> {target_username}: {text}")
            else:
                client.send_msg(f"Error: User '{target_username}' not found or not logged in.".encode())
                
        # NAME command - kept for backward compatibility, but recommend LOGIN
        elif cmd == "NAME" and len(parts) >= 2:
            name = parts[1]
            with lock:
                client_names[conn_id] = name
            client.send_msg(f"Name set to: {name} (Note: Use LOGIN <username> for persistent unique username)".encode())
            
        elif cmd == "SHUTDOWN":
            print("[SHUTDOWN] Server shutdown command received.")
            client.send_msg(b"Server shutting down...")
            
        else:
            client.send_msg(b"Invalid command. Use: LOGIN <username>, LOGOUT, JOIN <room>, LEAVE <room>, MSG <room> <text>, DM <user> <text>, NAME <name>")
            
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

def queue_message(priority, room, data, is_presence=False):
    """Queue a message for processing with priority (0=high, 1=normal)"""
    timestamp = time.time()
    if is_presence:
        # Presence messages are high priority
        priority = 0
    priority_queue.put((priority, timestamp, room, data, is_presence))

def process_message_queue():
    """Process messages from priority queue, ensuring presence updates come first"""
    global message_processor_running
    
    message_processor_running = True
    while True:
        try:
            priority, timestamp, room, data, is_presence = priority_queue.get(timeout=0.1)
            # Broadcast to the room
            if room:
                broadcast_to_room(room, data)
            priority_queue.task_done()
        except:
            continue

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
        # Handle all commands (priority handling is done inside handle_client_message)
        handle_client_message(conn_id, pkt.payload, is_priority=False)
    
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
            username = client.username if client.username else client_names.get(conn_id, str(client.addr))
            print(f"[DISCONNECTED] Client {username} ({client.addr}, conn_id={conn_id})")
            client.connected = False
            
            # Remove client from all rooms and send presence updates
            rooms_to_notify = []
            for room_name, members in rooms.items():
                if conn_id in members:
                    rooms_to_notify.append(room_name)
                    members.discard(conn_id)
            
            # Send presence updates for leaving rooms
            for room in rooms_to_notify:
                notice = f"[presence] {username} left {room}"
                queue_message(0, room, notice.encode(), is_presence=True)
            
            # Clean up username mapping
            if client.logged_in and client.username:
                if client.username in username_to_conn_id:
                    del username_to_conn_id[client.username]
                logged_in_users.discard(conn_id)
            
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
    global server_sock, message_processor_running
    
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind((SERVER_BIND, SERVER_PORT))
    
    print(f"[LISTENING] Chat server on {SERVER_BIND}:{SERVER_PORT}")
    print("Press Ctrl+C to stop.\n")
    
    recv_thread = threading.Thread(target=receive_loop, daemon=True)
    recv_thread.start()
    
    # Start message processor thread for priority queue
    if not message_processor_running:
        processor_thread = threading.Thread(target=process_message_queue, daemon=True)
        processor_thread.start()
    
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
