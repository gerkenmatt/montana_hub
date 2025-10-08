import argparse
import paho.mqtt.client as mqtt

def main(broker, port, user, password, topic):
    """
    Connects to an MQTT broker, publishes a message, and disconnects.
    Sensitive connection details are passed as arguments.
    """
    # Create a new MQTT client instance
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "publisher-client")

    # Set username and password
    client.username_pw_set(user, password)

    # Enable TLS encryption
    client.tls_set()

    # Connect to the broker
    print(f"Connecting to broker at {broker}...")
    try:
        client.connect(broker, port, 60)
    except Exception as e:
        print(f"Error connecting to broker: {e}")
        return

    # Publish a message
    message = "Hello from Python!"
    print(f"Publishing message to topic `{topic}`")
    client.publish(topic, message)

    # Disconnect from the broker
    client.disconnect()
    print("Disconnected.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MQTT Publisher")
    
    # Define command-line arguments
    parser.add_argument("--broker", required=True, help="MQTT broker address")
    parser.add_argument("--port", type=int, default=8883, help="MQTT broker port (default: 8883)")
    parser.add_argument("--user", required=True, help="MQTT username")
    parser.add_argument("--password", required=True, help="MQTT password")
    parser.add_argument("--topic", required=True, help="MQTT topic to publish to")

    # Parse arguments from the command line
    args = parser.parse_args()

    # Call the main function with the parsed arguments
    main(args.broker, args.port, args.user, args.password, args.topic)