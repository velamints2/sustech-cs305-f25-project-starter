import sys
import select
import struct
import socket
import hashlib
import argparse
import pickle

from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from utils import simsocket
from utils.simsocket import AddressType
from utils.peer_context import PeerContext

"""
This is CS305 project skeleton code. Please refer to the example files -
  example/demo_receiver.py and
  example/demo_sender.py 
- to learn how to play with this skeleton.

The sample code is for reference only.
The given function is only one possible design, you are not required to follow it strictly.
We allow you to use better code design that conforms to best practices.
But ensure that your program's entry point is `peer.py` .
"""

BUF_SIZE: int = 1400
CHUNK_DATA_SIZE: int = 512 * 1024
MAX_PAYLOAD: int = 1024

HEADER_FMT: str = "BBHII"
HEADER_LEN: int = struct.calcsize(HEADER_FMT)


# Packet types
class PktType:
    """Packet type constants"""
    WHOHAS: int = 0
    IHAVE: int = 1
    GET: int = 2
    DATA: int = 3
    ACK: int = 4
    DENIED: int = 5


class Packet:
    """Utility class for building and parsing packets"""
    
    @staticmethod
    def build_header(pkt_type: int, seq: int, ack: int, payload_len: int) -> bytes:
        """
        Build a packet header.
        
        :param pkt_type: Type of the packet
        :param seq: Sequence number
        :param ack: ACK number
        :param payload_len: Length of the payload
        :return: Packed header bytes
        """
        pkt_len = HEADER_LEN + payload_len
        return struct.pack(
            HEADER_FMT,
            pkt_type,
            HEADER_LEN,
            socket.htons(pkt_len),
            socket.htonl(seq),
            socket.htonl(ack),
        )
    
    @staticmethod
    def build_packet(pkt_type: int, seq: int, ack: int, payload: bytes = b"") -> bytes:
        """
        Build a complete packet with header and payload.
        
        :param pkt_type: Type of the packet
        :param seq: Sequence number
        :param ack: ACK number
        :param payload: Payload bytes
        :return: Complete packet bytes
        """
        header = Packet.build_header(pkt_type, seq, ack, len(payload))
        return header + payload
    
    @staticmethod
    def parse_header(data: bytes) -> tuple[int, int, int, int, int]:
        """
        Parse packet header.
        
        :param data: Raw packet data
        :return: Tuple of (pkt_type, hlen, plen, seq, ack)
        """
        pkt_type, hlen, plen, seq, ack = struct.unpack(HEADER_FMT, data[:HEADER_LEN])
        plen = socket.ntohs(plen)
        seq = socket.ntohl(seq)
        ack = socket.ntohl(ack)
        return pkt_type, hlen, plen, seq, ack


class DownloadSession:
    """Manages the state of downloading a chunk from a peer"""
    
    def __init__(self, chunk_hash: str, peer_addr: AddressType):
        self.chunk_hash: str = chunk_hash
        self.peer_addr: AddressType = peer_addr
        self.data: bytes = b""
        self.expected_seq: int = 1
        self.completed: bool = False
        self.last_ack_time: float = 0
    
    def add_data(self, seq: int, data: bytes) -> bool:
        """
        Add received data to the session.
        
        :param seq: Sequence number of the data
        :param data: Data bytes
        :return: True if this is the expected sequence number
        """
        if seq == self.expected_seq:
            self.data += data
            self.expected_seq += 1
            if len(self.data) >= CHUNK_DATA_SIZE:
                self.completed = True
            return True
        return False
    
    def is_complete(self) -> bool:
        """Check if the chunk download is complete"""
        return self.completed


class UploadSession:
    """Manages the state of uploading a chunk to a peer"""
    
    def __init__(self, chunk_hash: str, chunk_data: bytes, peer_addr: AddressType):
        self.chunk_hash: str = chunk_hash
        self.chunk_data: bytes = chunk_data
        self.peer_addr: AddressType = peer_addr
        self.next_seq: int = 1
        self.completed: bool = False
        self.last_send_time: float = 0
    
    def get_next_data(self) -> tuple[int, bytes] | None:
        """
        Get the next chunk of data to send.
        
        :return: Tuple of (seq, data) or None if complete
        """
        if self.completed:
            return None
        
        offset = (self.next_seq - 1) * MAX_PAYLOAD
        if offset >= len(self.chunk_data):
            self.completed = True
            return None
        
        end = min(offset + MAX_PAYLOAD, len(self.chunk_data))
        data = self.chunk_data[offset:end]
        seq = self.next_seq
        return seq, data
    
    def handle_ack(self, ack_num: int) -> bool:
        """
        Handle an ACK for this upload session.
        
        :param ack_num: The ACK number received
        :return: True if this advances the session
        """
        if ack_num == self.next_seq:
            self.next_seq += 1
            offset = (self.next_seq - 1) * MAX_PAYLOAD
            if offset >= len(self.chunk_data):
                self.completed = True
            return True
        return False
    
    def is_complete(self) -> bool:
        """Check if the chunk upload is complete"""
        return self.completed


# Global session management
g_download_sessions: dict[tuple[AddressType, str], DownloadSession] = {}
g_upload_sessions: dict[AddressType, UploadSession] = {}

# Global download state
g_needed_chunks: set[str] = set()
g_downloaded_chunks: dict[str, bytes] = {}
g_output_file: str = ""

# Global peer context
g_context: PeerContext | None = None


def process_download(
    sock: simsocket.SimSocket, chunk_file: str, output_file: str
) -> None:
    """
    Initiates and manages the download of one or more chunks.

    This function is called when a 'DOWNLOAD' command is received. It is
    responsible for reading the chunk hashes from the ``chunk_file``,
    orchestrating the network requests (e.g., sending WHOHAS, GET) to
    retrieve all necessary chunks, and saving the completed data to
    the ``output_file``.

    :param sock: The :class:`simsocket.SimSocket` for network communication.
    :param chunk_file: Path to the file containing hashes of chunks to download.
    :param output_file: Path to the file to save the downloaded chunk data.
    """
    global g_needed_chunks, g_downloaded_chunks, g_output_file, g_context
    
    g_output_file = output_file
    g_needed_chunks.clear()
    g_downloaded_chunks.clear()
    
    # Step 1: Read chunk hashes from the chunk file
    chunk_hashes: list[str] = []
    with open(chunk_file, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                parts = line.split()
                if len(parts) >= 2:
                    # Format: index hash
                    chunk_hash = parts[1]
                    chunk_hashes.append(chunk_hash)
                    g_needed_chunks.add(chunk_hash)
    
    if not chunk_hashes:
        print("No chunks to download")
        return
    
    # Step 2: Build WHOHAS packet with all chunk hashes
    # Payload: concatenated 20-byte hashes
    payload = b""
    for chunk_hash_str in chunk_hashes:
        chunk_hash_bytes = bytes.fromhex(chunk_hash_str)
        payload += chunk_hash_bytes
    
    whohas_pkt = Packet.build_packet(PktType.WHOHAS, 0, 0, payload)
    
    # Step 3: Broadcast WHOHAS to all peers
    if g_context:
        for peer in g_context.peers:
            peer_id = int(peer[0])
            if peer_id != g_context.identity:
                peer_addr = (peer[1], int(peer[2]))
                sock.sendto(whohas_pkt, peer_addr)
                if g_context.verbose >= 2:
                    print(f"Sent WHOHAS to peer {peer_id} at {peer_addr}")


def process_inbound_udp(sock: simsocket.SimSocket) -> None:
    """
    Processes a single inbound packet received from the socket.

    This function should receive data, unpack the standard header,
    and then use the packet type to route the packet to the appropriate
    handling logic (e.g., for WHOHAS, IHAVE, GET, DATA, ACK).

    :param sock: The :class:`simsocket.SimSocket` with a pending packet.
    :type sock: simsocket.SimSocket
    """
    global g_context, g_download_sessions, g_upload_sessions
    global g_needed_chunks, g_downloaded_chunks, g_output_file
    
    # Receive pkt
    pkt: bytes
    from_addr: AddressType
    pkt, from_addr = sock.recvfrom(BUF_SIZE)

    # Parse header
    pkt_type, hlen, plen, seq, ack = Packet.parse_header(pkt)
    payload: bytes = pkt[HEADER_LEN:]
    
    if g_context and g_context.verbose >= 3:
        print(f"Received pkt type {pkt_type} from {from_addr}, seq={seq}, ack={ack}")
    
    # Route packet based on type
    if pkt_type == PktType.WHOHAS:
        # Handle WHOHAS: check if we have the requested chunks
        # Payload contains concatenated 20-byte chunk hashes
        num_hashes = len(payload) // 20
        requested_hashes = []
        available_hashes = []
        
        for i in range(num_hashes):
            chunk_hash_bytes = payload[i*20:(i+1)*20]
            chunk_hash_str = chunk_hash_bytes.hex()
            requested_hashes.append(chunk_hash_str)
            
            if g_context and chunk_hash_str in g_context.has_chunks:
                available_hashes.append(chunk_hash_str)
        
        # Check if we can accept more upload connections
        if g_context and len(g_upload_sessions) >= g_context.max_conn:
            # Send DENIED
            denied_pkt = Packet.build_packet(PktType.DENIED, 0, 0)
            sock.sendto(denied_pkt, from_addr)
            if g_context.verbose >= 2:
                print(f"Sent DENIED to {from_addr} (max connections reached)")
        elif available_hashes:
            # Send IHAVE with available chunk hashes
            ihave_payload = b""
            for chunk_hash_str in available_hashes:
                ihave_payload += bytes.fromhex(chunk_hash_str)
            
            ihave_pkt = Packet.build_packet(PktType.IHAVE, 0, 0, ihave_payload)
            sock.sendto(ihave_pkt, from_addr)
            if g_context and g_context.verbose >= 2:
                print(f"Sent IHAVE to {from_addr} with {len(available_hashes)} chunks")
    
    elif pkt_type == PktType.IHAVE:
        # Handle IHAVE: extract available chunks and send GET requests
        num_hashes = len(payload) // 20
        
        for i in range(num_hashes):
            chunk_hash_bytes = payload[i*20:(i+1)*20]
            chunk_hash_str = chunk_hash_bytes.hex()
            
            # Check if we still need this chunk and don't have a session for it
            session_key = (from_addr, chunk_hash_str)
            if chunk_hash_str in g_needed_chunks and session_key not in g_download_sessions:
                # Send GET request for this chunk
                get_payload = chunk_hash_bytes
                get_pkt = Packet.build_packet(PktType.GET, 0, 0, get_payload)
                sock.sendto(get_pkt, from_addr)
                
                # Create download session
                g_download_sessions[session_key] = DownloadSession(chunk_hash_str, from_addr)
                
                if g_context and g_context.verbose >= 2:
                    print(f"Sent GET to {from_addr} for chunk {chunk_hash_str[:8]}...")
                
                # Only request one chunk per peer at a time (task 4.2 requirement)
                break
    
    elif pkt_type == PktType.DENIED:
        # Handle DENIED: peer cannot send to us right now
        if g_context and g_context.verbose >= 2:
            print(f"Received DENIED from {from_addr}")
        # Could implement retry logic here, but for now just log it
    
    elif pkt_type == PktType.GET:
        # Handle GET: peer wants to download a chunk from us
        chunk_hash_bytes = payload[:20]
        chunk_hash_str = chunk_hash_bytes.hex()
        
        # Check if we have this chunk and can send it
        if g_context and chunk_hash_str in g_context.has_chunks:
            # Check if we already have an upload session with this peer
            if from_addr not in g_upload_sessions:
                # Create upload session
                chunk_data = g_context.has_chunks[chunk_hash_str]
                g_upload_sessions[from_addr] = UploadSession(chunk_hash_str, chunk_data, from_addr)
                
                # Send first DATA packet
                next_data = g_upload_sessions[from_addr].get_next_data()
                if next_data:
                    seq, data = next_data
                    data_pkt = Packet.build_packet(PktType.DATA, seq, 0, data)
                    sock.sendto(data_pkt, from_addr)
                    if g_context.verbose >= 2:
                        print(f"Started upload to {from_addr}, sent seq {seq}")
    
    elif pkt_type == PktType.DATA:
        # Handle DATA: receiving chunk data
        session_key = None
        for key, session in g_download_sessions.items():
            if key[0] == from_addr:
                session_key = key
                break
        
        if session_key:
            session = g_download_sessions[session_key]
            if session.add_data(seq, payload):
                # Send ACK
                ack_pkt = Packet.build_packet(PktType.ACK, 0, seq, b"")
                sock.sendto(ack_pkt, from_addr)
                
                # Check if download is complete
                if session.is_complete():
                    chunk_hash = session.chunk_hash
                    g_downloaded_chunks[chunk_hash] = session.data
                    g_needed_chunks.discard(chunk_hash)
                    
                    if g_context and g_context.verbose >= 2:
                        print(f"Completed download of chunk {chunk_hash[:8]}...")
                    
                    # Remove session
                    del g_download_sessions[session_key]
                    
                    # Check if all chunks are downloaded
                    if not g_needed_chunks:
                        # Save to file
                        with open(g_output_file, "wb") as f:
                            pickle.dump(g_downloaded_chunks, f)
                        print(f"GOT {g_output_file}")
                        
                        # Add downloaded chunks to our collection
                        if g_context:
                            g_context.has_chunks.update(g_downloaded_chunks)
    
    elif pkt_type == PktType.ACK:
        # Handle ACK: acknowledgment for our DATA packet
        if from_addr in g_upload_sessions:
            session = g_upload_sessions[from_addr]
            if session.handle_ack(ack):
                if not session.is_complete():
                    # Send next DATA packet
                    next_data = session.get_next_data()
                    if next_data:
                        seq, data = next_data
                        data_pkt = Packet.build_packet(PktType.DATA, seq, 0, data)
                        sock.sendto(data_pkt, from_addr)
                else:
                    # Upload complete, remove session
                    if g_context and g_context.verbose >= 2:
                        print(f"Completed upload to {from_addr}")
                    del g_upload_sessions[from_addr]


def process_user_input(sock: simsocket.SimSocket) -> None:
    """
    Handles a single line of user input from ``sys.stdin``.

    Parses the input and, if the command is "DOWNLOAD", calls
    :func:`process_download` with the provided file paths.

    :param sock: The :class:`simsocket.SimSocket` to be passed to
                 :func:`process_download`.
    :type sock: simsocket.SimSocket
    """
    command, chunk_file, output_file = input().split()
    if command == "DOWNLOAD":
        process_download(sock, chunk_file, output_file)
    else:
        pass


def peer_run(context: PeerContext) -> None:
    """
    Runs the main event loop for the peer.

    Initializes the :class:`simsocket.SimSocket` and enters a loop
    that uses :func:`select.select` to monitor both the socket for
    inbound packets (handled by :func:`process_inbound_udp`) and
    ``sys.stdin`` for user commands (handled by
    :func:`process_user_input`).

    :param context: The peer's configuration and state object.
    """
    global g_context
    g_context = context
    
    addr: AddressType = (context.ip, context.port)
    sock = simsocket.SimSocket(context.identity, addr, verbose=context.verbose)

    try:
        while True:
            ready: tuple[list, list, list] = select.select(
                [sock, sys.stdin], [], [], 0.1
            )
            read_ready: list = ready[0]
            if len(read_ready) > 0:
                if sock in read_ready:
                    process_inbound_udp(sock)
                if sys.stdin in read_ready:
                    process_user_input(sock)
            else:
                # No pkt nor input arrives during this period
                pass
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


def main() -> None:
    """
    Main entry point for the peer script.

    Parses command-line arguments, initializes the global PeerContext,
    and starts the peer's main run loop.
    """

    """
    -i: ID, it is the index in nodes.map

    -p: Peer list file, it will be in the form "*.map" like nodes.map.

    -c: Chunkfile, a dictionary dumped by pickle. It will be loaded automatically in peer_context.
        The loaded dictionary has the form: {chunkhash: chunkdata}

    -m: The max number of peer that you can send chunk to concurrently.
        If more peers ask you for chunks, you should reply "DENIED"

    -v: verbose level for printing logs to stdout, 0 for no verbose, 1 for WARNING level, 2 for INFO, 3 for DEBUG.

    -t: pre-defined timeout. If it is not set, you should estimate timeout via RTT.
        If it is set, you should not change this time out.
        The timeout will be set when running test scripts. PLEASE do not change timeout if it set.
    """

    parser = argparse.ArgumentParser(
        description="CS305 Project Peer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--identity",
        dest="identity",
        type=int,
        help="Which peer # am I?",
    )
    parser.add_argument(
        "-p",
        "--peer-file",
        dest="peer_file",
        type=str,
        help="The list of all peers",
        default="nodes.map",
    )
    parser.add_argument(
        "-c",
        "--chunk-file",
        dest="chunk_file",
        type=str,
        help="Pickle dumped dictionary {chunkhash: chunkdata}",
    )
    parser.add_argument(
        "-m",
        "--max-conn",
        dest="max_conn",
        type=int,
        help="Max # of concurrent sending",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        type=int,
        help="verbose level",
        default=0,
    )
    parser.add_argument(
        "-t",
        "--timeout",
        dest="timeout",
        type=int,
        help="pre-defined timeout",
        default=0,
    )
    args = parser.parse_args()

    context = PeerContext(args)
    peer_run(context)


if __name__ == "__main__":
    main()
