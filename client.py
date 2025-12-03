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
    
    print("\nCommands: JOIN <room>, LEAVE <room>, MSG <room> <text>, exit\n")
    
    try:
        while conn.connected:
            user_input = input("> ").strip()
            if not user_input:
                continue
            
            if user_input.lower() in {"exit", "quit"}:
                break
            
            try:
                conn.send_msg(user_input.encode())
                print("[SENT] Message queued for delivery")
            except Exception as e:
                print(f"[ERROR] Failed to send: {e}")
            
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        conn.close()
        print("Closed.")

if __name__ == "__main__":
    main()
