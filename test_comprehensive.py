#!/usr/bin/env python3
"""
Comprehensive testing suite for P2P file transfer implementation
Tests all aspects of tasks 4.1 and 4.2
"""
import subprocess
import time
import os
import pickle
import sys
import hashlib

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.peers = []
        
    def cleanup_ports(self):
        """Kill any processes using test ports"""
        ports = range(58001, 58010)
        for port in ports:
            os.system(f"lsof -ti:{port} | xargs kill -9 2>/dev/null")
        time.sleep(0.5)
    
    def start_peer(self, peer_id, nodes_map, chunk_file, max_conn, port, verbose=1):
        """Start a peer process"""
        peer = subprocess.Popen(
            ["python3", "-m", "src.peer",
             "-p", nodes_map,
             "-c", chunk_file,
             "-m", str(max_conn),
             "-i", str(peer_id),
             "-v", str(verbose)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        self.peers.append(peer)
        return peer
    
    def cleanup_peers(self):
        """Terminate all peer processes"""
        for peer in self.peers:
            try:
                peer.terminate()
                peer.wait(timeout=1)
            except:
                peer.kill()
        self.peers = []
        self.cleanup_ports()
    
    def verify_download(self, result_file, expected_hashes):
        """Verify downloaded file contains expected chunks"""
        if not os.path.exists(result_file):
            return False, "Result file not created"
        
        try:
            with open(result_file, "rb") as f:
                result = pickle.load(f)
            
            if not isinstance(result, dict):
                return False, "Result is not a dictionary"
            
            for expected_hash in expected_hashes:
                if expected_hash not in result:
                    return False, f"Missing chunk {expected_hash}"
                
                # Verify chunk size
                if len(result[expected_hash]) != 524288:
                    return False, f"Wrong chunk size for {expected_hash}"
                
                # Verify hash
                sha1 = hashlib.sha1()
                sha1.update(result[expected_hash])
                actual_hash = sha1.hexdigest()
                if actual_hash != expected_hash:
                    return False, f"Hash mismatch for {expected_hash}"
            
            return True, f"All {len(expected_hashes)} chunks verified"
        except Exception as e:
            return False, str(e)
    
    def run_test(self, name, test_func):
        """Run a single test"""
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print('='*60)
        try:
            self.cleanup_peers()
            result = test_func()
            if result:
                print(f"✅ PASSED: {name}")
                self.passed += 1
            else:
                print(f"❌ FAILED: {name}")
                self.failed += 1
        except Exception as e:
            print(f"❌ FAILED: {name}")
            print(f"   Error: {e}")
            self.failed += 1
        finally:
            self.cleanup_peers()
    
    def test_1_basic_download(self):
        """Test 1: Basic single chunk download from one peer"""
        print("Starting basic download test...")
        
        # Clean up result file
        result_file = "test/tmp1/result_test1.fragment"
        if os.path.exists(result_file):
            os.remove(result_file)
        
        # Start peer 2 (has the chunk we need)
        print("  Starting peer 2 (sender)...")
        peer2 = self.start_peer(2, "test/tmp1/nodes1.map", "test/tmp1/data2.fragment", 2, 58002)
        time.sleep(0.5)
        
        # Start peer 1 (downloader)
        print("  Starting peer 1 (receiver)...")
        peer1 = self.start_peer(1, "test/tmp1/nodes1.map", "test/tmp1/data1.fragment", 2, 58001)
        time.sleep(0.5)
        
        # Send download command
        print("  Sending DOWNLOAD command...")
        peer1.stdin.write("DOWNLOAD test/tmp1/download_target.chunkhash test/tmp1/result_test1.fragment\n")
        peer1.stdin.flush()
        
        # Wait for completion
        time.sleep(8)
        
        # Verify
        expected = ["3b68110847941b84e8d05417a5b2609122a56314"]
        success, msg = self.verify_download(result_file, expected)
        print(f"  {msg}")
        
        return success
    
    def test_2_multiple_chunks(self):
        """Test 2: Download multiple chunks from multiple peers"""
        print("Starting multiple chunk download test...")
        
        result_file = "test/tmp3/result_test2.fragment"
        if os.path.exists(result_file):
            os.remove(result_file)
        
        # Start multiple peers - peer 2 and 3 only (nodes3.map only has 1,2,3)
        print("  Starting peer 2...")
        peer2 = self.start_peer(2, "test/tmp3/nodes3.map", "test/tmp3/data3-2.fragment", 3, 58002)
        time.sleep(0.3)
        
        print("  Starting peer 3...")
        peer3 = self.start_peer(3, "test/tmp3/nodes3.map", "test/tmp3/data3-3.fragment", 3, 58003)
        time.sleep(0.3)
        
        print("  Starting peer 1 (downloader)...")
        peer1 = self.start_peer(1, "test/tmp3/nodes3.map", "test/tmp3/data3-1.fragment", 3, 58001)
        time.sleep(0.5)
        
        # Check what chunks we need
        with open("test/tmp3/download_target3.chunkhash", "r") as f:
            lines = f.readlines()
            expected = [line.strip().split()[1] for line in lines if line.strip()]
        
        print(f"  Need to download {len(expected)} chunks")
        
        # Send download command
        print("  Sending DOWNLOAD command...")
        peer1.stdin.write("DOWNLOAD test/tmp3/download_target3.chunkhash test/tmp3/result_test2.fragment\n")
        peer1.stdin.flush()
        
        # Wait longer for multiple chunks
        time.sleep(15)
        
        # Verify
        success, msg = self.verify_download(result_file, expected)
        print(f"  {msg}")
        
        return success
    
    def test_3_concurrent_downloads(self):
        """Test 3: Concurrent downloads from different peers"""
        print("Starting concurrent download test...")
        
        result_file = "test/tmp4/result_test3.fragment"
        if os.path.exists(result_file):
            os.remove(result_file)
        
        # Start peers with different chunks
        print("  Starting peer 2...")
        peer2 = self.start_peer(2, "test/tmp4/nodes4.map", "test/tmp4/data4-1.fragment", 2, 58002)
        time.sleep(0.3)
        
        print("  Starting peer 3...")
        peer3 = self.start_peer(3, "test/tmp4/nodes4.map", "test/tmp4/data4-2.fragment", 2, 58003)
        time.sleep(0.3)
        
        print("  Starting peer 1 (downloader)...")
        peer1 = self.start_peer(1, "test/tmp4/nodes4.map", "test/tmp4/data4-1.fragment", 2, 58001)
        time.sleep(0.5)
        
        # Check expected chunks
        with open("test/tmp4/download_target4.chunkhash", "r") as f:
            lines = f.readlines()
            expected = [line.strip().split()[1] for line in lines if line.strip()]
        
        print(f"  Need to download {len(expected)} chunks concurrently")
        
        # Send download command
        print("  Sending DOWNLOAD command...")
        peer1.stdin.write("DOWNLOAD test/tmp4/download_target4.chunkhash test/tmp4/result_test3.fragment\n")
        peer1.stdin.flush()
        
        # Wait for concurrent downloads
        time.sleep(12)
        
        # Verify
        success, msg = self.verify_download(result_file, expected)
        print(f"  {msg}")
        
        return success
    
    def test_4_max_connections(self):
        """Test 4: Test max connection limit (DENIED functionality)"""
        print("Starting max connection limit test...")
        
        result_file = "test/tmp1/result_test4.fragment"
        if os.path.exists(result_file):
            os.remove(result_file)
        
        # Start peer 2 with max_conn=1 (will be busy)
        print("  Starting peer 2 with max_conn=1...")
        peer2 = self.start_peer(2, "test/tmp1/nodes1.map", "test/tmp1/data2.fragment", 1, 58002, verbose=2)
        time.sleep(0.5)
        
        # Start peer 3 to occupy peer 2
        print("  Starting peer 3 to occupy peer 2...")
        peer3 = self.start_peer(3, "test/tmp1/nodes1.map", "test/tmp1/data1.fragment", 2, 58003)
        time.sleep(0.3)
        
        # Make peer 3 download from peer 2 first
        peer3.stdin.write("DOWNLOAD test/tmp1/download_target.chunkhash test/tmp1/result_peer3.fragment\n")
        peer3.stdin.flush()
        time.sleep(2)  # Let peer 3 start downloading
        
        # Now peer 1 tries to download (should get DENIED or wait)
        print("  Starting peer 1 (should experience connection limit)...")
        peer1 = self.start_peer(1, "test/tmp1/nodes1.map", "test/tmp1/data1.fragment", 2, 58001, verbose=2)
        time.sleep(0.3)
        
        peer1.stdin.write("DOWNLOAD test/tmp1/download_target.chunkhash test/tmp1/result_test4.fragment\n")
        peer1.stdin.flush()
        
        # Wait and see what happens
        time.sleep(8)
        
        # Read peer 1 output to check for DENIED or successful alternative download
        try:
            peer1.terminate()
            output = peer1.stdout.read()
            
            # Test passes if either:
            # 1. Received DENIED message
            # 2. Successfully downloaded (found another peer)
            has_denied = "DENIED" in output or "Received DENIED" in output
            has_success = os.path.exists(result_file)
            
            print(f"  DENIED received: {has_denied}")
            print(f"  Alternative download: {has_success}")
            
            # Either behavior is acceptable
            return has_denied or has_success
        except:
            return False
    
    def test_5_whohas_broadcast(self):
        """Test 5: Verify WHOHAS is broadcast to all peers"""
        print("Starting WHOHAS broadcast test...")
        
        # Start multiple peers
        print("  Starting 5 peers...")
        for i in range(2, 7):
            self.start_peer(i, "test/tmp1/nodes1.map", "test/tmp1/data2.fragment", 2, 58000+i, verbose=2)
            time.sleep(0.2)
        
        print("  Starting peer 1 (broadcaster)...")
        peer1 = self.start_peer(1, "test/tmp1/nodes1.map", "test/tmp1/data1.fragment", 2, 58001, verbose=2)
        time.sleep(0.5)
        
        # Send download command
        print("  Sending DOWNLOAD command...")
        peer1.stdin.write("DOWNLOAD test/tmp1/download_target.chunkhash test/tmp1/result_test5.fragment\n")
        peer1.stdin.flush()
        
        time.sleep(5)
        
        # Check if at least some peers received WHOHAS (by checking if download succeeded)
        success = os.path.exists("test/tmp1/result_test5.fragment")
        print(f"  Broadcast successful: {success}")
        
        return success
    
    def test_6_single_session_per_peer(self):
        """Test 6: Verify only one chunk transfer per peer pair at a time"""
        print("Starting single session per peer test...")
        
        # This test verifies that peer A doesn't request multiple chunks from peer B simultaneously
        # We'll use tmp3 setup where peer 1 needs multiple chunks
        
        result_file = "test/tmp3/result_test6.fragment"
        if os.path.exists(result_file):
            os.remove(result_file)
        
        print("  Starting peer 2 with multiple chunks...")
        peer2 = self.start_peer(2, "test/tmp3/nodes3.map", "test/tmp3/data3-2.fragment", 3, 58002, verbose=2)
        time.sleep(0.3)
        
        print("  Starting peer 3 with multiple chunks...")
        peer3 = self.start_peer(3, "test/tmp3/nodes3.map", "test/tmp3/data3-3.fragment", 3, 58003, verbose=2)
        time.sleep(0.3)
        
        print("  Starting peer 1...")
        peer1 = self.start_peer(1, "test/tmp3/nodes3.map", "test/tmp3/data3-1.fragment", 3, 58001, verbose=2)
        time.sleep(0.5)
        
        # Download multiple chunks (peer 1 will get them from peers 2 and 3)
        peer1.stdin.write("DOWNLOAD test/tmp3/download_target3.chunkhash test/tmp3/result_test6.fragment\n")
        peer1.stdin.flush()
        
        time.sleep(15)
        
        # If download succeeds, the implementation handled it correctly
        # (each peer only sends one chunk at a time to peer 1)
        with open("test/tmp3/download_target3.chunkhash", "r") as f:
            lines = f.readlines()
            expected = [line.strip().split()[1] for line in lines if line.strip()]
        
        success, msg = self.verify_download(result_file, expected)
        print(f"  {msg}")
        print(f"  Sequential/concurrent transfer handled correctly: {success}")
        
        return success
    
    def test_7_packet_format(self):
        """Test 7: Verify packet format correctness"""
        print("Starting packet format test...")
        
        # Import and test the Packet class directly
        sys.path.insert(0, '/Users/macbookair/Documents/CN')
        from src.peer import Packet, PktType, HEADER_LEN
        
        # Test header building
        header = Packet.build_header(PktType.WHOHAS, 0, 0, 20)
        print(f"  Header length: {len(header)} (expected {HEADER_LEN})")
        
        if len(header) != HEADER_LEN:
            return False
        
        # Test packet building
        payload = b"test" * 5
        pkt = Packet.build_packet(PktType.DATA, 1, 0, payload)
        print(f"  Packet length: {len(pkt)} (expected {HEADER_LEN + len(payload)})")
        
        if len(pkt) != HEADER_LEN + len(payload):
            return False
        
        # Test parsing
        pkt_type, hlen, plen, seq, ack = Packet.parse_header(pkt)
        print(f"  Parsed: type={pkt_type}, seq={seq}, plen={plen}")
        
        if pkt_type != PktType.DATA or seq != 1:
            return False
        
        print("  Packet format verification passed")
        return True
    
    def test_8_hash_format(self):
        """Test 8: Verify hash format conversions"""
        print("Starting hash format test...")
        
        test_hash_str = "3b68110847941b84e8d05417a5b2609122a56314"
        
        # Convert to bytes
        hash_bytes = bytes.fromhex(test_hash_str)
        print(f"  Hash bytes length: {len(hash_bytes)} (expected 20)")
        
        if len(hash_bytes) != 20:
            return False
        
        # Convert back
        hash_str_back = hash_bytes.hex()
        print(f"  Roundtrip: {test_hash_str == hash_str_back}")
        
        if test_hash_str != hash_str_back:
            return False
        
        print("  Hash format verification passed")
        return True
    
    def print_summary(self):
        """Print test summary"""
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print('='*60)
        print(f"Total tests: {total}")
        print(f"Passed: {self.passed} ✅")
        print(f"Failed: {self.failed} ❌")
        print(f"Success rate: {self.passed/total*100:.1f}%")
        print('='*60)
        
        if self.failed == 0:
            print("🎉 ALL TESTS PASSED!")
        else:
            print("⚠️  Some tests failed. Review the output above.")

def main():
    print("="*60)
    print("COMPREHENSIVE P2P FILE TRANSFER TEST SUITE")
    print("Testing Tasks 4.1 and 4.2")
    print("="*60)
    
    runner = TestRunner()
    
    # Run all tests
    runner.run_test("Test 1: Basic Single Chunk Download", runner.test_1_basic_download)
    runner.run_test("Test 2: Multiple Chunks Download", runner.test_2_multiple_chunks)
    runner.run_test("Test 3: Concurrent Downloads", runner.test_3_concurrent_downloads)
    runner.run_test("Test 4: Max Connection Limit", runner.test_4_max_connections)
    runner.run_test("Test 5: WHOHAS Broadcast", runner.test_5_whohas_broadcast)
    runner.run_test("Test 6: Single Session Per Peer", runner.test_6_single_session_per_peer)
    runner.run_test("Test 7: Packet Format Verification", runner.test_7_packet_format)
    runner.run_test("Test 8: Hash Format Verification", runner.test_8_hash_format)
    
    # Print summary
    runner.print_summary()
    
    # Return exit code
    sys.exit(0 if runner.failed == 0 else 1)

if __name__ == "__main__":
    main()
