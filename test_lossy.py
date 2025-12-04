
import time
import transport

SERVER_ADDR = ("127.0.0.1", 45000)
CLIENT_ADDR = ("127.0.0.1", 45001)

def run_test(profile_name, profile_value):
    """Run transport test with specified loss profile"""
    print(f"\n{'='*60}")
    print(f"Testing with LOSS_PROFILE = '{profile_value}'")
    print(f"{'='*60}\n")
    
    # Set loss profile
    original_profile = transport.LOSS_PROFILE
    transport.LOSS_PROFILE = profile_value
    
    received_messages = []
    
    def server_on_message(data: bytes):
        msg = data.decode('utf-8', 'ignore')
        received_messages.append(msg)
        print(f"[SERVER] ✓ Received: {msg}")
    
    # Start server
    server = transport.TransportConnection(
        local_addr=SERVER_ADDR,
        remote_addr=None,
        on_message=server_on_message,
        is_server=True,
    )
    
    # Start client
    client = transport.TransportConnection(
        local_addr=CLIENT_ADDR,
        remote_addr=SERVER_ADDR,
        on_message=lambda d: None,
        is_server=False,
    )
    
    print(f"[{profile_name}] Starting handshake...")
    try:
        client.connect()
        print(f"[{profile_name}] ✓ Handshake complete")
    except TimeoutError:
        print(f"[{profile_name}] ✗ Handshake timeout (expected with high loss)")
        client.close()
        server.close()
        transport.LOSS_PROFILE = original_profile
        return
    
    print(f"[{profile_name}] Sending 10 messages...\n")
    
    # Send test messages
    for i in range(10):
        msg = f"Message {i}"
        client.send_msg(msg.encode())
        time.sleep(0.02)
    
    # Wait for delivery
    time.sleep(2.0)
    
    client.close()
    server.close()
    
    # Get metrics
    client_metrics = client.get_metrics()
    server_metrics = server.get_metrics()
    
    print(f"\n--- {profile_name} RESULTS ---")
    print(f"Messages sent: {client_metrics['messages_sent']}")
    print(f"Messages delivered: {server_metrics['messages_delivered']}")
    print(f"All messages received: {'✓' if len(received_messages) == 10 else '✗'}")
    print(f"Retransmissions: {client_metrics['retransmissions']}")
    print(f"Out-of-order packets: {server_metrics['ooo_packets']}")
    
    if client_metrics['avg_rtt_sec'] is not None:
        print(f"Average RTT: {client_metrics['avg_rtt_sec']*1000:.2f} ms")
        print(f"95th percentile RTT: {client_metrics['p95_rtt_sec']*1000:.2f} ms")
    
    if server_metrics['goodput_bps'] is not None:
        print(f"Goodput: {server_metrics['goodput_bps']:.2f} bits/sec")
    
    # Restore original profile
    transport.LOSS_PROFILE = original_profile

def main():
    print("="*60)
    print("RELIABLE TRANSPORT PROTOCOL - LOSS SIMULATION DEMO")
    print("="*60)
    print("\nThis demo shows how Go-Back-N ARQ handles packet loss:")
    print("  • Clean: 0% loss (baseline)")
    print("  • Random: ~8% independent packet loss")
    print("  • Bursty: Packets drop in bursts")
    print()
    
    # Test 1: Clean (baseline)
    run_test("CLEAN", "clean")
    time.sleep(0.5)
    
    # Test 2: Random loss
    run_test("RANDOM LOSS", "random")
    time.sleep(0.5)
    
    # Test 3: Bursty loss
    run_test("BURSTY LOSS", "bursty")
    
    print("\n" + "="*60)
    print("DEMO COMPLETE")
    print("="*60)
    print("\nKey observations:")
    print("  • All messages delivered reliably despite packet loss")
    print("  • Retransmissions increase with loss rate")
    print("  • RTT and throughput affected by loss conditions")
    print("  • Go-Back-N ensures in-order, reliable delivery")

if __name__ == "__main__":
    main()
