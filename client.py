import argparse
import time
from constants import SERVER_HOST, SERVER_PORT
from transport import TransportConnection

def main():
    #  command line arguments
    parser = argparse.ArgumentParser(description='Chat client')
    parser.add_argument('--name', type=str, required=True, help='Your display name')
    parser.add_argument('--server', type=str, default=SERVER_HOST, help='Server IP')
    parser.add_argument('--port', type=int, default=SERVER_PORT, help='Server port')
    args = parser.parse_args()
    
    #  incoming messages from server
    def on_message(data):
        print(f"\n{data.decode('utf-8', errors='ignore')}\n> ", end="", flush=True)
    
    # Create connection to server
    print(f" Connecting to {args.server}:{args.port}...")
    conn = TransportConnection(
        local_addr=('0.0.0.0', 0),  # bind to any available port
        remote_addr=(args.server, args.port),
        on_message=on_message,
        is_server=False
    )
    
    # Perform three-way handshake
    try:
        conn.connect()
        print(f"✅ Connected (conn_id={conn.conn_id})")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return
    
    # Login with username (required for new features)
    print(f"Logging in as '{args.name}'...")
    conn.send_msg(f"LOGIN {args.name}".encode())
    time.sleep(0.2)  # Wait for login confirmation
    
    print("\nCommands:")
    print("  LOGIN <username>  - Login with unique username (required)")
    print("  LOGOUT            - Logout")
    print("  JOIN <room>       - Join a chat room")
    print("  LEAVE <room>      - Leave a room")
    print("  MSG <room> <text> - Send message to room")
    print("  DM <user> <text>  - Send private message to user")
    print("  exit/quit         - Disconnect\n")
    
    # Main input loop
    try:
        while conn.connected:
            user_input = input("> ").strip()
            # Skip empty input
            if not user_input:
                continue
            
            # Exit commands
            if user_input.lower() in {"exit", "quit"}:
                break
            
            # Send command to server
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
