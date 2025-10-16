# Custom Transport Protocol & Chat Service (Python)

This project implements a reliable transport protocol over UDP from scratch and a multi-client chat application that uses it. The transport layer's reliability, connection management, and flow control are built without using standard TCP sockets. The application layer provides a multi-room chat server capable of handling concurrent clients.

---

## Files
* `server.py`: Manages client connections, chat rooms, and message broadcasting.
* `client.py`: Connects to the server and handles user input/output.
* `transport.py`: Implements the custom reliable transport protocol (Go-Back-N).
* `constants.py`: Defines shared constants like the header format and default port.

---

## Requirements
* Python 3.8+ (standard library only)
* No third-party packages required

---

## How to Run

### Local Testing

1.  **Start the server** in a terminal. It will wait for connections on the default port.
    ```bash
    # Terminal A (Server)
    python3 server.py
    ```

2.  **Start the clients** in separate terminals. Each client needs a unique name.
    ```bash
    # Terminal B (Client 1)
    python3 client.py --name Alice

    # Terminal C (Client 2)
    python3 client.py --name Bob
    ```

3.  In a client window, join a room with `/join <room_name>` and start chatting. Messages will be broadcast to all members of the room.

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

3.  On the **client computer**, connect using the server's IP and port.
    ```bash
    # On the Client Machine
    python3 client.py --server <SERVER_IP> --name <your_name>
    ```
    > **Example:** `python3 client.py --server 192.168.1.15 --name Carol`

**If it doesn't connect:**
* Ensure both devices are on the same Wi-Fi network/subnet.
* Allow "python" through the operating system firewall on the server.
* Test reachability with `ping <SERVER_IP>`.

---

## Tasks

This project can be broken down into the following implementation stages.

* **Stage 1: Foundation & Packet Definition**
    * Define the protocol header in `constants.py`.
    * Implement a `TransportPacket` class in `transport.py` to serialize and deserialize packets.
    * Establish basic, unreliable UDP communication between the client and server.

* **Stage 2: Reliability (Go-Back-N)**
    * Implement the 3-way handshake (`SYN`, `SYN-ACK`, `ACK`) for connection management.
    * Implement sender-side GBN logic: send window, retransmission timers, and ACK handling.
    * Implement receiver-side GBN logic: cumulative ACKs and handling of out-of-order packets.
    * Integrate flow control using the receiver-advertised window.

* **Stage 3: Application Layer**
    * Implement server logic for managing rooms and broadcasting messages.
    * Use threading in the server to handle multiple clients concurrently.
    * Build the client-side user interface for sending commands and displaying messages.

* **Stage 4: Testing & Metrics**
    * Test the system thoroughly under simulated network loss.
    * Implement code to collect and report required metrics (latency, goodput, retransmissions).
    * Add graceful shutdown logic and polish user-facing messages.

---

## Manual Test Checklist

1.  ✅ Start server, then start two clients; verify connection messages.
2.  ✅ Have Client 1 join a room (e.g., `/join general`).
3.  ✅ Have Client 2 join the same room; verify Client 1 receives a presence notification.
4.  ✅ Type a message on Client 1; verify it appears on both Client 1 and Client 2.
5.  ✅ Type a message on Client 2; verify it appears on both clients.
6.  ✅ Close Client 1 (`Ctrl+C`); verify the server handles the disconnect cleanly.

---

## Notes
* The transport protocol is built on top of **UDP**.
* Reliability is achieved using a **Go-Back-N** ARQ strategy.
* The server uses **threading** for concurrency.
* The application protocol is a simple, **pipe-delimited (`|`) text format**.
