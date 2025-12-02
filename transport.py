import socket
import struct
import threading
import time
import random
from constants import HEADER_FORMAT, HEADER_LEN, BUFFER_SIZE

# PARAMETERS
DEFAULT_WINDOW = 4
DEFAULT_TIMEOUT = 0.5  # SECONDS NEEDED

def checksum_bytes(data: bytes) -> int:
    """Simple 16-bit checksum (ones' complement sum)."""
    s = 0
    # IF LOOP FOR DATA
    if len(data) % 2 == 1:
        data = data + b'\x00'
    for i in range(0, len(data), 2):
        w = (data[i] << 8) + data[i+1]
        s += w
        s = (s & 0xffff) + (s >> 16)
    return (~s) & 0xffff

class TransportPacket:
    """Packet packing/unpacking with checksum verification."""
    def __init__(self, ver=1, flags=0, conn_id=0, seq=0, ack=0,
                 recv_win=0, length=0, checksum=0, payload=b''):
        self.ver = ver
        self.flags = flags
        self.conn_id = conn_id
        self.seq = seq
        self.ack = ack
        self.recv_win = recv_win
        self.length = length if length else len(payload)
        self.checksum = checksum
        self.payload = payload

    def pack(self):
        # SELF PARAMETERS
        header_without_checksum = struct.pack(
            HEADER_FORMAT,
            self.ver,
            self.flags,
            self.conn_id,
            self.seq,
            self.ack,
            self.recv_win,
            self.length,
            0
        )
        ch = checksum_bytes(header_without_checksum + self.payload) & 0xffffffff
        # STORING 32-BIT PAYLOAD
        header = struct.pack(
            HEADER_FORMAT,
            self.ver,
            self.flags,
            self.conn_id,
            self.seq,
            self.ack,
            self.recv_win,
            self.length,
            ch
        )
        return header + self.payload

    @staticmethod
    def unpack(data: bytes):
        if len(data) < HEADER_LEN:
            raise ValueError("packet too small")
        header = data[:HEADER_LEN]
        payload = data[HEADER_LEN:]
        ver, flags, conn_id, seq, ack, recv_win, length, ch = struct.unpack(HEADER_FORMAT, header)
        # CHECKSUM
        header_zero_ch = struct.pack(
            HEADER_FORMAT,
            ver, flags, conn_id, seq, ack, recv_win, length, 0
        )
        calc = checksum_bytes(header_zero_ch + payload) & 0xffffffff
        if calc != ch:
            raise ValueError("checksum mismatch")
        return TransportPacket(ver, flags, conn_id, seq, ack, recv_win, length, ch, payload)

    def __repr__(self):
        return f"TP(seq={self.seq}, ack={self.ack}, flags={self.flags}, len={self.length})"


class GBNTransport:
    def __init__(self, local_addr=None, window_size=DEFAULT_WINDOW, timeout=DEFAULT_TIMEOUT,
                 loss_prob=0.0):
        """
        local_addr: (host, port) to bind to. If None, bind to ('0.0.0.0', 0) ephemeral.
        loss_prob: simulate packet loss (0.0..1.0) for outgoing packets (useful for testing).
        """
        if local_addr is None:
            local_addr = ("0.0.0.0", 0)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)
        self.sock.settimeout(0.1)
        self.window = window_size
        self.timeout = timeout
        self.lock = threading.Lock()

        # SENDER
        self.base = 1
        self.nextseq = 1
        self.send_buffer = {}
        self.timer = None
        self.timer_start = None

        self.expected = {}

        # REACHED
        self.app_queue = []
        self.app_cv = threading.Condition()

        self.loss_prob = loss_prob

        self._stop = False
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()

    def _start_timer(self):
        self.timer_start = time.time()

    def _stop_timer(self):
        self.timer_start = None

    def _timer_expired(self):
        if self.timer_start is None:
            return False
        return (time.time() - self.timer_start) >= self.timeout

    def _send_raw(self, data: bytes, addr):
        if self.loss_prob and random.random() < self.loss_prob:
            return
        self.sock.sendto(data, addr)

    def send(self, payload: bytes, addr):
        """
        Reliable send of a payload to addr using GBN. Non-blocking wrt other callers,
        but may block if window is full until base advances.
        """
        while True:
            with self.lock:
                if self.nextseq < self.base + self.window:
                    seq = self.nextseq
                    # PACKET
                    pkt = TransportPacket(seq=seq, ack=0, payload=payload)
                    pkt_bytes = pkt.pack()
                    # STORING
                    self.send_buffer[seq] = [pkt_bytes, addr, time.time()]
                    self._send_raw(pkt_bytes, addr)
                    if self.base == self.nextseq:
                        # BEGINNING TIMER
                        self._start_timer()
                    self.nextseq += 1
                    return seq
            time.sleep(0.01)

    def _handle_ack(self, ack_num):
        with self.lock:
            if ack_num >= self.base:
                # + 1
                # REMOVING OF KEYS FROM BUFFER, IF LOOP
                keys = [k for k in self.send_buffer.keys() if k <= ack_num]
                for k in keys:
                    self.send_buffer.pop(k, None)
                self.base = ack_num + 1
                if self.base == self.nextseq:
                    # STOP BEGINNING TIMER
                    self._stop_timer()
                else:
                    # RESET/RESTART TIMER
                    self._start_timer()

    def _recv_loop(self):
        """Background thread: receive packets, handle ACKs and deliver data."""
        while not self._stop:
            try:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                data = None
            except Exception:
                continue

            if data:
                try:
                    pkt = TransportPacket.unpack(data)
                except Exception:
                    continue

                # IF PACKET = ACK
                if pkt.ack != 0 and pkt.payload == b'':
                    # KEEP PACKET AS ACK NUMBER
                    try:
                        ack_num = pkt.ack
                        self._handle_ack(ack_num)
                    except Exception:
                        pass
                    continue

                # DATA IN PACKET EXPECTED IF LOOP
                exp = self.expected.get(addr, 1)
                if pkt.seq == exp:
                    # DELIVERABLE
                    with self.app_cv:
                        self.app_queue.append((pkt.payload, addr))
                        self.app_cv.notify()
                    self.expected[addr] = exp + 1
                    ack_pkt = TransportPacket(seq=0, ack=pkt.seq, payload=b'')
                    self._send_raw(ack_pkt.pack(), addr)
                else:
                    ack_pkt = TransportPacket(seq=0, ack=exp-1 if exp>1 else 0, payload=b'')
                    self._send_raw(ack_pkt.pack(), addr)

            # TIMER SELF.LOCK
            with self.lock:
                if self._timer_expired():
                    for seq in sorted(self.send_buffer.keys()):
                        pkt_bytes, addr, ts = self.send_buffer[seq]
                        self._send_raw(pkt_bytes, addr)
                    self._start_timer()

    def recv(self, timeout=None):
        """
        Blocking receive to get next application payload.
        If timeout not None, returns None on timeout.
        Returns (payload_bytes, addr)
        """
        with self.app_cv:
            if timeout is None:
                while not self.app_queue:
                    self.app_cv.wait()
            else:
                end = time.time() + timeout
                while not self.app_queue:
                    remaining = end - time.time()
                    if remaining <= 0:
                        return None
                    self.app_cv.wait(timeout=remaining)
            return self.app_queue.pop(0)

    def close(self):
        self._stop = True
        self.recv_thread.join(timeout=1.0)
        try:
            self.sock.close()
        except:
            pass

    def local_addr(self):
        return self.sock.getsockname()
