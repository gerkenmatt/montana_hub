import argparse
import paho.mqtt.client as mqtt
import json
import sys
import os # <-- New import
from datetime import datetime # <-- New import

def main():
    """
    Main function to run the interactive MQTT host control panel.
    """
    parser = argparse.ArgumentParser(description="MQTT Host Control Panel")

    # --- Argument Definitions ---
    parser.add_argument("--broker", required=True, help="MQTT broker address")
    parser.add_argument("--port", type=int, default=8883, help="MQTT broker port (default: 8883)")
    parser.add_argument("--user", required=True, help="MQTT username")
    parser.add_argument("--password", required=True, help="MQTT password")
    parser.add_argument("--subscribe-topic", default="cabin/hub/#", help="Wildcard topic for subscribing to messages")
    parser.add_argument("--command-topic", default="cabin/hub/command", help="Topic for publishing commands")
    # New argument for saving screenshots
    parser.add_argument("--screenshot-dir", default="screenshots", help="Directory to save screenshots")
    
    args = parser.parse_args()

    # Create screenshot directory if it doesn't exist
    if not os.path.isdir(args.screenshot_dir):
        print(f"Creating screenshot directory: {args.screenshot_dir}")
        os.makedirs(args.screenshot_dir)

    # --- Callback Functions ---
    def on_connect(client, userdata, flags, rc, properties=None):
        """Callback for when the client connects to the broker."""
        if rc == 0:
            print("Successfully connected to MQTT Broker!")
            # Subscribe to main topic
            client.subscribe(args.subscribe_topic)
            print(f"Subscribed to wildcard topic: {args.subscribe_topic}")
            # Also subscribe to camera topics
            camera_topic = "cabin/camera/+/screenshot"
            client.subscribe(camera_topic)
            print(f"Subscribed to camera topic: {camera_topic}")
        else:
            print(f"Failed to connect, return code {rc}\n")
            sys.exit(1)

    def on_message(client, userdata, msg):
        """Callback for when a message is received from the broker."""
        prompt = "\nEnter command (ping, reboot, screenshot <cam_id>, quit): "
        
        # --- New logic to handle incoming screenshots ---
        if msg.topic.startswith("cabin/camera/") and msg.topic.endswith("/screenshot"):
            try:
                camera_id = msg.topic.split('/')[2]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(args.screenshot_dir, f"{camera_id}_{timestamp}.jpg")
                
                with open(filename, "wb") as f:
                    f.write(msg.payload)
                
                print(f"\n--- Screenshot Received ---")
                print(f"Saved screenshot from '{camera_id}' to '{filename}'")
                print("---------------------------")
            except Exception as e:
                print(f"\n[Error saving screenshot: {e}]")
            finally:
                print(prompt, end="", flush=True)
            return

        # Existing logic for JSON messages
        try:
            payload = json.loads(msg.payload.decode())
            print(f"\n--- Incoming Message ---")
            print(f"Topic: {msg.topic}")
            print(f"Payload: {json.dumps(payload, indent=2)}")
            print("------------------------")
        except json.JSONDecodeError:
            print(f"\n[Received non-JSON message on topic {msg.topic}: {msg.payload.decode()}]")
        finally:
            print(prompt, end="", flush=True)

    # --- Client Setup ---
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "host-control-panel")
    client.username_pw_set(args.user, args.password)
    client.tls_set()
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to broker at {args.broker}...")
    try:
        client.connect(args.broker, args.port, 60)
    except Exception as e:
        print(f"Could not connect to MQTT broker: {e}")
        sys.exit(1)

    client.loop_start()

    # --- Main User Interface Loop ---
    print("\nHost Control Panel is running.")
    
    try:
        while True:
            command_input = input("Enter command (ping, reboot, screenshot <cam_id>, quit): ")
            parts = command_input.lower().strip().split()
            
            if not parts:
                continue

            command = parts[0]
            
            if command == "ping":
                print("Sending 'ping' command...")
                payload = json.dumps({"action": "ping"})
                client.publish(args.command_topic, payload)
            
            elif command == "reboot":
                print("Sending 'reboot' command...")
                payload = json.dumps({"action": "reboot"})
                client.publish(args.command_topic, payload)

            # --- New command parsing ---
            elif command == "screenshot":
                if len(parts) > 1:
                    camera_id = parts[1]
                    print(f"Sending 'screenshot' command for camera '{camera_id}'...")
                    payload = json.dumps({"action": "screenshot", "camera_id": camera_id})
                    client.publish(args.command_topic, payload)
                else:
                    print("Usage: screenshot <camera_id>")

            elif command == "quit":
                print("Exiting...")
                break
            
            else:
                print("Unknown command. Please use 'ping', 'reboot', 'screenshot <cam_id>', or 'quit'.")

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        client.loop_stop()
        client.disconnect()
        print("Disconnected from broker.")

if __name__ == '__main__':
    main()