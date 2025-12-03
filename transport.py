import socket
import threading
import time
import random
import struct
from constants import HEADER_FORMAT, HEADER_LEN, ACK, SYN, FIN

# Go-Back-N parameters
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

        self.send_base = 0
        self.next_seq_num = 0
        self.window_size = WINDOW_SIZE
        self.unacked_packets = {}
        self.timer = None
        self.lock = threading.Lock()

        self.expected_seq_num = 0
        self.recv_buffer_size = 10
        self.recv_buffer = []
        self.recv_win = self.recv_buffer_size
        self.peer_recv_win = WINDOW_SIZE
        self.conn_id = 0
        self.connected = False
        self.running = True
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def connect(self):
        """Initiate a connection using three-way handshake (client side)."""
        self.conn_id = random.randint(1, 65535)
        syn_pkt = TransportPacket(flags=SYN, conn_id=self.conn_id, seq=0, recv_win=self.recv_win)
        self.sock.sendto(syn_pkt.pack(), self.remote_addr)
        
        # Wait for connection to be established by _recv_loop
        timeout = 5.0
        start_time = time.time()
        while not self.connected and (time.time() - start_time) < timeout:
            time.sleep(0.01)
        
        if not self.connected:
            raise TimeoutError("Connection handshake timed out")

    def _handle_handshake(self, pkt, addr):
        if (pkt.flags & SYN) and not (pkt.flags & ACK):
            self.conn_id = pkt.conn_id
            if self.remote_addr is None:
                self.remote_addr = addr
            self.peer_recv_win = pkt.recv_win if pkt.recv_win > 0 else 1
            syn_ack_pkt = TransportPacket(flags=SYN|ACK, conn_id=pkt.conn_id, seq=0, ack=pkt.seq+1, recv_win=self.recv_win)
            self.sock.sendto(syn_ack_pkt.pack(), addr)
        elif (pkt.flags & ACK) and not (pkt.flags & SYN) and pkt.conn_id == self.conn_id:
            self.peer_recv_win = pkt.recv_win if pkt.recv_win > 0 else 1
            self.connected = True

    def send_msg(self, data):
        with self.lock:
            effective_window = min(self.window_size, self.peer_recv_win)
            
            if self.next_seq_num < self.send_base + effective_window:
                pkt = TransportPacket(
                    seq=self.next_seq_num, 
                    ack=0, 
                    payload=data, 
                    conn_id=self.conn_id,
                    recv_win=self.recv_win
                )
                self.sock.sendto(pkt.pack(), self.remote_addr)
                self.unacked_packets[self.next_seq_num] = (pkt, time.time())
                if self.send_base == self.next_seq_num:
                    self._start_timer()
                self.next_seq_num += 1

    def _start_timer(self):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(TIMEOUT, self._timeout)
        self.timer.start()

    def _timeout(self):
        with self.lock:
            for seq in range(self.send_base, self.next_seq_num):
                pkt, _ = self.unacked_packets.get(seq, (None, None))
                if pkt:
                    self.sock.sendto(pkt.pack(), self.remote_addr)
            self._start_timer()

    def _recv_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                pkt = TransportPacket.unpack(data)

                if pkt.flags & SYN:
                    if self.is_server:
                        self._handle_handshake(pkt, addr)
                    else:
                        if (pkt.flags & ACK) and pkt.conn_id == self.conn_id and not self.connected:
                            self.peer_recv_win = pkt.recv_win if pkt.recv_win > 0 else 1
                            ack_pkt = TransportPacket(flags=ACK, conn_id=self.conn_id, seq=1, ack=pkt.seq+1, recv_win=self.recv_win)
                            self.sock.sendto(ack_pkt.pack(), addr)
                            self.connected = True
                    continue

                if pkt.flags & FIN:
                    self.running = False
                    break

                if not self.connected and not self.is_server:
                    continue

                if pkt.payload:
                    if pkt.seq == self.expected_seq_num:
                        self.on_message(pkt.payload)
                        self.expected_seq_num += 1
                        self.recv_win = self.recv_buffer_size
                    
                    ack_pkt = TransportPacket(
                        seq=0, 
                        ack=self.expected_seq_num, 
                        flags=ACK, 
                        conn_id=self.conn_id,
                        recv_win=self.recv_win
                    )
                    self.sock.sendto(ack_pkt.pack(), self.remote_addr if self.remote_addr else addr)

                if pkt.ack > self.send_base:
                    with self.lock:
                        self.peer_recv_win = pkt.recv_win if pkt.recv_win > 0 else 1
                        
                        for seq in range(self.send_base, pkt.ack):
                            self.unacked_packets.pop(seq, None)
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
            self.sock.sendto(fin_pkt.pack(), self.remote_addr)
        
        self.running = False
        self.connected = False
        if self.timer:
            self.timer.cancel()
        self.sock.close()


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
        return sum(header + self.payload) % (2**32)

    def pack(self):
        self.len = len(self.payload)
        self.checksum = self.compute_checksum()
        return struct.pack(HEADER_FORMAT, self.ver, self.flags, self.conn_id,
                          self.seq, self.ack, self.recv_win, self.len, self.checksum) + self.payload

    @staticmethod
    def verify_checksum(ver, flags, conn_id, seq, ack, recv_win, length, checksum, payload):
        temp_packet = TransportPacket(ver, flags, conn_id, seq, ack, recv_win, length, 0, payload)
        computed = temp_packet.compute_checksum()
        return computed == checksum

    @staticmethod
    def unpack(data):
        if len(data) < HEADER_LEN:
            raise ValueError("Packet too small")

        ver, flags, conn_id, seq, ack, recv_win, length, checksum = struct.unpack(HEADER_FORMAT, data[:HEADER_LEN])
        payload = data[HEADER_LEN:]

        if not TransportPacket.verify_checksum(ver, flags, conn_id, seq, ack, recv_win, length, checksum, payload):
            raise ValueError("Checksum failed")

        return TransportPacket(ver, flags, conn_id, seq, ack, recv_win, length, checksum, payload)

    def __repr__(self):
        payload_str = self.payload.decode('utf-8', 'ignore')
        return f"TransportPacket(seq={self.seq}, ack={self.ack}, flags={bin(self.flags)}, payload='{payload_str}')"