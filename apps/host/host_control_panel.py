import argparse
import paho.mqtt.client as mqtt
import json
import sys
import os
from datetime import datetime
from rich.console import Console
from rich.panel import Panel

# NEW IMPORTS for non-blocking keyboard input
import time
import select
import tty
import termios

# Initialize the rich console
console = Console()

# NEW: Global flag for "human status mode"
human_status_mode = False

def main():
    """
    Main function to run the interactive MQTT host control panel.
    """
    global human_status_mode # Make the global flag accessible

    parser = argparse.ArgumentParser(description="MQTT Host Control Panel")
    # (Arguments are the same as before)
    parser.add_argument("--broker", required=True, help="MQTT broker address")
    parser.add_argument("--port", type=int, default=8883, help="MQTT broker port (default: 8883)")
    parser.add_argument("--user", required=True, help="MQTT username")
    parser.add_argument("--password", required=True, help="MQTT password")
    parser.add_argument("--subscribe-topic", default="cabin/hub/#", help="Wildcard topic for subscribing to messages")
    parser.add_argument("--command-topic", default="cabin/hub/command", help="Topic for publishing commands")
    parser.add_argument("--screenshot-dir", default="screenshots", help="Directory to save screenshots")
    
    args = parser.parse_args()

    if not os.path.isdir(args.screenshot_dir):
        console.print(f"Creating screenshot directory: {args.screenshot_dir}", style="yellow")
        os.makedirs(args.screenshot_dir)

    # --- Callback Functions ---
    def on_connect(client, userdata, flags, rc, properties=None):
        """Callback for when the client connects to the broker."""
        if rc == 0:
            console.print("Successfully connected to MQTT Broker!", style="bold green")
            client.subscribe(args.subscribe_topic)
            console.print(f"Subscribed to wildcard topic: {args.subscribe_topic}")
            camera_topic = "cabin/camera/+/screenshot"
            client.subscribe(camera_topic)
            console.print(f"Subscribed to camera topic: {camera_topic}")
            detection_topic = "cabin/camera/+/detection"
            client.subscribe(detection_topic)
            console.print(f"Subscribed to detection topic: {detection_topic}")

            # --- NEW: Print the FIRST prompt here ---
            if not human_status_mode:
                print("\nEnter command (ping, reboot, screenshot <cam_id>, human, quit): ", end="", flush=True)
            # --- END NEW ---
        else:
            console.print(f"Failed to connect, return code {rc}\n", style="bold red")
            sys.exit(1)

    def on_message(client, userdata, msg):
        """Callback for when a message is received from the broker."""
        prompt = "\nEnter command (ping, reboot, screenshot <cam_id>, human, quit): "
        
        # --- Handle incoming screenshots ---
        if msg.topic.startswith("cabin/camera/") and msg.topic.endswith("/screenshot"):
            if not human_status_mode: 
                try:
                    camera_id = msg.topic.split('/')[2]
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = os.path.join(args.screenshot_dir, f"{camera_id}_{timestamp}.jpg")
                    with open(filename, "wb") as f:
                        f.write(msg.payload)
                    console.print(Panel(f"Saved from [bold]{camera_id}[/bold] to:\n[cyan]{filename}[/cyan]", title="📸 Screenshot Received 📸", style="bold blue"))
                except Exception as e:
                    console.print(f"\n[Error saving screenshot: {e}]", style="red")
                finally:
                    # --- MOVED HERE ---
                    print(prompt, end="", flush=True)
            
        # --- Handle detection alerts ---
        elif msg.topic.startswith("cabin/camera/") and msg.topic.endswith("/detection"):
            if human_status_mode:
                try:
                    camera_id = msg.topic.split('/')[2]
                    payload = json.loads(msg.payload.decode())
                    status_text = payload.get("event", payload.get("status", "UNKNOWN")).upper()

                    if "PERSON_DETECTED" in status_text or "HUMAN" in status_text:
                        console.print(Panel(f"[bold]Camera: {camera_id}[/bold]", title="🚨 HUMAN DETECTED 🚨", style="bold red", padding=(1, 4)))
                    else: 
                        console.print(Panel(f"[bold]Camera: {camera_id}[/bold]", title=f"✅ STATUS: {status_text}", style="bold green", padding=(1, 4)))
                except Exception as e:
                    console.print(f"\n[Error processing detection alert: {e}]", style="red")
            # If not in human_status_mode, DO NOTHING (no prompt)
        
        # --- Handle standard JSON status messages ---
        elif not human_status_mode:
            try:
                payload = json.loads(msg.payload.decode())
                console.print(Panel(json.dumps(payload, indent=2), title=f"Incoming Message: {msg.topic}", style="dim"))
            except json.JSONDecodeError:
                console.print(f"\n[Received non-JSON message on topic {msg.topic}: {msg.payload.decode()}]", style="yellow")
            finally:
                # --- MOVED HERE ---
                print(prompt, end="", flush=True)
        
        # --- REMOVED prompt printing from here ---

    # --- Client Setup (no changes) ---
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "host-control-panel")
    client.username_pw_set(args.user, args.password)
    client.tls_set()
    client.on_connect = on_connect
    client.on_message = on_message

    console.print(f"Connecting to broker at {args.broker}...", style="cyan")
    try:
        client.connect(args.broker, args.port, 60)
    except Exception as e:
        console.print(f"Could not connect to MQTT broker: {e}", style="bold red")
        sys.exit(1)

    client.loop_start()

    # --- Main User Interface Loop (MODIFIED) ---
    console.print("\nHost Control Panel is running.", style="bold")
    
    try:
        while True:
            # The prompt is now printed by on_connect or on_message
            command_input = input() # No prompt string here
            
            parts = command_input.lower().strip().split()
            
            if not parts:
                # User just hit Enter, print a new prompt
                if not human_status_mode:
                    print("\nEnter command (ping, reboot, screenshot <cam_id>, human, quit): ", end="", flush=True)
                continue
                
            command = parts[0]
            
            if command == "ping":
                console.print("Sending 'ping' command...", style="yellow")
                payload = json.dumps({"action": "ping"})
                client.publish(args.command_topic, payload)
            
            elif command == "reboot":
                console.print("Sending 'reboot' command...", style="yellow")
                payload = json.dumps({"action": "reboot"})
                client.publish(args.command_topic, payload)

            elif command == "screenshot":
                if len(parts) > 1:
                    camera_id = parts[1]
                    console.print(f"Sending 'screenshot' command for camera '{camera_id}'...", style="yellow")
                    payload = json.dumps({"action": "screenshot", "camera_id": camera_id})
                    client.publish(args.command_topic, payload)
                else:
                    console.print("Usage: screenshot <camera_id>", style="red")
            
            # --- HUMAN STATUS MODE ---
            elif command == "human":
                human_status_mode = True
                console.print(Panel("Entering Human Detection Mode. Press 'q' to quit.", style="bold cyan"))
                
                # Save old terminal settings
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                try:
                    # Set terminal to "cbreak" mode to read single chars
                    tty.setcbreak(sys.stdin.fileno())
                    
                    # This is the "human mode" non-blocking loop
                    while human_status_mode:
                        # Check if a key is pressed (timeout of 0.1s)
                        if select.select([sys.stdin], [], [], 0.1)[0]:
                            key = sys.stdin.read(1)
                            if key.lower() == 'q':
                                human_status_mode = False # Signal loop to exit
                        # Let the MQTT thread do its work
                        time.sleep(0.05) 
                
                finally:
                    # Always restore terminal settings
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                
                console.print(Panel("Exiting Human Detection Mode.", style="bold cyan"))
                # Print a new prompt after exiting human mode
                print("\nEnter command (ping, reboot, screenshot <cam_id>, human, quit): ", end="", flush=True)

            elif command == "quit":
                console.print("Exiting...", style="bold")
                break
            
            else:
                console.print("Unknown command. Please use 'ping', 'reboot', 'screenshot <cam_id>', 'human', or 'quit'.", style="red")

    except KeyboardInterrupt:
        console.print("\nExiting...", style="bold")
    finally:
        human_status_mode = True # Stop prompts from printing during shutdown
        client.loop_stop()
        client.disconnect()
        console.print("Disconnected from broker.", style="bold")

if __name__ == '__main__':
    main()