import argparse
import time
from constants import SERVER_HOST, SERVER_PORT
from transport import TransportConnection

# Command-lines including the arguments needed ('Your display name', 'Server IP', 'Server port').
def main():
    parser = argparse.ArgumentParser(description='Chat client')
    parser.add_argument('--name', type=str, required=True, help='Your display name')
    parser.add_argument('--server', type=str, default=SERVER_HOST, help='Server IP')
    parser.add_argument('--port', type=int, default=SERVER_PORT, help='Server port')
    args = parser.parse_args()

    # Validated message executes callback.
    def on_message(data):
        print(f"\n{data.decode('utf-8', errors='ignore')}\n> ", end="", flush=True)
    
    print(f"🔌 Connecting to {args.server}:{args.port}...")
    # Transport connection with random free port local address.
    conn = TransportConnection(
        local_addr=('0.0.0.0', 0),
        remote_addr=(args.server, args.port),
        on_message=on_message,
        is_server=False
    )
    # Three-way handshake.
    try:
        conn.connect()
        print(f"✅ Connected (conn_id={conn.conn_id})")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return
    
    conn.send_msg(f"NAME {args.name}".encode()) # Display name presented to server once connected.
    time.sleep(0.1)
    
    print("\nCommands: JOIN <room>, LEAVE <room>, MSG <room> <text>, exit\n")

    # Input loop for main, includes messages and commands implemented until server disconnection.
    try:
        while conn.connected:
            user_input = input("> ").strip()
            if not user_input:
                continue
            
            if user_input.lower() in {"exit", "quit"}: # User disconnects.
                break
            # Message/command is sent through the UDP.
            try:
                conn.send_msg(user_input.encode())
                print("[SENT] Message queued for delivery")
            except Exception as e:
                print(f"[ERROR] Failed to send: {e}")
            
    except KeyboardInterrupt:
        print("\n\nInterrupted.") # Ctrl+C disconnect.
    finally:
        # FIN packet closure of the TransportConnection.
        conn.close()
        print("Closed.")

if __name__ == "__main__":
    main()
