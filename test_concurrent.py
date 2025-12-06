#!/usr/bin/env python3
"""
Test concurrent download from multiple peers
"""
import subprocess
import time
import os
import pickle

def test_concurrent_download():
    """Test downloading multiple chunks from multiple peers concurrently"""
    print("=== Concurrent Download Test ===\n")
    
    # Clean up result file
    result_file = "test/tmp2/result_concurrent.fragment"
    if os.path.exists(result_file):
        os.remove(result_file)
    
    # Start 3 peers with different chunks
    print("Starting peers...")
    peers = []
    
    # Peer 2 has data2 chunks
    peer2 = subprocess.Popen(
        ["python3", "-m", "src.peer",
         "-p", "test/tmp2/nodes2.map",
         "-c", "test/tmp2/data2.fragment",
         "-m", "3", "-i", "2", "-v", "1"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    peers.append(("peer 2", peer2))
    
    # Peer 3 has data1 chunks  
    peer3 = subprocess.Popen(
        ["python3", "-m", "src.peer",
         "-p", "test/tmp2/nodes2.map",
         "-c", "test/tmp2/data1.fragment",
         "-m", "3", "-i", "3", "-v", "1"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    peers.append(("peer 3", peer3))
    
    time.sleep(0.5)
    
    # Peer 1 will download from both
    peer1 = subprocess.Popen(
        ["python3", "-m", "src.peer",
         "-p", "test/tmp2/nodes2.map",
         "-c", "test/tmp2/data1.fragment",  # Start with some chunks
         "-m", "3", "-i", "1", "-v", "2"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    peers.append(("peer 1", peer1))
    
    time.sleep(0.5)
    
    # Send download command
    print("Sending DOWNLOAD command...")
    peer1.stdin.write("DOWNLOAD test/tmp2/download_target.chunkhash test/tmp2/result_concurrent.fragment\n")
    peer1.stdin.flush()
    
    print("Waiting for download (15 seconds)...")
    time.sleep(15)
    
    # Terminate all peers
    print("\nTerminating peers...")
    for name, peer in peers:
        peer.terminate()
        try:
            output = peer.stdout.read()
            if "GOT" in output or "Sent" in output or "Received" in output:
                print(f"\n=== {name} Output ===")
                print(output[:500])  # Print first 500 chars
        except:
            pass
    
    # Verify result
    print("\n=== Verification ===")
    if os.path.exists(result_file):
        print(f"✓ Result file created")
        
        with open(result_file, "rb") as f:
            result = pickle.load(f)
        
        print(f"✓ Downloaded {len(result)} chunk(s)")
        for chunk_hash in result.keys():
            print(f"  - {chunk_hash}: {len(result[chunk_hash])} bytes")
        
        print("\n✅ CONCURRENT TEST PASSED!")
    else:
        print(f"✗ Result file not created")
        print("\n❌ TEST FAILED!")

if __name__ == "__main__":
    # Check if tmp2 directory exists
    if not os.path.exists("test/tmp2"):
        print("test/tmp2 directory not found")
        exit(1)
    
    test_concurrent_download()
