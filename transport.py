# transport.py

import struct
from constants import HEADER_FORMAT, HEADER_LEN

class TransportPacket:
    """Represents a custom transport layer packet."""

    def __init__(self, ver=1, flags=0, conn_id=0, seq=0, ack=0,
                 recv_win=0, length=0, checksum=0, payload=b''):
        # initialize all header fields and the payload
        self.ver = ver
        self.flags = flags
        self.conn_id = conn_id
        self.seq = seq
        self.ack = ack
        self.recv_win = recv_win
        self.payload = payload
        self.len = len(self.payload) # calculate length based on the payload size
        self.checksum = checksum

    def pack(self):
        """Serializes the packet object into a bytes object for transmission."""
        header = struct.pack(
            HEADER_FORMAT,
            self.ver,
            self.flags,
            self.conn_id,
            self.seq,
            self.ack,
            self.recv_win,
            self.len,
            self.checksum
        )
        # combine the header and payload into a single bytes object
        return header + self.payload

    @staticmethod
    def unpack(data):
        """Deserializes a bytes object into a TransportPacket object."""
        # check if data is large enough to contain a full header
        if len(data) < HEADER_LEN:
            raise ValueError("Data is too small to unpack header.")

        # unpack the header portion of the data using the defined format
        header_tuple = struct.unpack(HEADER_FORMAT, data[:HEADER_LEN])
        ver, flags, conn_id, seq, ack, recv_win, length, checksum = header_tuple

        # the remainder of the data is the payload
        payload = data[HEADER_LEN:]

        # return a new object with the parsed data
        return TransportPacket(
            ver, flags, conn_id, seq, ack, recv_win, length, checksum, payload
        )

    def __repr__(self):
        """Provides a developer-friendly string representation of the packet."""
        payload_str = self.payload.decode('utf-8', 'ignore')
        return (
            f"TransportPacket(seq={self.seq}, ack={self.ack}, "
            f"flags={bin(self.flags)}, len={self.len}, payload='{payload_str}')"
        )