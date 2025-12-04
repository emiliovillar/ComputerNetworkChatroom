import argparse
import time
from constants import SERVER_HOST, SERVER_PORT
from transport import TransportConnection

def main():
    parser = argparse.ArgumentParser(description='Chat client')
    parser.add_argument('--name', type=str, required=True, help='Your display name')
    parser.add_argument('--server', type=str, default=SERVER_HOST, help='Server IP')
    parser.add_argument('--port', type=int, default=SERVER_PORT, help='Server port')
    args = parser.parse_args()
    
    def on_message(data):
        print(f"\n{data.decode('utf-8', errors='ignore')}\n> ", end="", flush=True)
    
    print(f"🔌 Connecting to {args.server}:{args.port}...")
    conn = TransportConnection(
        local_addr=('0.0.0.0', 0),
        remote_addr=(args.server, args.port),
        on_message=on_message,
        is_server=False
    )
    try:
        conn.connect()
        print(f"✅ Connected (conn_id={conn.conn_id})")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return
    
    conn.send_msg(f"NAME {args.name}".encode())
    time.sleep(0.1)
    
    def print_metrics():
        metrics = conn.get_metrics()
        print("\n=== TRANSPORT METRICS ===")
        if metrics.get("messages_sent") is not None:
            print(f"Messages sent: {metrics['messages_sent']}")
        if metrics.get("messages_delivered") is not None:
            print(f"Messages delivered: {metrics['messages_delivered']}")
        if metrics.get("retransmissions") is not None:
            print(f"Retransmissions: {metrics['retransmissions']}")
        if metrics.get("retransmissions_per_kb") is not None:
            print(f"Retransmissions per KB: {metrics['retransmissions_per_kb']:.3f}")
        if metrics.get("ooo_packets") is not None:
            print(f"Out-of-order packets: {metrics['ooo_packets']}")
        if metrics.get("avg_rtt_ms") is not None:
            print(f"Average RTT: {metrics['avg_rtt_ms']:.2f} ms")
        if metrics.get("p95_rtt_ms") is not None:
            print(f"95th percentile RTT: {metrics['p95_rtt_ms']:.2f} ms")
        if metrics.get("goodput_msg_per_sec") is not None:
            print(f"Goodput: {metrics['goodput_msg_per_sec']:.2f} messages/sec")
        print("========================\n")
    
    print("\nCommands: JOIN <room>, LEAVE <room>, MSG <room> <text>, METRICS, exit\n")
    
    try:
        while conn.connected:
            user_input = input("> ").strip()
            if not user_input:
                continue
            
            if user_input.lower() in {"exit", "quit"}:
                break
            
            if user_input.upper() == "METRICS":
                print_metrics()
                continue
            
            try:
                conn.send_msg(user_input.encode())
                print("[SENT] Message queued for delivery")
            except Exception as e:
                print(f"[ERROR] Failed to send: {e}")
            
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        print_metrics()
        conn.close()
        print("Closed.")

if __name__ == "__main__":
    main()
