#!/usr/bin/env python3
"""
Manual test script to verify basic P2P file transfer functionality
"""
import subprocess
import time
import sys
import os
import pickle

def test_basic_transfer():
    """Test basic file transfer between two peers"""
    print("=== Manual P2P Transfer Test ===\n")
    
    # Clean up any existing result file
    result_file = "test/tmp1/result_test.fragment"
    if os.path.exists(result_file):
        os.remove(result_file)
        print(f"Cleaned up existing {result_file}")
    
    # Start peer 2 (has the chunk we need)
    print("Starting peer 2 (sender)...")
    peer2 = subprocess.Popen(
        ["python3", "-m", "src.peer", 
         "-p", "test/tmp1/nodes1.map",
         "-c", "test/tmp1/data2.fragment",
         "-m", "2",
         "-i", "2",
         "-v", "2"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    time.sleep(0.5)  # Let peer 2 start
    
    # Start peer 1 (will download)
    print("Starting peer 1 (receiver)...")
    peer1 = subprocess.Popen(
        ["python3", "-m", "src.peer",
         "-p", "test/tmp1/nodes1.map",
         "-c", "test/tmp1/data1.fragment",
         "-m", "2",
         "-i", "1",
         "-v", "2"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    time.sleep(0.5)  # Let peer 1 start
    
    # Send download command to peer 1
    print("Sending DOWNLOAD command to peer 1...")
    peer1.stdin.write("DOWNLOAD test/tmp1/download_target.chunkhash test/tmp1/result_test.fragment\n")
    peer1.stdin.flush()
    
    # Wait for download to complete
    print("Waiting for download to complete (10 seconds)...")
    time.sleep(10)
    
    # Terminate peers
    print("\nTerminating peers...")
    peer1.terminate()
    peer2.terminate()
    
    # Read output
    print("\n=== Peer 1 Output ===")
    try:
        peer1_output = peer1.stdout.read()
        print(peer1_output)
    except:
        pass
    
    print("\n=== Peer 2 Output ===")
    try:
        peer2_output = peer2.stdout.read()
        print(peer2_output)
    except:
        pass
    
    # Check if result file was created
    print("\n=== Verification ===")
    if os.path.exists(result_file):
        print(f"✓ Result file created: {result_file}")
        
        # Load and verify
        with open(result_file, "rb") as f:
            result = pickle.load(f)
        
        print(f"✓ Contains {len(result)} chunk(s)")
        print(f"✓ Chunk hashes: {list(result.keys())}")
        
        # Check if it matches the expected chunk
        expected_hash = "3b68110847941b84e8d05417a5b2609122a56314"
        if expected_hash in result:
            print(f"✓ Successfully downloaded chunk {expected_hash}")
            print(f"✓ Chunk size: {len(result[expected_hash])} bytes")
            print("\n✅ TEST PASSED!")
        else:
            print(f"✗ Expected chunk {expected_hash} not found")
            print("\n❌ TEST FAILED!")
    else:
        print(f"✗ Result file not created: {result_file}")
        print("\n❌ TEST FAILED!")

if __name__ == "__main__":
    test_basic_transfer()
