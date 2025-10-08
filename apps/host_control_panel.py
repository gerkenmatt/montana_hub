import argparse
import paho.mqtt.client as mqtt
import json
import sys

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
    
    args = parser.parse_args()

    # --- Callback Functions ---
    def on_connect(client, userdata, flags, rc, properties=None):
        """Callback for when the client connects to the broker."""
        if rc == 0:
            print("Successfully connected to MQTT Broker!")
            client.subscribe(args.subscribe_topic)
            print(f"Subscribed to wildcard topic: {args.subscribe_topic}")
        else:
            print(f"Failed to connect, return code {rc}\n")
            sys.exit(1)

    def on_message(client, userdata, msg):
        """Callback for when a message is received from the broker."""
        prompt = "\nEnter command (ping, reboot, quit): "
        try:
            payload = json.loads(msg.payload.decode())
            print(f"\n--- Incoming Message ---")
            print(f"Topic: {msg.topic}")
            print(f"Payload: {json.dumps(payload, indent=2)}")
            print("------------------------")
        except json.JSONDecodeError:
            print(f"\n[Received non-JSON message on topic {msg.topic}: {msg.payload.decode()}]")
        finally:
            # Refresh the input prompt
            print(prompt, end="", flush=True)

    # --- Client Setup ---
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "host-control-panel")

    # Assign credentials and enable TLS
    client.username_pw_set(args.user, args.password)
    client.tls_set()

    # Assign callback functions
    client.on_connect = on_connect
    client.on_message = on_message

    # Connect to the broker
    print(f"Connecting to broker at {args.broker}...")
    try:
        client.connect(args.broker, args.port, 60)
    except Exception as e:
        print(f"Could not connect to MQTT broker: {e}")
        sys.exit(1)

    # Start the background thread for network communication
    client.loop_start()

    # --- Main User Interface Loop ---
    print("\nHost Control Panel is running.")
    
    try:
        while True:
            command = input("Enter command (ping, reboot, quit): ")
            
            if command.lower() == "ping":
                print("Sending 'ping' command...")
                payload = json.dumps({"action": "ping"})
                client.publish(args.command_topic, payload)
            
            elif command.lower() == "reboot":
                print("Sending 'reboot' command...")
                payload = json.dumps({"action": "reboot"})
                client.publish(args.command_topic, payload)

            elif command.lower() == "quit":
                print("Exiting...")
                break
            
            else:
                print("Unknown command. Please use 'ping', 'reboot', or 'quit'.")

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        client.loop_stop()
        client.disconnect()
        print("Disconnected from broker.")

if __name__ == '__main__':
    main()