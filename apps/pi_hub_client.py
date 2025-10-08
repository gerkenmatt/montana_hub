import argparse
import paho.mqtt.client as mqtt
import time
import json
import sys

def main():
    """
    Main function to run the MQTT client for the Pi IoT hub.
    """
    parser = argparse.ArgumentParser(description="Raspberry Pi MQTT IoT Hub Client")

    # --- Argument Definitions ---
    parser.add_argument("--broker", required=True, help="MQTT broker address")
    parser.add_argument("--port", type=int, default=8883, help="MQTT broker port (default: 8883)")
    parser.add_argument("--user", required=True, help="MQTT username")
    parser.add_argument("--password", required=True, help="MQTT password")
    parser.add_argument("--status-topic", default="cabin/hub/status", help="Topic for publishing status and heartbeat")
    parser.add_argument("--command-topic", default="cabin/hub/command", help="Topic for subscribing to commands")

    args = parser.parse_args()

    # --- Callback Functions ---
    def on_connect(client, userdata, flags, rc, properties=None):
        """Callback for when the client connects to the broker."""
        if rc == 0:
            print("Successfully connected to MQTT Broker!")
            # Subscribe to the command topic upon successful connection
            client.subscribe(args.command_topic)
            print(f"Subscribed to command topic: {args.command_topic}")
        else:
            print(f"Failed to connect, return code {rc}\n")
            # Exit if the connection fails
            sys.exit(1)

    def on_message(client, userdata, msg):
        """Callback for when a message is received."""
        print(f"Received message on topic `{msg.topic}`: {msg.payload.decode()}")
        try:
            payload = json.loads(msg.payload.decode())
            action = payload.get("action")

            if action == "ping":
                print("Received ping command! Responding.")
                response_payload = json.dumps({"response": "pong", "timestamp": time.time()})
                client.publish(args.status_topic, response_payload)
            elif action == "reboot":
                print("Received reboot command! (Simulating reboot)")
                # In a real scenario, you would execute: os.system('sudo reboot')
                response_payload = json.dumps({"status": "rebooting"})
                client.publish(args.status_topic, response_payload)
            else:
                print(f"Unknown action received: {action}")

        except json.JSONDecodeError:
            print("Error: Received message is not valid JSON.")
        except Exception as e:
            print(f"An error occurred while processing message: {e}")

    # --- Client Setup ---
    # Define the Last Will and Testament (LWT) message
    lwt_payload = json.dumps({"status": "offline", "reason": "unclean_disconnect"})
    lwt_topic = args.status_topic

    # Create a new MQTT client instance
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "pi-hub-client")

    # Set the LWT
    client.will_set(lwt_topic, payload=lwt_payload, qos=1, retain=True)

    # Assign credentials and enable TLS
    client.username_pw_set(args.user, args.password)
    client.tls_set()

    # Assign callbacks
    client.on_connect = on_connect
    client.on_message = on_message

    # Connect to the broker
    print(f"Connecting to broker at {args.broker}...")
    try:
        client.connect(args.broker, args.port, 60)
    except Exception as e:
        print(f"Could not connect to MQTT broker: {e}")
        sys.exit(1)

    # Start the non-blocking network loop
    client.loop_start()

    # --- Main Application Loop ---
    print("Starting main application loop... Press Ctrl+C to exit.")
    try:
        while True:
            heartbeat_payload = json.dumps({
                "status": "online",
                "timestamp": time.time()
            })
            # Publish heartbeat with retain flag so new clients get the last known status
            client.publish(args.status_topic, heartbeat_payload, qos=1, retain=True)
            print(f"Published heartbeat to {args.status_topic}")
            time.sleep(30)
    except KeyboardInterrupt:
        print("\nCaught interrupt signal, shutting down gracefully.")
    finally:
        # Publish a final "offline" message before disconnecting
        final_payload = json.dumps({"status": "offline", "reason": "clean_shutdown"})
        client.publish(args.status_topic, final_payload, qos=1, retain=True)
        print("Published final offline status.")
        time.sleep(1) # Give a moment for the message to send
        
        client.loop_stop()
        client.disconnect()
        print("Client disconnected.")

if __name__ == '__main__':
    main()