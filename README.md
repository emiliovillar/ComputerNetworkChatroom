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

This project implements a reliable transport protocol over UDP from scratch and a multi-client chat application that uses it. The transport layer's reliability, connection management, and flow control are built without using standard TCP sockets. The application layer provides a multi-room chat server capable of handling concurrent clients.

**Goals:**
- Demonstrate understanding of transport layer protocols by implementing Go-Back-N ARQ from scratch
- Create a reliable communication channel over unreliable UDP
- Build a concurrent multi-client chat application
- Test and measure performance under various network conditions

**What we intend to demonstrate:**
- Reliable data transmission over lossy networks using custom transport protocol
- Multi-client concurrent chat functionality with room management
- Performance metrics under different network loss scenarios
- Proper connection management and error handling

---

## 3. Transport Protocol Design Plan

**Reliability Protocol:** Go-Back-N ARQ (Automatic Repeat Request) - *Planned for final milestone*

**Current Implementation:**
- Basic UDP communication with custom packet structure
- TransportPacket class with header fields for future reliability features

**Planned Design Details:**

**Header Fields (Currently Implemented):**
- Version (8 bits): Protocol version
- Flags (8 bits): SYN, ACK, FIN, DATA flags for connection state  
- Connection ID (16 bits): Connection identifier
- Sequence Number (32 bits): For ordering and duplicate detection
- Acknowledgment Number (32 bits): Next expected sequence number
- Receiver Window (16 bits): Receiver-advertised window for flow control
- Length (16 bits): Payload size
- Checksum (16 bits): Error detection

**Planned Features (Not Yet Implemented):**
- **Timers:** Retransmission timer and connection timer
- **Flow Control:** Receiver-advertised window limiting sender transmission rate
- **Retransmission Logic:** Sliding window of unacknowledged packets
- **Reliability Mechanisms:** Packet loss detection, duplication handling, reordering management

---

## 4. Application Layer Design Plan

**Message Format:**
The application uses space-separated text format for simplicity and human readability.

**Command Grammar:**
- `JOIN room_name` - Join a chat room
- `LEAVE room_name` - Leave a chat room  
- `MSG room_name message_text` - Send message to room
- `SHUTDOWN` - Shutdown the server (admin command)

**Client-Server Interaction:**
1. **Connection:** Client connects directly via UDP
2. **Room Management:** Clients can join/leave multiple rooms
3. **Messaging:** Server broadcasts messages to all room members
4. **Disconnection:** Client can exit with 'exit' or 'quit' command

**Concurrency Support:**
- **Server-side:** Uses threading to handle multiple clients simultaneously
- **Minimum Requirement:** Supports at least 2 concurrent clients
- **Implementation:** Each client connection runs in a separate thread
- **Synchronization:** Thread-safe room management and message broadcasting

---

## 5. Testing and Metrics Plan

**Network Loss Profiles:**

**Clean Network:**
- 0% packet loss
- Baseline performance measurement
- Expected metrics: High throughput, low latency, minimal retransmissions

**Random Loss:**
- 1-5% random packet loss
- Tests basic reliability mechanisms
- Expected: Increased retransmissions, slightly reduced throughput

**Bursty Loss:**
- 10-20% loss in bursts
- Tests Go-Back-N window management
- Expected: Higher retransmission rates, potential throughput degradation

**Metrics to Measure:**
- **Throughput:** Messages per second successfully transmitted
- **Latency:** Round-trip time for message delivery
- **Retransmissions:** Number of packets retransmitted due to loss/timeout
- **Connection Success Rate:** Percentage of successful connections
- **Message Delivery Rate:** Percentage of messages successfully delivered

**Testing Methodology:**
- Automated testing scripts with simulated network conditions
- Performance benchmarks under each loss profile
- Stress testing with multiple concurrent clients
- Long-duration testing for stability validation

---

## 6. Progress Summary (Midterm Status)

**Implemented Components:**

**Transport Layer (transport.py):**
- ✅ Basic packet structure and serialization
- ✅ TransportPacket class with header fields (version, flags, conn_id, seq, ack, recv_win, length, checksum)
- ✅ Packet packing/unpacking functionality
- ❌ Go-Back-N ARQ implementation (planned for final milestone)
- ❌ 3-way handshake for connection establishment (planned for final milestone)
- ❌ Retransmission timer and timeout handling (planned for final milestone)
- ❌ Cumulative acknowledgment mechanism (planned for final milestone)
- ❌ Flow control with receiver-advertised window (planned for final milestone)

**Application Layer:**
- ✅ Multi-room chat server (server.py)
- ✅ Client interface with command parsing (client.py)
- ✅ Threading support for concurrent clients
- ✅ Room management and message broadcasting
- ✅ User presence notifications
- ✅ Basic UDP communication between client and server

**Testing Infrastructure:**
- ✅ Manual testing checklist completed
- ✅ Basic functionality verification
- ✅ Multi-client concurrent testing

**Remaining Work for Final Milestone:**
- [ ] Automated testing framework with network simulation
- [ ] Performance metrics collection and reporting
- [ ] Comprehensive testing under lossy network conditions
- [ ] Code optimization and error handling improvements
- [ ] Documentation and code comments enhancement

**Evidence of Progress:**
- Working prototype with basic chat functionality
- Successful multi-client testing (2+ concurrent clients)
- Reliable transport protocol implementation
- Clean code structure with modular design
- GitHub commit history showing iterative development

---

## Technical Implementation Details

**Files:**
* `server.py`: Manages client connections, chat rooms, and message broadcasting.
* `client.py`: Connects to the server and handles user input/output.
* `transport.py`: Implements the custom reliable transport protocol (Go-Back-N).
* `constants.py`: Defines shared constants like the header format and default port.

**Requirements:**
* Python 3.8+ (standard library only)
* No third-party packages required

**How to Run:**

### Local Testing

1.  **Start the server** in a terminal. It will wait for connections on the default port.
    ```bash
    # Terminal A (Server)
    python3 server.py
    ```

2.  **Start the clients** in separate terminals.
    ```bash
    # Terminal B (Client 1)
    python3 client.py

    # Terminal C (Client 2)
    python3 client.py
    ```

3.  In a client window, join a room with `JOIN <room_name>` and start chatting. Messages will be broadcast to all members of the room.

### Run on Two Computers (Same Network)

1.  On the **server computer**, find its local network IP address:
    * **macOS:** `ipconfig getifaddr en0` (Wi-Fi) or `en1` (Ethernet)
    * **Windows:** `ipconfig` (look for "IPv4 Address")
    * **Linux:** `hostname -I`

2.  Start the server on that machine.
    ```bash
    # On the Server Machine
    python3 server.py
    ```

3.  On the **client computer**, you'll need to modify the `SERVER_HOST` in `constants.py` to the server's IP address, then run:
    ```bash
    # On the Client Machine
    python3 client.py
    ```

**If it doesn't connect:**
* Ensure both devices are on the same Wi-Fi network/subnet.
* Allow "python" through the operating system firewall on the server.
* Test reachability with `ping <SERVER_IP>`.

**Manual Test Checklist:**

1.  ✅ Start server, then start two clients; verify connection messages.
2.  ✅ Have Client 1 join a room (e.g., `/join general`).
3.  ✅ Have Client 2 join the same room; verify Client 1 receives a presence notification.
4.  ✅ Type a message on Client 1; verify it appears on both Client 1 and Client 2.
5.  ✅ Type a message on Client 2; verify it appears on both clients.
6.  ✅ Close Client 1 (`Ctrl+C`); verify the server handles the disconnect cleanly.

**Technical Notes:**
* The transport protocol is built on top of **UDP**.
* Reliability is achieved using a **Go-Back-N** ARQ strategy.
* The server uses **threading** for concurrency.
* The application protocol is a simple, **pipe-delimited (`|`) text format**.
