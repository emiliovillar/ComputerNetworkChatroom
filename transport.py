import socket
import threading
import time
import random
import struct
from constants import HEADER_FORMAT, HEADER_LEN, ACK, SYN, FIN

# ----------------------------------------------------------------------
# Loss simulation (for testing only)
# ----------------------------------------------------------------------
LOSS_PROFILE = "bursty"   # "clean", "random", or "bursty"

# Used when LOSS_PROFILE == "random"
RANDOM_LOSS_PROB = 0.08  # ~8% loss (within 5–10%)

# Used when LOSS_PROFILE == "bursty"
BURSTY_BASE_LOSS = 0.02      # small background loss
BURSTY_BURST_LOSS = 0.25     # loss probability during a burst
BURSTY_BURST_CHANCE = 0.10   # chance that a new packet starts/continues a burst
BURSTY_MIN_LEN = 3           # min packets in a burst
BURSTY_MAX_LEN = 8           # max packets in a burst

_burst_active = False
_burst_remaining = 0


def maybe_drop_packet():
    """
    Returns True if this packet should be dropped (simulated loss).
    """
    global _burst_active, _burst_remaining

    if LOSS_PROFILE == "clean":
        return False

    r = random.random()

    if LOSS_PROFILE == "random":
        return r < RANDOM_LOSS_PROB

    elif LOSS_PROFILE == "bursty":
        # If currently in a burst, use high loss prob
        if _burst_active:
            _burst_remaining -= 1
            if _burst_remaining <= 0:
                _burst_active = False
            return r < BURSTY_BURST_LOSS

        # Outside a burst: small base loss
        if r < BURSTY_BASE_LOSS:
            return True

        # Chance to start a new burst
        if r < BURSTY_BURST_CHANCE:
            _burst_active = True
            _burst_remaining = random.randint(BURSTY_MIN_LEN, BURSTY_MAX_LEN)
            return r < BURSTY_BURST_LOSS

        return False

    return False


# ----------------------------------------------------------------------
# Go-Back-N parameters
# ----------------------------------------------------------------------
WINDOW_SIZE = 5
TIMEOUT = 0.5  # seconds


class TransportConnection:
    """Implements Go-Back-N ARQ for reliable transport."""
    def __init__(self, local_addr, remote_addr, on_message, is_server=False):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)
        self.remote_addr = remote_addr
        self.on_message = on_message
        self.is_server = is_server

        # Sender-side state
        self.send_base = 0
        self.next_seq_num = 0
        self.window_size = WINDOW_SIZE
        # seq_num -> (packet, send_time)
        self.unacked_packets = {}
        self.timer = None
        self.lock = threading.Lock()

        # Receiver-side state
        self.expected_seq_num = 0
        self.recv_buffer_size = 10
        self.recv_buffer = []
        self.recv_win = self.recv_buffer_size
        self.peer_recv_win = WINDOW_SIZE

        # Connection + control
        self.conn_id = 0
        self.connected = False
        self.running = True

        # --- Metrics ---
        self.metrics_lock = threading.Lock()
        self.metrics = {
            "start_time": None,           # first data send OR first delivery (depends on side)
            "end_time": None,             # last delivery to app
            "bytes_sent": 0,              # payload bytes (original sends)
            "bytes_resent": 0,            # payload bytes in retransmissions
            "bytes_delivered": 0,         # payload bytes delivered to app
            "messages_sent": 0,           # app-level messages sent
            "messages_delivered": 0,      # app-level messages delivered
            "retransmissions": 0,         # total retransmitted packets
            "ooo_packets": 0,             # out-of-order packets seen
            "rtt_samples": [],            # RTT samples (sec)
        }

        threading.Thread(target=self._recv_loop, daemon=True).start()

    # ------------------------------------------------------------------
    # Internal helper: send with optional loss simulation
    # ------------------------------------------------------------------

    def _sendto(self, data: bytes, addr):
        """
        Wrapper around socket.sendto that can simulate packet loss.
        """
        if not maybe_drop_packet():
            self.sock.sendto(data, addr)

    # ------------------------------------------------------------------
    # Connection Management
    # ------------------------------------------------------------------

    def connect(self):
        """Initiate a connection using three-way handshake (client side)."""
        self.conn_id = random.randint(1, 65535)
        syn_pkt = TransportPacket(flags=SYN, conn_id=self.conn_id, seq=0, recv_win=self.recv_win)
        self._sendto(syn_pkt.pack(), self.remote_addr)

        # Wait for connection to be established by _recv_loop
        timeout = 5.0
        start_time = time.time()
        while not self.connected and (time.time() - start_time) < timeout:
            time.sleep(0.01)

        if not self.connected:
            raise TimeoutError("Connection handshake timed out")

    def _handle_handshake(self, pkt, addr):
        """Server-side and client-side handshake logic."""
        # Incoming SYN (from client)
        if (pkt.flags & SYN) and not (pkt.flags & ACK):
            self.conn_id = pkt.conn_id
            if self.remote_addr is None:
                self.remote_addr = addr
            self.peer_recv_win = pkt.recv_win if pkt.recv_win > 0 else 1
            syn_ack_pkt = TransportPacket(
                flags=SYN | ACK,
                conn_id=pkt.conn_id,
                seq=0,
                ack=pkt.seq + 1,
                recv_win=self.recv_win,
            )
            self._sendto(syn_ack_pkt.pack(), addr)

        # Final ACK of three-way handshake (client receives SYN-ACK and sends ACK)
        elif (pkt.flags & ACK) and not (pkt.flags & SYN) and pkt.conn_id == self.conn_id:
            self.peer_recv_win = pkt.recv_win if pkt.recv_win > 0 else 1
            self.connected = True

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send_msg(self, data: bytes):
        """Send an application message reliably using Go-Back-N."""
        with self.lock:
            effective_window = min(self.window_size, self.peer_recv_win)

            if self.next_seq_num < self.send_base + effective_window:
                pkt = TransportPacket(
                    seq=self.next_seq_num,
                    ack=0,
                    payload=data,
                    conn_id=self.conn_id,
                    recv_win=self.recv_win,
                )

                now = time.time()
                # Metrics: record first send time and bytes/messages sent
                with self.metrics_lock:
                    if self.metrics["start_time"] is None:
                        self.metrics["start_time"] = now
                    self.metrics["bytes_sent"] += len(data)
                    self.metrics["messages_sent"] += 1

                self._sendto(pkt.pack(), self.remote_addr)
                self.unacked_packets[self.next_seq_num] = (pkt, now)

                if self.send_base == self.next_seq_num:
                    self._start_timer()
                self.next_seq_num += 1

    def _start_timer(self):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(TIMEOUT, self._timeout)
        self.timer.start()

    def _timeout(self):
        """Timeout handler for Go-Back-N: retransmit the entire window."""
        with self.lock:
            for seq in range(self.send_base, self.next_seq_num):
                pkt, _ = self.unacked_packets.get(seq, (None, None))
                if pkt:
                    self._sendto(pkt.pack(), self.remote_addr)
                    # Metrics: retransmission + bytes_resent
                    with self.metrics_lock:
                        self.metrics["retransmissions"] += 1
                        self.metrics["bytes_resent"] += len(pkt.payload)
            self._start_timer()

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    def _recv_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                pkt = TransportPacket.unpack(data)

                # Handshake handling
                if pkt.flags & SYN:
                    if self.is_server:
                        self._handle_handshake(pkt, addr)
                    else:
                        # Client receiving SYN-ACK
                        if (pkt.flags & ACK) and pkt.conn_id == self.conn_id and not self.connected:
                            self.peer_recv_win = pkt.recv_win if pkt.recv_win > 0 else 1
                            ack_pkt = TransportPacket(
                                flags=ACK,
                                conn_id=self.conn_id,
                                seq=1,
                                ack=pkt.seq + 1,
                                recv_win=self.recv_win,
                            )
                            self._sendto(ack_pkt.pack(), addr)
                            self.connected = True
                    continue

                # FIN: remote side closing
                if pkt.flags & FIN:
                    self.running = False
                    break

                # Ignore data/ACK until handshake done (client side)
                if not self.connected and not self.is_server:
                    continue

                # Data packet
                if pkt.payload:
                    if pkt.seq == self.expected_seq_num:
                        # In-order delivery to application
                        self.on_message(pkt.payload)
                        self.expected_seq_num += 1
                        self.recv_win = self.recv_buffer_size

                        # Metrics: bytes + messages delivered, update start/end time
                        with self.metrics_lock:
                            if self.metrics["start_time"] is None:
                                self.metrics["start_time"] = time.time()
                            self.metrics["bytes_delivered"] += len(pkt.payload)
                            self.metrics["messages_delivered"] += 1
                            self.metrics["end_time"] = time.time()

                    elif pkt.seq > self.expected_seq_num:
                        # Out-of-order packet (dropped but counted)
                        with self.metrics_lock:
                            self.metrics["ooo_packets"] += 1

                    # Send ACK for highest in-order seq we've seen
                    ack_pkt = TransportPacket(
                        seq=0,
                        ack=self.expected_seq_num,
                        flags=ACK,
                        conn_id=self.conn_id,
                        recv_win=self.recv_win,
                    )
                    self._sendto(ack_pkt.pack(), self.remote_addr if self.remote_addr else addr)

                # ACK processing (advance window)
                if pkt.ack > self.send_base:
                    now = time.time()
                    with self.lock:
                        self.peer_recv_win = pkt.recv_win if pkt.recv_win > 0 else 1

                        for seq in range(self.send_base, pkt.ack):
                            pkt_obj, send_time = self.unacked_packets.pop(seq, (None, None))
                            if pkt_obj is not None and send_time is not None:
                                rtt = now - send_time
                                with self.metrics_lock:
                                    self.metrics["rtt_samples"].append(rtt)

                        self.send_base = pkt.ack
                        if self.send_base == self.next_seq_num:
                            if self.timer:
                                self.timer.cancel()
                                self.timer = None
                        else:
                            self._start_timer()
            except Exception:
                # swallow errors to keep background thread alive
                continue

    # ------------------------------------------------------------------
    # Closing + Metrics API
    # ------------------------------------------------------------------

    def close(self):
        if self.connected:
            fin_pkt = TransportPacket(flags=FIN, conn_id=self.conn_id, seq=self.next_seq_num)
            self._sendto(fin_pkt.pack(), self.remote_addr)

        # Metrics: if we never set end_time but had a start_time, close it out
        with self.metrics_lock:
            if self.metrics["end_time"] is None and self.metrics["start_time"] is not None:
                self.metrics["end_time"] = time.time()

        self.running = False
        self.connected = False
        if self.timer:
            self.timer.cancel()
        self.sock.close()

    def get_metrics(self):
        """Return raw counters plus derived metrics (goodput, latency stats, retrans per KB)."""
        with self.metrics_lock:
            m = dict(self.metrics)  # shallow copy
            rtts = list(m["rtt_samples"])

        duration = None
        if m["start_time"] is not None and m["end_time"] is not None and m["end_time"] > m["start_time"]:
            duration = m["end_time"] - m["start_time"]

        goodput_bps = None
        if duration and duration > 0:
            # Goodput = delivered payload bits / second
            goodput_bps = (m["bytes_delivered"] * 8.0) / duration

        avg_rtt = None
        p95_rtt = None
        if rtts:
            rtts_sorted = sorted(rtts)
            avg_rtt = sum(rtts_sorted) / len(rtts_sorted)
            idx = int(0.95 * len(rtts_sorted)) - 1
            if idx < 0:
                idx = 0
            p95_rtt = rtts_sorted[idx]

        retrans_per_kb = None
        if m["bytes_sent"] > 0:
            kb = m["bytes_sent"] / 1024.0
            if kb > 0:
                retrans_per_kb = m["retransmissions"] / kb

        return {
            **m,
            "duration_sec": duration,
            "goodput_bps": goodput_bps,
            "avg_rtt_sec": avg_rtt,
            "p95_rtt_sec": p95_rtt,
            "retransmissions_per_kb": retrans_per_kb,
        }


class TransportPacket:
    def __init__(self, ver=1, flags=0, conn_id=0, seq=0, ack=0,
                 recv_win=0, length=0, checksum=0, payload=b''):
        self.ver = ver
        self.flags = flags
        self.conn_id = conn_id
        self.seq = seq
        self.ack = ack
        self.recv_win = recv_win
        self.payload = payload
        self.len = len(self.payload)
        self.checksum = checksum

    def compute_checksum(self):
        header = struct.pack(
            HEADER_FORMAT,
            self.ver,
            self.flags,
            self.conn_id,
            self.seq,
            self.ack,
            self.recv_win,
            self.len,
            0
        )
        return sum(header + self.payload) % (2 ** 32)

    def pack(self):
        self.len = len(self.payload)
        self.checksum = self.compute_checksum()
        return struct.pack(
            HEADER_FORMAT,
            self.ver,
            self.flags,
            self.conn_id,
            self.seq,
            self.ack,
            self.recv_win,
            self.len,
            self.checksum
        ) + self.payload

    @staticmethod
    def verify_checksum(ver, flags, conn_id, seq, ack, recv_win, length, checksum, payload):
        temp_packet = TransportPacket(ver, flags, conn_id, seq, ack, recv_win, length, 0, payload)
        computed = temp_packet.compute_checksum()
        return computed == checksum

    @staticmethod
    def unpack(data):
        if len(data) < HEADER_LEN:
            raise ValueError("Packet too small")

        ver, flags, conn_id, seq, ack, recv_win, length, checksum = struct.unpack(
            HEADER_FORMAT, data[:HEADER_LEN]
        )
        payload = data[HEADER_LEN:]

        if not TransportPacket.verify_checksum(ver, flags, conn_id, seq, ack, recv_win, length, checksum, payload):
            raise ValueError("Checksum failed")

        return TransportPacket(ver, flags, conn_id, seq, ack, recv_win, length, checksum, payload)

    def __repr__(self):
        payload_str = self.payload.decode('utf-8', 'ignore')
        return f"TransportPacket(seq={self.seq}, ack={self.ack}, flags={bin(self.flags)}, payload='{payload_str}')"
