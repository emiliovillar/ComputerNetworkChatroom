# constants.py

import struct

# server network configuration
SERVER_HOST = '0.0.0.0'  # accept connections on all available IPs
SERVER_PORT = 12345

# defines the binary structure of the packet header
# ! = network byte order, B = 1 byte, H = 2 bytes, I = 4 bytes
HEADER_FORMAT = '!BBHIIHHI'
HEADER_LEN = struct.calcsize(HEADER_FORMAT) # total size of the header in bytes

# bitmask values for the 'flags' field
SYN = 0x02 # flag for connection initiation
ACK = 0x10 # flag for acknowledgement
FIN = 0x01 # flag for connection termination

# size of the buffer for receiving socket data
BUFFER_SIZE = 4096