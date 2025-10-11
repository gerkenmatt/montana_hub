import socket
import sys

# --- Configuration ---
HOST = '127.0.0.1'
PORT = 9090

if len(sys.argv) > 1:
    PORT = int(sys.argv[1])

print(f"Attempting to connect to {HOST}:{PORT}...")

try:
    # Create a socket and set a 5-second timeout
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect((HOST, PORT))
        print(f"SUCCESS: A connection to port {PORT} was established.")

except socket.timeout:
    print(f"FAILURE: Connection to port {PORT} timed out.")
except ConnectionRefusedError:
    print(f"FAILURE: Connection to port {PORT} was refused.")
except Exception as e:
    print(f"FAILURE: An unexpected error occurred: {e}")