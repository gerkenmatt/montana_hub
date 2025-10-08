import argparse
import paho.mqtt.client as mqtt

def main():
    """
    Connects to an MQTT broker, subscribes to a topic, and waits for messages.
    """
    parser = argparse.ArgumentParser(description="MQTT Subscriber")
    
    # Define command-line arguments
    parser.add_argument("--broker", required=True, help="MQTT broker address")
    parser.add_argument("--port", type=int, default=8883, help="MQTT broker port (default: 8883)")
    parser.add_argument("--user", required=True, help="MQTT username")
    parser.add_argument("--password", required=True, help="MQTT password")
    parser.add_argument("--topic", required=True, help="MQTT topic to subscribe to")

    # Parse arguments from the command line
    args = parser.parse_args()

    # --- Callback Functions ---
    # This function is called when the client successfully connects to the broker.
    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            print("Connected to MQTT Broker!")
            # Subscribe to the topic once connected
            print(f"Subscribing to topic `{args.topic}`")
            client.subscribe(args.topic)
        else:
            print(f"Failed to connect, return code {rc}\n")

    # This function is called when a message is received from the broker.
    def on_message(client, userdata, msg):
        print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")

    # --- Client Setup ---
    # Create a new MQTT client instance
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "subscriber-client")

    # Set username and password
    client.username_pw_set(args.user, args.password)

    # Enable TLS encryption
    client.tls_set()

    # Assign the callback functions
    client.on_connect = on_connect
    client.on_message = on_message

    # Connect to the broker
    print(f"Connecting to broker at {args.broker}...")
    try:
        client.connect(args.broker, args.port, 60)
    except Exception as e:
        print(f"Error connecting to broker: {e}")
        return

    # Start a blocking loop to process messages.
    client.loop_forever()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSubscriber stopped.")