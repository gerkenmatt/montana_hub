import cv2
import argparse
import sys

def main():
    """
    Connects to a TCP video stream using OpenCV and displays it in a window.
    """
    # --- Argument Parsing ---
    # Set up command-line arguments to make the script flexible.
    parser = argparse.ArgumentParser(
        description="Connect to and display a TCP video stream from the Pi hub.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--ip",
        default="10.0.0.2",
        help="The VPN IP address of the Raspberry Pi.\n(default: 10.0.0.2)"
    )
    parser.add_argument(
        "--port",
        default="9090",
        help="The port for the specific camera stream on the Pi.\n(default: 9090)"
    )
    args = parser.parse_args()

    # --- Stream Connection ---
    # Construct the full stream URL for OpenCV.
    stream_url = f"tcp://{args.ip}:{args.port}"
    print(f"Attempting to connect to stream at: {stream_url}")

    # Create the VideoCapture object to connect to the stream.
    cap = cv2.VideoCapture(stream_url)

    # Check if the connection was successful.
    if not cap.isOpened():
        print("\n--- Connection Failed ---")
        print("Error: Cannot open the video stream.")
        print("Troubleshooting steps:")
        print(" 1. Ensure your WireGuard VPN is active on this machine.")
        print(f" 2. Verify the Pi's ffmpeg service for port {args.port} is running.")
        print(f" 3. Check that you can ping the Pi: ping {args.ip}")
        print("-------------------------\n")
        sys.exit(1)

    print("Connection successful. Displaying stream...")

    # --- Main Display Loop ---
    while True:
        try:
            # Read one frame from the video stream.
            ret, frame = cap.read()

            # If 'ret' is False, it means the frame could not be read (stream ended or error).
            if not ret:
                print("Stream ended or connection lost. Exiting.")
                break

            # Display the captured frame in a window.
            cv2.imshow('Live Cabin Feed (Press "q" to quit)', frame)

            # Wait for 1 millisecond for a key press.
            # The '0xFF' mask is a standard good practice for 64-bit systems.
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

        except KeyboardInterrupt:
            # Allow quitting with Ctrl+C in the terminal.
            print("\nCaught Ctrl+C. Exiting.")
            break

    # --- Cleanup ---
    print("Closing stream viewer.")
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()