import time
from transport import TransportConnection

SERVER_ADDR = ("127.0.0.1", 40000)
CLIENT_ADDR = ("127.0.0.1", 40001)

def server_on_message(data: bytes):
    print(f"[SERVER] Received: {data.decode('utf-8', 'ignore')}")

def main():
    # Start server connection
    server = TransportConnection(
        local_addr=SERVER_ADDR,
        remote_addr=None,          # filled in when SYN arrives
        on_message=server_on_message,
        is_server=True,
    )

    # Start client connection
    client = TransportConnection(
        local_addr=CLIENT_ADDR,
        remote_addr=SERVER_ADDR,
        on_message=lambda d: None,  # client is only sending in this demo
        is_server=False,
    )

    print("[DEMO] Starting three-way handshake...")
    client.connect()
    print("[DEMO] Handshake complete. Sending 5 messages...")

    for i in range(5):
        msg = f"Hello {i}".encode()
        client.send_msg(msg)
        time.sleep(0.05)  # small spacing between sends

    # Give time for delivery + ACKs
    time.sleep(1.0)

    client.close()
    server.close()

    # Fetch metrics from client (sender) side
    client_metrics = client.get_metrics()
    server_metrics = server.get_metrics()

    print("\n=== CLIENT METRICS (SENDER) ===")
    for k, v in client_metrics.items():
        print(f"{k}: {v}")

    print("\n=== SERVER METRICS (RECEIVER) ===")
    for k, v in server_metrics.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()
