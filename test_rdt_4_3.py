import unittest
import time
import sys
import struct
import socket
from unittest.mock import MagicMock

# Add src to path to allow imports
sys.path.append("src")

# Import classes to test
from src.peer import UploadSession, Packet, PktType, MAX_PAYLOAD
from src.congestion_control import CongestionController

class MockSocket:
    def __init__(self):
        self.sent_packets = []

    def sendto(self, data, addr):
        self.sent_packets.append((data, addr))

class TestRDT43(unittest.TestCase):
    def setUp(self):
        self.chunk_hash = "hash"
        # Create enough data for multiple packets
        # MAX_PAYLOAD is usually 1024
        self.chunk_data = b"x" * (MAX_PAYLOAD * 10) 
        self.peer_addr = ("127.0.0.1", 12345)
        self.session = UploadSession(self.chunk_hash, self.chunk_data, self.peer_addr)
        self.mock_sock = MockSocket()

    def test_01_rtt_update(self):
        """Test Karn's Algorithm for RTT estimation"""
        print("\nTesting RTT Update (Karn's Algorithm)...")
        
        # Initial values
        self.assertEqual(self.session.estimated_rtt, 0.5)
        self.assertEqual(self.session.dev_rtt, 0.25)
        self.assertEqual(self.session.timeout_interval, 1.5) # 0.5 + 4*0.25

        # Update with sample RTT = 1.0
        # EstRTT = 0.85*0.5 + 0.15*1.0 = 0.425 + 0.15 = 0.575
        # DevRTT = 0.7*0.25 + 0.3*|1.0 - 0.575| = 0.175 + 0.3*0.425 = 0.175 + 0.1275 = 0.3025
        # Timeout = 0.575 + 4*0.3025 = 0.575 + 1.21 = 1.785
        self.session.update_rtt(1.0)
        
        self.assertAlmostEqual(self.session.estimated_rtt, 0.575)
        self.assertAlmostEqual(self.session.dev_rtt, 0.3025)
        self.assertAlmostEqual(self.session.timeout_interval, 1.785)
        print("✅ RTT Update verified")

    def test_02_sliding_window(self):
        """Test that sending is limited by cwnd"""
        print("\nTesting Sliding Window...")
        
        # Initial cwnd is 1
        self.assertEqual(self.session.cc.get_cwnd(), 1)
        
        # Send packets
        self.session.send_new_packets(self.mock_sock)
        
        # Should have sent 1 packet (seq 1)
        self.assertEqual(len(self.mock_sock.sent_packets), 1)
        self.assertEqual(self.session.next_seq_num, 2)
        
        # Try to send more, should be blocked by window
        self.session.send_new_packets(self.mock_sock)
        self.assertEqual(len(self.mock_sock.sent_packets), 1)
        print("✅ Sliding Window verified")

    def test_03_ack_handling_and_window_slide(self):
        """Test ACK processing and window sliding"""
        print("\nTesting ACK Handling & Window Slide...")
        
        # Send packet 1
        self.session.send_new_packets(self.mock_sock)
        self.mock_sock.sent_packets.clear()
        
        # Receive ACK 1
        # cwnd should increase to 2 (slow start)
        self.session.handle_ack(1, self.mock_sock)
        
        self.assertEqual(self.session.base_seq, 2)
        self.assertEqual(self.session.cc.get_cwnd(), 2)
        
        # Should send packet 2 and 3 (window size 2)
        # next_seq_num was 2. base_seq is 2. cwnd is 2.
        # Can send 2, 3.
        self.assertEqual(len(self.mock_sock.sent_packets), 2)
        
        pkt2_type, _, _, pkt2_seq, _ = Packet.parse_header(self.mock_sock.sent_packets[0][0])
        pkt3_type, _, _, pkt3_seq, _ = Packet.parse_header(self.mock_sock.sent_packets[1][0])
        
        self.assertEqual(pkt2_seq, 2)
        self.assertEqual(pkt3_seq, 3)
        print("✅ ACK Handling & Window Slide verified")

    def test_04_fast_retransmit(self):
        """Test Fast Retransmit on 3 duplicate ACKs"""
        print("\nTesting Fast Retransmit...")
        
        # Send packet 1
        self.session.send_new_packets(self.mock_sock)
        self.mock_sock.sent_packets.clear()
        
        # Receive ACK 1 -> Send 2, 3
        self.session.handle_ack(1, self.mock_sock)
        self.mock_sock.sent_packets.clear()
        
        # Current state: base_seq=2, next_seq_num=4, cwnd=2
        # Packets 2 and 3 are in flight.
        
        # Simulate receiving duplicate ACKs for 1 (meaning peer expects 2)
        
        # 1st Duplicate ACK (ACK=1)
        self.session.handle_ack(1, self.mock_sock)
        self.assertEqual(self.session.cc.dup_ack_count, 1)
        self.assertEqual(len(self.mock_sock.sent_packets), 0)
        
        # 2nd Duplicate ACK (ACK=1)
        self.session.handle_ack(1, self.mock_sock)
        self.assertEqual(self.session.cc.dup_ack_count, 2)
        self.assertEqual(len(self.mock_sock.sent_packets), 0)
        
        # 3rd Duplicate ACK (ACK=1) -> Fast Retransmit Packet 2
        self.session.handle_ack(1, self.mock_sock)
        
        # Should have retransmitted packet 2 (base_seq)
        self.assertEqual(len(self.mock_sock.sent_packets), 1)
        _, _, _, seq, _ = Packet.parse_header(self.mock_sock.sent_packets[0][0])
        self.assertEqual(seq, 2)
        
        # Verify Congestion Control reaction (ssthresh dropped, cwnd reset)
        # ssthresh = max(floor(cwnd/2), 2). cwnd was 2. ssthresh = 2.
        # cwnd = 1.
        self.assertEqual(self.session.cc.cwnd, 1.0)
        print("✅ Fast Retransmit verified")

    def test_05_timeout(self):
        """Test Timeout Retransmission"""
        print("\nTesting Timeout...")
        
        # Send packet 1
        self.session.send_new_packets(self.mock_sock)
        self.mock_sock.sent_packets.clear()
        
        # Force timeout
        # Set send_time of packet 1 to be very old
        self.session.unacked_buffer[1]['send_time'] = time.time() - 100
        
        self.session.check_timeout(self.mock_sock)
        
        # Should retransmit packet 1
        self.assertEqual(len(self.mock_sock.sent_packets), 1)
        _, _, _, seq, _ = Packet.parse_header(self.mock_sock.sent_packets[0][0])
        self.assertEqual(seq, 1)
        
        # Verify Congestion Control reaction
        self.assertEqual(self.session.cc.cwnd, 1.0)
        print("✅ Timeout verified")

if __name__ == '__main__':
    unittest.main()
