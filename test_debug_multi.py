#!/usr/bin/env python3
"""Debug test for multiple chunks"""
import subprocess
import time
import os
import pickle

def cleanup_ports():
    os.system("lsof -ti:58001,58002,58003,58004 | xargs kill -9 2>/dev/null")
    time.sleep(0.5)

cleanup_ports()

result_file = "test/tmp3/result_debug.fragment"
if os.path.exists(result_file):
    os.remove(result_file)

# Start peers
print("Starting peers...")
peers = []

peer2 = subprocess.Popen(
    ["python3", "-m", "src.peer", "-p", "test/tmp3/nodes3.map", 
     "-c", "test/tmp3/data3-1.fragment", "-m", "3", "-i", "2", "-v", "2"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)
peers.append(peer2)
time.sleep(0.3)

peer3 = subprocess.Popen(
    ["python3", "-m", "src.peer", "-p", "test/tmp3/nodes3.map",
     "-c", "test/tmp3/data3-2.fragment", "-m", "3", "-i", "3", "-v", "2"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)
peers.append(peer3)
time.sleep(0.3)

peer4 = subprocess.Popen(
    ["python3", "-m", "src.peer", "-p", "test/tmp3/nodes3.map",
     "-c", "test/tmp3/data3-3.fragment", "-m", "3", "-i", "4", "-v", "2"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)
peers.append(peer4)
time.sleep(0.3)

peer1 = subprocess.Popen(
    ["python3", "-m", "src.peer", "-p", "test/tmp3/nodes3.map",
     "-c", "test/tmp3/data3-1.fragment", "-m", "3", "-i", "1", "-v", "2"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)
peers.append(peer1)
time.sleep(0.5)

print("Sending DOWNLOAD command...")
peer1.stdin.write("DOWNLOAD test/tmp3/download_target3.chunkhash test/tmp3/result_debug.fragment\n")
peer1.stdin.flush()

print("Waiting 20 seconds...")
time.sleep(20)

print("\n=== Peer 1 Output ===")
peer1.terminate()
try:
    output = peer1.stdout.read()
    print(output)
except:
    pass

for p in peers[:-1]:
    p.terminate()

print("\n=== Verification ===")
if os.path.exists(result_file):
    with open(result_file, "rb") as f:
        result = pickle.load(f)
    print(f"✓ Downloaded {len(result)} chunks:")
    for h in result.keys():
        print(f"  - {h}: {len(result[h])} bytes")
else:
    print("✗ Result file not created")

cleanup_ports()
