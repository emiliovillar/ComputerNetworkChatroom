# Custom Transport Protocol & Chat Service (Python)

## 1. Team Information


**Team Members:**
- Hugo Padilla
- Jaspal khalon
- Emilio Villar
- Amy Cabrera



---

## 2. Project Overview

For this project, we built a **reliable transport protocol over UDP ** and a **multi-client chat application** that runs on top of it. The transport layer has Go-Back-N ARQ for reliability, flow control to prevent overwhelming the receiver, a three-way handshake for connections, checksum validation to catch corrupted packets, and timeout/retransmission when packets get lost.

**What we built:**
- Complete reliable transport layer from scratch (Go-Back-N, flow control, connection management)
- Multiple clients can connect to our server at the same time and chat in different rooms
- The system works even when the network drops packets
- Performance metrics showing goodput, RTT, and retransmission rates


---

## 3. Architecture Overview

### **System Components**

```
┌─────────────────────────────────────────────────────────────┐
│                     Chat Application                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│  │ Client 1 │    │ Client 2 │    │ Client N │             │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘             │
│       │               │               │                     │
│  ┌────▼───────────────▼───────────────▼─────┐             │
│  │      Multiplexed Server (Port 12345)      │             │
│  │   - Connection multiplexing (conn_id)     │             │
│  │   - Room management                       │             │
│  │   - Message broadcasting                  │             │
│  └──────────────────┬─────────────────────────┘            │
└─────────────────────┼──────────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────────┐
│              Custom Transport Layer                         │
│  - Go-Back-N ARQ (window size = 5)                         │
│  - Flow control (receiver-advertised windows)              │
│  - Three-way handshake (SYN/SYN-ACK/ACK)                   │
│  - Checksum validation                                      │
│  - Timeout & retransmission (0.5s)                         │
└─────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────────┐
│                       UDP Layer                             │
└─────────────────────────────────────────────────────────────┘
```

### **Key Implementation Details**

#### **1. Transport Layer (transport.py)**

**Packet Header (24 bytes):**
```
| Ver | Flags | ConnID | Seq | Ack | RecvWin | Len | Checksum |
| 1B  |  1B   |   2B   | 4B  | 4B  |   4B    | 4B  |    4B    |
```

**Header Definition:**
```python
#  constants.py
HEADER_FORMAT = "!BBHIIHHI"  # Network byte order (big-endian)
# B = unsigned char (1 byte)   - Version
# B = unsigned char (1 byte)   - Flags (SYN, ACK, FIN bits)
# H = unsigned short (2 bytes) - Connection ID
# I = unsigned int (4 bytes)   - Sequence number
# I = unsigned int (4 bytes)   - Acknowledgment number
# H = unsigned short (2 bytes) - Receiver window size
# H = unsigned short (2 bytes) - Payload length
# I = unsigned int (4 bytes)   - Checksum
```

**Go-Back-N Implementation:**
```python
def send_msg(self, data):
    with self.lock:
        #  how many packets we can send (limited by our window and receiver's window)
        effective_window = min(self.window_size, self.peer_recv_win)
        
        #  send if we have space in the window
        if self.next_seq_num < self.send_base + effective_window:
            pkt = TransportPacket(seq=self.next_seq_num, payload=data, 
                                 conn_id=self.conn_id, recv_win=self.recv_win)
            self._sendto(pkt.pack(), self.remote_addr)
            self.unacked_packets[self.next_seq_num] = (pkt, time.time())
            # Start timer if this is the first unacked packet
            if self.send_base == self.next_seq_num:
                self._start_timer()
            self.next_seq_num += 1
```

**Three-Way Handshake:**
```python
# Client initiates the connection
def connect(self):
    # Generate random connection ID to identify this connection
    self.conn_id = random.randint(1, 65535)
    # Create and send SYN packet to start handshake
    syn_pkt = TransportPacket(flags=SYN, conn_id=self.conn_id, 
                              seq=0, recv_win=self.recv_win)
    self._sendto(syn_pkt.pack(), self.remote_addr)
    #  wait for SYN-ACK and send final ACK (handled in _recv_loop)
```

#### **2. Server (server.py)**

**Connection Multiplexing:**
```python
class ClientConnection:
    def __init__(self, conn_id, addr):
        self.conn_id = conn_id      # Unique identifier for this connection
        self.addr = addr            # Client's (IP, port) 
        self.connected = False      # Handshake completed?
        self.expected_seq = 0       # Next sequence number we expect (in-order delivery)
        self.recv_win = 10          # How many packets we can receive (flow control)

# Dictionary maps each connection ID to its client state
# This lets one socket handle multiple clients at once
clients = {}  # conn_id -> ClientConnection
```

**Packet Routing:**
```python
def receive_loop():
    # Main server loop - runs forever waiting for packets
    while True:
        data, addr = server_sock.recvfrom(4096)
        pkt = TransportPacket.unpack(data)
        
        
        if pkt.flags & SYN:  # Handshake request
            handle_handshake(pkt, addr)
        elif pkt.flags & FIN:  # Client disconnecting
            handle_fin(pkt)
        elif (pkt.flags & ACK) and not pkt.payload:  # ACK-only (handshake completion)
            handle_handshake(pkt, addr)
        elif pkt.payload:  # Data packet
            handle_data_packet(pkt, addr)
```

#### **3. Client (client.py)**

**Simple API:**
```python
# Create connection
conn = TransportConnection(
    local_addr=('0.0.0.0', 0),      # Random port
    remote_addr=(server, port),
    on_message=on_message,           
    is_server=False
)

# Connect with handshake
conn.connect()

#  commands
conn.send_msg(f"JOIN {room}".encode())
conn.send_msg(f"MSG {room} {text}".encode())
```

### **Chat Protocol Commands**

**Authentication:**
- `LOGIN <username>` - Login with a unique username (required for most commands)
- `LOGOUT` - Logout from the server

**Room Management:**
- `JOIN <room>` - Join a chat room (receives last N messages automatically)
- `LEAVE <room>` - Leave a room

**Messaging:**
- `MSG <room> <text>` - Send message to all members in a room
- `DM <user> <text>` - Send private direct message to a specific user

**Legacy:**
- `NAME <name>` - Set display name (backward compatibility, use LOGIN instead)
- `exit/quit` - Disconnect gracefully

### **Bonus Features**

**1. Message History**
- When a client joins a room, they automatically receive the last 50 messages from that room
- Messages are stored per room and delivered before presence notifications

**2. Private Messages (DM)**
- Use `DM <username> <text>` to send direct messages that bypass room broadcasts
- Only works with logged-in users (must use LOGIN first)
- Both sender and recipient receive confirmation of the message

**3. Priority Messages**
- Presence updates (JOIN/LEAVE notifications) are delivered before regular chat messages
- Ensures users see who joined/left before seeing chat messages

**4. Persistent Usernames**
- Users must `LOGIN <username>` with a unique username before using most commands
- Usernames are validated for uniqueness across all connected clients
- Use `LOGOUT` to disconnect your username (allows re-login with different name)

---
### **Start server**


```bash
# server.py file
python server.py

```



### **Start Clients**

In separate terminals:
```bash
# Client 1 (Alice)
python client.py --name Alice

# Client 2 (Bob)
python client.py --name Bob
```

For remote connections:
```bash
python client.py --name Alice --server 192.168.1.100 --port 12345
```

### **Using the Chat**

**Basic Usage:**
```
> LOGIN Alice
Logged in as 'Alice'. Welcome!

> JOIN lobby
[history] Last 5 messages in lobby:
[lobby] Bob: Hello!
[lobby] Charlie: Hi there!
[presence] Alice joined lobby

> MSG lobby Hello everyone!
[lobby] Alice: Hello everyone!

> DM Bob Hey, private message!
[DM to Bob] Hey, private message!

> LEAVE lobby
[presence] Alice left lobby

> LOGOUT
Logged out successfully.

> exit
```

**Example with Multiple Users:**
```
# Terminal 1 (Alice)
> LOGIN Alice
> JOIN general
> MSG general Hi Bob!

# Terminal 2 (Bob)  
> LOGIN Bob
> JOIN general
[history] Last 1 messages in general:
[general] Alice: Hi Bob!
[presence] Bob joined general
> DM Alice Hi back!
```

---


---

## 9. Project Structure

Here's how the code is organized:

```
├── transport.py              # Our custom reliable transport layer (Go-Back-N)
├── server.py                 # Multi-client chat server with room support
├── client.py                 # Simple chat client
├── constants.py              # Config values and packet formats
├── test_transport.py         # Demo showing the transport layer works
├── test_lossy.py             # Tests transport under lossy network conditions
└── README.md                 # This file (you're reading it!)
```

---

## 10. Performance Evaluation


### 10.1 Test Setup
We ran all our tests using `test_lossy.py` on localhost:

- Client talking to Server over UDP using our Go-Back-N protocol
- Sent 10 test messages per test run
- Collected metrics from both the client and server sides to see what's happening
- Tests run automatically for each loss profile

### 10.2 Network Loss Profiles
We simulated three different network conditions (configurable via `LOSS_PROFILE` in `transport.py`):

- **clean** → Perfect network, 0% packet loss (ideal case, default for demo)
- **random** → About 8% of packets randomly drop (simulates normal internet)
- **bursty** → Packets drop in bursts (simulates WiFi congestion)
#### 10.2.1 Clean Profile (0% Loss)
**Results:**
- Messages sent: 10
- Messages delivered: 10 / 10 ✓
- Retransmissions: 0
- Out-of-order packets: 0
- Average RTT: ~0.5-1 ms
- Goodput: ~40-50 messages/sec

**Bottom line:**  no retransmissions needed and super low latency. 

#### 10.2.2 Random Loss (~8% Loss)
**Config:** `LOSS_PROFILE = "random"`, `RANDOM_LOSS_PROB = 0.08`

**Results:**
- Messages sent: 10
- Messages delivered: 10 / 10 ✓ (all messages still get through!)
- Retransmissions: 2-5 (varies per run)
- Out-of-order packets: 1-3
- Average RTT: ~1-3 ms (slightly higher)
- Goodput: ~30-40 messages/sec (reduced due to retransmissions)

**Bottom line:**  8% packet loss, protocol ensures all messages get delivered reliably. We see some retransmissions and throughput drops a bit, but everything still works correctly.

#### 10.2.3 Bursty Loss (8-12% in bursts)
**Config:** `LOSS_PROFILE = "bursty"` with burst parameters

**Results:**
- Messages sent: 10
- Messages delivered: 10 / 10 ✓ (still 100% reliable!)
- Retransmissions: 5-10 (higher due to burst nature)
- Out-of-order packets: 3-6
- Average RTT: ~5-15 ms (significantly higher)
- Goodput: ~15-25 messages/sec (notably reduced)

**Bottom line:** multiple packets drop at once and Go-Back-N has to retransmit the whole window. Latency spikes and throughput takes a hit,still delivers everything correctly.

### 10.3 Running Loss Tests

To see the protocol handle packet loss:
```bash
python test_lossy.py
```

This automatically runs all three test profiles and shows:
- Live message delivery status
- Retransmission counts
- RTT statistics
- Goodput (messages/sec)

### 10.4 Application Testing
We also tested the actual chat application:

#### Multiple Clients
- Started `server.py` on port 12345
- Connected 3+ clients simultaneously
- Had them all join the same room and chat
- **Result:** All clients could see each other's messages, server handled concurrent connections perfectly

#### Stability
- Left server running with clients connected for extended periods
- Clients sent messages periodically
- **Result:** No crashes, no freezes, connections remained stable and responsive

#### Message Throughput
- Tested rapid message sending under both clean and lossy conditions
- **Result:** Clean network = instant delivery. Lossy network = retransmissions kick in, but everything still gets delivered correctly

### 10.5 Summary
After all these tests, here's what we demonstrated:

- **100% Reliability:** Our transport layer delivers all messages correctly and in order over UDP, even with significant packet loss
- **Go-Back-N Works:** Automatic retransmission kicks in when packets are lost, maintaining reliability
- **Metrics Tracking:** We measure goodput (messages/sec), RTT, retransmissions, and out-of-order packets
- **Production Ready:** The chat application is stable with multiple concurrent clients and handles real-world usage patterns


### AI Citation
Gemini 3.0 Pro 
ChatGPT 2.5 Flash
