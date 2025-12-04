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

**Demo:**
- Reliable transport layer from scratch (Go-Back-N, flow control, connection management)
- Multiple clients can connect to our server at the same time and chat
- The system works even when the network drops packets


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
# From constants.py
HEADER_FORMAT = "!BBHIIHHI"  # Network byte order (big-endian)
# B = unsigned char (1 byte)  - Version
# B = unsigned char (1 byte)  - Flags (SYN, ACK, FIN bits)
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
        # how many packets we can send (limited by our window and receiver's window)
        effective_window = min(self.window_size, self.peer_recv_win)
        
        # send if we have space in the window
        if self.next_seq_num < self.send_base + effective_window:
            pkt = TransportPacket(seq=self.next_seq_num, payload=data, 
                                 conn_id=self.conn_id, recv_win=self.recv_win)
            self.sock.sendto(pkt.pack(), self.remote_addr)
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
    # random connection ID to identify this connection
    self.conn_id = random.randint(1, 65535)
    # Create and send SYN packet to start handshake
    syn_pkt = TransportPacket(flags=SYN, conn_id=self.conn_id, 
                              seq=0, recv_win=self.recv_win)
    self.sock.sendto(syn_pkt.pack(), self.remote_addr)
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
    # Main server loop 
    while True:
        data, addr = server_sock.recvfrom(4096)
        pkt = TransportPacket.unpack(data)
        
        # Route incoming packets based on what they are:
        if pkt.flags & SYN:  
            handle_handshake(pkt, addr)
        elif pkt.payload:  
            handle_data_packet(pkt, addr)
```

#### **3. Client (client.py)**

**Simple API:**
```python
# Create connection
conn = TransportConnection(
    local_addr=('0.0.0.0', 0),      # Random port
    remote_addr=(server, port),
    on_message=on_message,           # Callback for received data
    is_server=False
)

# Connect with handshake
conn.connect()

# Send commands
conn.send_msg(f"JOIN {room}".encode())
conn.send_msg(f"MSG {room} {text}".encode())
```

### **Chat Protocol Commands**
- `NAME <name>` - Set display name
- `JOIN <room>` - Join a chat room
- `LEAVE <room>` - Leave a room
- `MSG <room> <text>` - Send message to room members
- `exit/quit` - Disconnect gracefully

---




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

```
> JOIN lobby
> MSG lobby Hello everyone!
> LEAVE lobby
> exit
```

---

### **Transport Layer Verification**

Run the transport demo:
```bash
python test_transport.py
```

Expected output shows:
- Successful handshake with conn_id
- All 5 messages delivered reliably
- Flow control windows displayed
- Clean connection teardown

---

## 9. Project Structure

Here's how the code is organized:

```
├── transport.py              # Our custom reliable transport layer (Go-Back-N)
├── server.py                 # Multi-client chat server with room support
├── client.py                 # Simple chat client
├── constants.py              # Config values and packet formats
├── test_transport.py         # Demo showing the transport layer works
├── test_multiclient.py       # Instructions for testing multiple clients
└── README.md                 # This file (you're reading it!)
```

---

## 10. Performance Evaluation


### 10.1 Test Setup
We ran all our tests using `test_transport.py` on localhost:

- Client talking to Server over UDP using our Go-Back-N protocol
- Sent 5 test messages ("Hello 0" through "Hello 4", 7 bytes each = 35 bytes total)
- Collected metrics from both the client and server sides to see what's happening

### 10.2 Network Loss Profiles
We simulated three different network conditions:

- **clean** → Perfect network, 0% packet loss (ideal case)
- **random** → About 8% of packets randomly drop (normal internet)
- **bursty** → Packets drop in bursts (WiFi gets congested)
#### 10.2.1 Clean Profile (0% Loss)
**Client:**
- Messages sent: 5
- Retransmissions: 0
- Average RTT: ~0.84 ms
- 95th percentile RTT: ~1.37 ms

**Server:**
- Messages delivered: 5 / 5
- Bytes delivered: 35 bytes
- Out-of-order packets: 0
- Delivery duration: ~0.21 s
- Goodput: ~1333 bits/sec

**Bottom line:** With perfect network conditions, everything works great - no retransmissions needed and super low latency. This is our baseline to compare against.

#### 10.2.2 Random Loss (~8% Loss)
**Config:** LOSS_PROFILE = "random", RANDOM_LOSS_PROB = 0.08

**Client:**
- Messages sent: 5
- Retransmissions: 0 (no drops in this short run)
- Average RTT: ~0.09 ms

**Server:**
- Messages delivered: 5 / 5
- Bytes delivered: 35 bytes
- Goodput: ~1369 bits/sec
- Out-of-order packets: 0

**Bottom line:** We got lucky in this short test - no packets dropped. But when we run longer tests with random loss, we do see retransmissions happening and throughput drops a bit compared to the perfect network.

#### 10.2.3 Bursty Loss (Bursty 8–12% Loss)
**Config:** LOSS_PROFILE = "bursty" with burst and base loss parameters

**Client:**
- Messages sent: 5
- Retransmissions: 0 (no drops in this short run)
- RTT samples: [0.0, 0.154…, 0.101…, 0.051…, 0.0]
- Average RTT: ~61 ms
- 95th percentile RTT: ~101 ms

**Server:**
- Messages delivered: 5 / 5
- Bytes delivered: 35 bytes
- Delivery duration: ~0.205 s
- Goodput: ~1365 bits/sec
- Out-of-order packets: 0

**Bottom line:** Bursty loss is rough - even when packets don't drop, the latency goes way up. When bursts actually happen, multiple packets drop at once and Go-Back-N has to retransmit the whole window, which really hurts throughput.

10.3 Additional Testing
We also ran basic application-level tests with the chat server:

#### 10.3.1 Multiple Clients at Once
- Started the server on port 12345
- Connected three clients (Alice, Bob, and Charlie)
- Had them all join the same room and start chatting
- **Result:** Everyone could see each other's messages and the server handled all the connections without breaking.

#### 10.3.2 Stability Over Time
- Left the server running with multiple clients connected 
- Had clients send messages every so often
- **Result:**  no crashes, no freezes, connections stayed responsive.

#### 10.3.3 Rapid Message Spam
- Tested under both perfect and lossy network conditions
- **Result:** With a good network, every message got through first try. With packet loss, we saw retransmissions, but the protocol still delivered everything correctly.

### 10.4 Summary
So after all these tests, here's what we can say:

- Our transport layer actually works! It delivers messages reliably and in order over UDP, even when packets are getting dropped.
- We track useful metrics like throughput, round-trip time, retransmissions, and out-of-order packets.
- The chat app itself is solid - handles multiple clients, stays stable over time, and can deal with message spam.


