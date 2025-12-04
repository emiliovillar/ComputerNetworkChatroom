# Custom Transport Protocol & Chat Service (Python)

## 1. Team Information

**Team Name:** Team 7

**Team Members:**
- Hugo Padilla
- Jaspal khalon
- Emilio Villar
- Amy Cabrera

**Selected Project:** Chat Room

---

## 2. Project Overview

This project implements a **reliable transport protocol over UDP from scratch** and a **multi-client chat application** that uses it. The transport layer includes Go-Back-N ARQ, flow control, three-way handshake, checksum validation, and timeout/retransmission mechanisms—all built without using TCP.

**Goals:**
- Implement a complete reliable transport layer (Go-Back-N ARQ, flow control, connection management)
- Create a concurrent multi-client chat server with room management
- Test and measure performance under various network conditions
- Demonstrate deep understanding of transport layer protocols

---

## 3. Transport Protocol Implementation

### **Implemented Features**

**Protocol Type:** Go-Back-N ARQ with sliding window

**Header Format (24 bytes):**
```
| Version (1B) | Flags (1B) | Conn ID (2B) | Seq (4B) | Ack (4B) | Recv Win (4B) | Length (4B) | Checksum (4B) |
```

**Core Features:**
- **Go-Back-N ARQ:** Sliding window protocol (window size = 5) with cumulative acknowledgments
- **Flow Control:** Receiver-advertised window to prevent buffer overflow
- **Connection Management:** Three-way handshake (SYN/SYN-ACK/ACK) and graceful teardown (FIN)
- **Checksum:** 32-bit checksum for packet integrity verification
- **Timeout & Retransmission:** Fixed timeout (0.5s) with full window retransmission on timeout
- **Multiplexing:** Connection ID-based multiplexing for multiple clients on single UDP socket

**API:**
```python
# Connection setup
conn = TransportConnection(local_addr, remote_addr, on_message, is_server)
conn.connect()  # Client-side handshake

# Sending data
conn.send_msg(data)  # Reliable delivery with flow control

# Receiving data
def on_message(data):  # Callback for received messages
    print(data.decode())

# Cleanup
conn.close()  # Send FIN and cleanup
```

---

## 4. Application Layer Implementation

**Architecture:** Multi-room chat server with connection multiplexing

**Files:**
- `transport.py`: Reliable transport layer (Go-Back-N, flow control, handshake)
- `server_multiplexed.py`: Multi-client chat server with single-socket architecture
- `client.py`: Chat client with command interface
- `constants.py`: Shared configuration (header format, ports, flags)

**Commands:**
- `JOIN <room>` - Join a chat room
- `LEAVE <room>` - Leave a chat room
- `MSG <room> <text>` - Send message to room
- `NAME <name>` - Set display name
- `exit/quit` - Disconnect from server

**Concurrency:**
- Single UDP socket on port 12345 for all clients
- Thread-safe room management with locks
- Per-client state tracking via `ClientConnection` objects
- Background receive loop for packet processing

---

## 5. Progress Summary (December 3, 2025)

### **Completed Today:**

1. **Code Cleanup:**
   - Removed verbose comments and "AI slop"
   - Cleaned up redundant code patterns
   - Simplified function signatures
   - Removed emoji characters, replaced with structured logging tags

2. **Client Enhancements:**
   - Added connection confirmation with flow control info
   - Added message send confirmation
   - Better error handling with try/catch blocks

3. **Architecture:**
   - All transport layer features implemented and tested
   - Single-socket server architecture with connection multiplexing
   - Thread-safe concurrent client handling

### **What's Working:**

- Go-Back-N ARQ with retransmission
- Three-way handshake (SYN/SYN-ACK/ACK)
- Flow control with receiver windows
- Checksum validation
- Connection teardown (FIN)
- Multi-room chat functionality
- Presence notifications

### **Verified Working:**

- ✅ Multi-client communication (2+ clients tested)
- ✅ Cross-client message delivery
- ✅ Room broadcasting
- ✅ Three-way handshake completion
- ✅ Go-Back-N retransmission
- ✅ Flow control

---

## 6. Remaining Work

### **Critical (Required for Completion):**

1. **Metrics Collection System:**
   - Throughput (goodput) measurement
   - Average and 95th percentile latency
   - Retransmissions per KB tracking
   - Out-of-order packet counting
   - Add metrics API to TransportConnection class

2. **Network Loss Testing:**
   - Clean profile (0% loss) - baseline performance
   - Random loss profile (5-10%)
   - Bursty loss profile (8-12%)
   - Document performance under each condition

3. **Additional Testing:**
   - Test with 3+ concurrent clients
   - Long-duration stability testing
   - Stress testing with rapid message sending

### **Optional Improvements:**

- Remove debug logging for production
- Adaptive timeout calculation (currently fixed at 0.5s)
- Better error recovery mechanisms
- Performance optimizations
- Proper logging framework

---

## 7. How to Run

**Requirements:**
- Python 3.8+ (standard library only)
- No external dependencies

### **Start the Server**

Use the multiplexed server (recommended):
```bash
python server_multiplexed.py
```

Server will start on `0.0.0.0:12345` and display:
```
[LISTENING] Chat server on 0.0.0.0:12345
Press Ctrl+C to stop.
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

```
> JOIN lobby
> MSG lobby Hello everyone!
> LEAVE lobby
> exit
```

---

## 8. Testing

### **Basic Functionality Test**

1. Start server
2. Connect two clients with different names
3. Both join same room: `JOIN lobby`
4. Send messages from each client
5. Verify both clients see all messages
6. Check presence notifications when joining/leaving

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

```
├── transport.py              # Reliable transport layer (Go-Back-N)
├── server_multiplexed.py     # Multi-client server (single socket)
├── client.py                 # Chat client
├── constants.py              # Shared configuration
├── test_transport.py         # Transport layer demo
├── test_multiclient.py       # Multi-client test script
└── README.md                 # This file
```
 Use `server_multiplexed.py` for actual deployment.

 10. Performance Evaluation
This section summarizes how our custom transport protocol behaves under different simulated network conditions and basic load tests.

10.1 Test Setup
All measurements were taken using test_transport.py on localhost:

Client ↔ Server over UDP with our Go-Back-N implementation
Payload: 5 messages ("Hello 0" … "Hello 4", 7 bytes each → 35 bytes total)
Metrics collected via TransportConnection.get_metrics() on both client (sender) and server (receiver)
10.2 Network Loss Profiles
We used a built-in loss simulator with three profiles:

LOSS_PROFILE = "clean" → 0% packet loss
LOSS_PROFILE = "random" → ~8% independent packet loss
LOSS_PROFILE = "bursty" → bursty loss with short high-loss bursts
10.2.1 Clean Profile (0% Loss)
Client:
Messages sent: 5
Retransmissions: 0
Average RTT: ~0.84 ms
95th percentile RTT: ~1.37 ms
Server:
Messages delivered: 5 / 5
Bytes delivered: 35 bytes
Out-of-order packets: 0
Delivery duration: ~0.21 s
Goodput: ~1333 bits/sec
Summary: With no loss, the protocol delivers all messages reliably with no retransmissions and very low latency. This is our baseline.

10.2.2 Random Loss (~8% Loss)
Config: LOSS_PROFILE = "random", RANDOM_LOSS_PROB = 0.08
Client:
Messages sent: 5
Retransmissions: 0 (no drops in this short run)
Average RTT: ~0.09 ms
Server:
Messages delivered: 5 / 5
Bytes delivered: 35 bytes
Goodput: ~1369 bits/sec
Out-of-order packets: 0
Summary: In this short 5-message test, no packets happened to be dropped, so behavior is almost identical to the clean profile. Over longer runs with the same random loss, we observe retransmissions and slightly reduced goodput compared to the clean baseline.

10.2.3 Bursty Loss (Bursty 8–12% Loss)
Config: LOSS_PROFILE = "bursty" with burst and base loss parameters
Client:
Messages sent: 5
Retransmissions: 0 (no drops in this short run)
RTT samples: [0.0, 0.154…, 0.101…, 0.051…, 0.0]
Average RTT: ~61 ms
95th percentile RTT: ~101 ms
Server:
Messages delivered: 5 / 5
Bytes delivered: 35 bytes
Delivery duration: ~0.205 s
Goodput: ~1365 bits/sec
Out-of-order packets: 0
Summary: Even without losses in this small run, bursty conditions significantly increase latency and jitter compared to clean/random. In longer runs, bursts cause multiple consecutive drops, which trigger Go-Back-N retransmissions and reduce effective goodput.

10.3 Additional Testing
We also ran basic application-level tests with the chat server:

10.3.1 3+ Concurrent Clients
Started server_multiplexed.py on port 12345.
Connected three clients (client.py --name Alice/Bob/Charlie).
All joined the same room (JOIN lobby) and exchanged messages.
Result: All clients saw each other’s messages and presence updates. The server handled multiple concurrent connections without errors.

10.3.2 Long-Duration Stability
Kept the server running with multiple clients for several minutes.
Sent periodic messages from different clients.
Result: No crashes, no deadlocks, and connections remained responsive.

10.3.3 Stress / Rapid Sending
Modified test_transport.py to send many messages in a tight loop.
Ran under clean and lossy profiles.
Result:
Under clean conditions, all messages were delivered with no retransmissions. Under random and bursty loss, retransmissions increased (as expected), but the transport still delivered all messages reliably and in order.

10.4 Summary
Across all tested scenarios:

The transport layer correctly implements reliable, in-order delivery over UDP.
The metrics system reports:
Goodput,
RTT (average and 95th percentile),
Retransmissions per KB,
Out-of-order packet counts.
The chat application remains stable with multiple clients, longer runtimes, and higher message rates.
This confirms that the protocol and chat system behave correctly and robustly under a range of network conditions.
