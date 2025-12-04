import socket
import threading
import time
import random
import struct
from constants import HEADER_FORMAT, HEADER_LEN, ACK, SYN, FIN

# Loss simulation (for testing)
LOSS_PROFILE = "clean"  # "clean", "random", or "bursty"


RANDOM_LOSS_PROB = 0.08


BURSTY_BASE_LOSS = 0.02
BURSTY_BURST_LOSS = 0.25
BURSTY_BURST_CHANCE = 0.10
BURSTY_MIN_LEN = 3
BURSTY_MAX_LEN = 8

_burst_active = False
_burst_remaining = 0


def maybe_drop_packet():
    """Returns True if packet should be dropped (for testing)"""
    global _burst_active, _burst_remaining

    if LOSS_PROFILE == "clean":
        return False

    r = random.random()

    if LOSS_PROFILE == "random":
        return r < RANDOM_LOSS_PROB

    elif LOSS_PROFILE == "bursty":
        # Inside burst - use high loss probability
        if _burst_active:
            _burst_remaining -= 1
            if _burst_remaining <= 0:
                _burst_active = False
            return r < BURSTY_BURST_LOSS

        # Outside burst - use base loss
        if r < BURSTY_BASE_LOSS:
            return True

        # Randomly start new burst
        if r < BURSTY_BURST_CHANCE:
            _burst_active = True
            _burst_remaining = random.randint(BURSTY_MIN_LEN, BURSTY_MAX_LEN)
            return r < BURSTY_BURST_LOSS

        return False

    return False


# Go-Back-N parameters
WINDOW_SIZE = 5
TIMEOUT = 0.5


class TransportConnection:
    """Go-Back-N reliable transport with flow control and handshake"""
    def __init__(self, local_addr, remote_addr, on_message, is_server=False):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)
        self.remote_addr = remote_addr
        self.on_message = on_message  # callback for received data
        self.is_server = is_server

        # Sender state
        self.send_base = 0  # oldest unacked seq
        self.next_seq_num = 0  # next seq to send
        self.window_size = WINDOW_SIZE
        self.unacked_packets = {}  # seq -> (packet, send_time)
        self.timer = None
        self.lock = threading.Lock()

        # Receiver state
        self.expected_seq_num = 0
        self.recv_win = 10
        self.peer_recv_win = WINDOW_SIZE

        # Connection state
        self.conn_id = 0
        self.connected = False
        self.running = True

        # Metrics
        self.metrics_lock = threading.Lock()
        self.metrics = {
            "start_time": None,
            "end_time": None,
            "bytes_sent": 0,
            "bytes_resent": 0,
            "bytes_delivered": 0,
            "messages_sent": 0,
            "messages_delivered": 0,
            "retransmissions": 0,
            "ooo_packets": 0,
            "rtt_samples": [],
        }

        # Start background receiver thread
        threading.Thread(target=self._recv_loop, daemon=True).start()



    def _sendto(self, data: bytes, addr):
        """Send packet with simulated loss (for testing)"""
        if not maybe_drop_packet():
            self.sock.sendto(data, addr)

    def connect(self):
        """Client-side three-way handshake"""
        # Generate random connection ID
        self.conn_id = random.randint(1, 65535)
        # Send SYN packet
        syn_pkt = TransportPacket(flags=SYN, conn_id=self.conn_id, seq=0, recv_win=self.recv_win)
        self._sendto(syn_pkt.pack(), self.remote_addr)

        # Wait for handshake to complete
        timeout = 5.0
        start_time = time.time()
        while not self.connected and (time.time() - start_time) < timeout:
            time.sleep(0.01)

        if not self.connected:
            raise TimeoutError("Connection handshake timed out")

    def _handle_handshake(self, pkt, addr):
        """Process handshake packets (SYN, SYN-ACK, ACK)"""
        # Server receives SYN
        if (pkt.flags & SYN) and not (pkt.flags & ACK):
            self.conn_id = pkt.conn_id
            if self.remote_addr is None:
                self.remote_addr = addr
            self.peer_recv_win = pkt.recv_win
            syn_ack_pkt = TransportPacket(
                flags=SYN | ACK,
                conn_id=pkt.conn_id,
                seq=0,
                ack=pkt.seq + 1,
                recv_win=self.recv_win,
            )
            self._sendto(syn_ack_pkt.pack(), addr)

        # Client receives final ACK
        elif (pkt.flags & ACK) and not (pkt.flags & SYN) and pkt.conn_id == self.conn_id:
            self.peer_recv_win = pkt.recv_win
            self.connected = True

    def send_msg(self, data: bytes):
        """Send message using Go-Back-N sliding window"""
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
        """Start/restart retransmission timer"""
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(TIMEOUT, self._timeout)
        self.timer.start()

    def _timeout(self):
        """Retransmit all unacked packets (Go-Back-N)"""
        with self.lock:
            for seq in range(self.send_base, self.next_seq_num):
                pkt, _ = self.unacked_packets.get(seq, (None, None))
                if pkt:
                    self._sendto(pkt.pack(), self.remote_addr)
                    self.metrics["retransmissions"] += 1
                    self.metrics["bytes_resent"] += len(pkt.payload)
            self._start_timer()

    def _recv_loop(self):
        """Background thread for receiving packets"""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                pkt = TransportPacket.unpack(data)

                # Handle handshake packets
                if pkt.flags & SYN:
                    if self.is_server:
                        self._handle_handshake(pkt, addr)
                    else:
                        # Client receives SYN-ACK
                        if (pkt.flags & ACK) and pkt.conn_id == self.conn_id and not self.connected:
                            self.peer_recv_win = pkt.recv_win
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

                #  (connection close)
                if pkt.flags & FIN:
                    self.running = False
                    break

                #  ignore packets before handshake completes
                if not self.connected and not self.is_server:
                    continue

                # Handle data packets
                if pkt.payload:
                    if pkt.seq == self.expected_seq_num:
                        self.on_message(pkt.payload)
                        self.expected_seq_num += 1
                        
                        if self.metrics["start_time"] is None:
                            self.metrics["start_time"] = time.time()
                        self.metrics["bytes_delivered"] += len(pkt.payload)
                        self.metrics["messages_delivered"] += 1
                        self.metrics["end_time"] = time.time()

                    elif pkt.seq > self.expected_seq_num:
                        self.metrics["ooo_packets"] += 1

                    ack_pkt = TransportPacket(
                        seq=0,
                        ack=self.expected_seq_num,
                        flags=ACK,
                        conn_id=self.conn_id,
                        recv_win=self.recv_win,
                    )
                    self._sendto(ack_pkt.pack(), addr)

                # Handle ACKs
                if pkt.ack > self.send_base:
                    now = time.time()
                    with self.lock:
                        self.peer_recv_win = pkt.recv_win

                        for seq in range(self.send_base, pkt.ack):
                            pkt_obj, send_time = self.unacked_packets.pop(seq, (None, None))
                            if pkt_obj and send_time:
                                self.metrics["rtt_samples"].append(now - send_time)

                        self.send_base = pkt.ack
                        if self.send_base == self.next_seq_num:
                            if self.timer:
                                self.timer.cancel()
                                self.timer = None
                        else:
                            self._start_timer()
            except Exception:
                continue

    def close(self):
        if self.connected:
            fin_pkt = TransportPacket(flags=FIN, conn_id=self.conn_id, seq=self.next_seq_num)
            self._sendto(fin_pkt.pack(), self.remote_addr)

        if self.metrics["end_time"] is None and self.metrics["start_time"]:
            self.metrics["end_time"] = time.time()

        self.running = False
        self.connected = False
        if self.timer:
            self.timer.cancel()
        self.sock.close()

    def get_metrics(self):
        m = dict(self.metrics)
        rtts = list(m["rtt_samples"])

        duration = None
        if m["start_time"] and m["end_time"] and m["end_time"] > m["start_time"]:
            duration = m["end_time"] - m["start_time"]

        goodput_bps = None
        goodput_msg_sec = None
        if duration:
            goodput_bps = (m["bytes_delivered"] * 8.0) / duration
            goodput_msg_sec = m["messages_delivered"] / duration

        avg_rtt = None
        p95_rtt = None
        if rtts:
            rtts_sorted = sorted(rtts)
            avg_rtt = sum(rtts_sorted) / len(rtts_sorted)
            p95_rtt = rtts_sorted[int(0.95 * len(rtts_sorted)) - 1]

        retrans_per_kb = None
        if m["bytes_sent"]:
            retrans_per_kb = m["retransmissions"] / (m["bytes_sent"] / 1024.0)

        return {
            **m,
            "duration_sec": duration,
            "goodput_bps": goodput_bps,
            "goodput_msg_sec": goodput_msg_sec,
            "avg_rtt_sec": avg_rtt,
            "p95_rtt_sec": p95_rtt,
            "retransmissions_per_kb": retrans_per_kb,
        }


class TransportPacket:
    def __init__(self, ver=1, flags=0, conn_id=0, seq=0, ack=0,
                 recv_win=0, checksum=0, payload=b''):
        self.ver = ver
        self.flags = flags
        self.conn_id = conn_id
        self.seq = seq
        self.ack = ack
        self.recv_win = recv_win
        self.payload = payload
        self.len = len(payload)
        self.checksum = checksum

    def compute_checksum(self):
        header = struct.pack(HEADER_FORMAT, self.ver, self.flags, self.conn_id,
                           self.seq, self.ack, self.recv_win, self.len, 0)
        return sum(header + self.payload) % (2 ** 32)

    def pack(self):
        self.len = len(self.payload)
        self.checksum = self.compute_checksum()
        return struct.pack(HEADER_FORMAT, self.ver, self.flags, self.conn_id,
                          self.seq, self.ack, self.recv_win, self.len, 
                          self.checksum) + self.payload

    @staticmethod
    def unpack(data):
        if len(data) < HEADER_LEN:
            raise ValueError("Packet too small")

        ver, flags, conn_id, seq, ack, recv_win, _, checksum = struct.unpack(
            HEADER_FORMAT, data[:HEADER_LEN]
        )
        payload = data[HEADER_LEN:]

        temp = TransportPacket(ver, flags, conn_id, seq, ack, recv_win, checksum, payload)
        if temp.compute_checksum() != checksum:
            raise ValueError("Checksum failed")

        return temp

    def __repr__(self):
        payload_str = self.payload.decode('utf-8', 'ignore')
        return f"TransportPacket(seq={self.seq}, ack={self.ack}, flags={bin(self.flags)}, payload='{payload_str}')"
