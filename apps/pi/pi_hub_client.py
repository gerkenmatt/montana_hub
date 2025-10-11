import argparse
import paho.mqtt.client as mqtt
import time
import json
import sys
import subprocess # <-- New import
import os         # <-- New import

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
    # Updated help text for camera configuration
    parser.add_argument("--cameras-config", required=True, help="Path to JSON file with camera RTSP URLs (e.g., {\"cam1\": \"rtsp://...\"})")

    args = parser.parse_args()

    # --- Load Camera Config ---
    try:
        with open(args.cameras_config, 'r') as f:
            cameras = json.load(f)
        print(f"Loaded {len(cameras)} camera configurations.")
    except FileNotFoundError:
        print(f"Error: Camera config file not found at {args.cameras_config}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {args.cameras_config}")
        sys.exit(1)

    # --- Callback Functions ---
    def on_connect(client, userdata, flags, rc, properties=None):
        """Callback for when the client connects to the broker."""
        if rc == 0:
            print("Successfully connected to MQTT Broker!")
            client.subscribe(args.command_topic)
            print(f"Subscribed to command topic: {args.command_topic}")
        else:
            print(f"Failed to connect, return code {rc}\n")
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
                response_payload = json.dumps({"status": "rebooting"})
                client.publish(args.status_topic, response_payload)
            
            # --- Updated action handler for screenshot using FFmpeg ---
            elif action == "screenshot":
                camera_id = payload.get("camera_id")
                print(f"Received screenshot command for camera: {camera_id}")
                
                if not camera_id or camera_id not in cameras:
                    error_msg = f"Unknown or missing camera_id: {camera_id}"
                    print(f"Error: {error_msg}")
                    response = {"status": "screenshot_failed", "camera_id": camera_id, "error": error_msg}
                    client.publish(args.status_topic, json.dumps(response))
                    return
                
                rtsp_url = cameras.get(camera_id)
                temp_image_path = f"/tmp/{camera_id}_snapshot.jpg"
                screenshot_topic = f"cabin/camera/{camera_id}/screenshot"
                
                ffmpeg_command = [
                    "ffmpeg",
                    "-rtsp_transport", "tcp",
                    "-i", rtsp_url,
                    "-vframes", "1",
                    "-q:v", "2",
                    "-y", # Overwrite output file
                    temp_image_path
                ]
                
                try:
                    print(f"Executing: {' '.join(ffmpeg_command)}")
                    # Run the command, raise exception on failure, capture output, and set a timeout
                    result = subprocess.run(
                        ffmpeg_command,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=15 # 15-second timeout to connect and grab a frame
                    )
                    
                    print(f"FFmpeg successfully created snapshot at {temp_image_path}")
                    
                    with open(temp_image_path, "rb") as f:
                        image_bytes = f.read()

                    client.publish(screenshot_topic, payload=image_bytes, qos=1)
                    print(f"Successfully published screenshot to {screenshot_topic}")

                    status_payload = {"status": "screenshot_success", "camera_id": camera_id, "timestamp": time.time()}
                    client.publish(args.status_topic, json.dumps(status_payload))

                except FileNotFoundError:
                    error_msg = "ffmpeg command not found. Is it installed and in the system's PATH?"
                    print(f"Error: {error_msg}")
                    status_payload = {"status": "screenshot_failed", "camera_id": camera_id, "error": error_msg}
                    client.publish(args.status_topic, json.dumps(status_payload))
                except subprocess.CalledProcessError as e:
                    error_msg = f"FFmpeg failed: {e.stderr}"
                    print(f"Error: {error_msg}")
                    status_payload = {"status": "screenshot_failed", "camera_id": camera_id, "error": error_msg}
                    client.publish(args.status_topic, json.dumps(status_payload))
                except subprocess.TimeoutExpired:
                    error_msg = "FFmpeg command timed out. Camera may be unreachable."
                    print(f"Error: {error_msg}")
                    status_payload = {"status": "screenshot_failed", "camera_id": camera_id, "error": error_msg}
                    client.publish(args.status_topic, json.dumps(status_payload))
                finally:
                    # Clean up the temporary file
                    if os.path.exists(temp_image_path):
                        os.remove(temp_image_path)
                        print(f"Removed temporary file: {temp_image_path}")
            
            else:
                print(f"Unknown action received: {action}")

        except json.JSONDecodeError:
            print("Error: Received message is not valid JSON.")
        except Exception as e:
            print(f"An error occurred while processing message: {e}")

    # --- Client Setup (no changes from here down) ---
    lwt_payload = json.dumps({"status": "offline", "reason": "unclean_disconnect"})
    lwt_topic = args.status_topic
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "pi-hub-client")
    client.will_set(lwt_topic, payload=lwt_payload, qos=1, retain=True)
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

    print("Starting main application loop... Press Ctrl+C to exit.")
    try:
        while True:
            heartbeat_payload = json.dumps({ "status": "online", "timestamp": time.time() })
            client.publish(args.status_topic, heartbeat_payload, qos=1, retain=True)
            print(f"Published heartbeat to {args.status_topic}")
            time.sleep(30)
    except KeyboardInterrupt:
        print("\nCaught interrupt signal, shutting down gracefully.")
    finally:
        final_payload = json.dumps({"status": "offline", "reason": "clean_shutdown"})
        client.publish(args.status_topic, final_payload, qos=1, retain=True)
        print("Published final offline status.")
        time.sleep(1)
        
        client.loop_stop()
        client.disconnect()
        print("Client disconnected.")

if __name__ == '__main__':
    main()