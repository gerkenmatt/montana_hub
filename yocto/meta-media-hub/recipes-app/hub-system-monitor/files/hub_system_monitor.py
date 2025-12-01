import argparse
import paho.mqtt.client as mqtt
import time
import json
import sys
import os
import psutil
import subprocess

# --- Constants ---
STATUS_TOPIC = "cabin/hub/status"
COMMAND_TOPIC = "cabin/hub/command"

def get_system_stats():
    """Gathers system health metrics."""
    try:
        # CPU Load (Blocking call for 0.1s for accuracy)
        cpu_pct = psutil.cpu_percent(interval=0.1)
        # Memory Usage
        ram = psutil.virtual_memory()
        ram_pct = ram.percent
        # Disk Usage
        disk = psutil.disk_usage('/')
        disk_pct = disk.percent
        # CPU Temperature
        temp = 0.0
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp = round(float(f.read()) / 1000.0, 1)
        except:
            pass 

        return {"cpu": cpu_pct, "ram": ram_pct, "disk": disk_pct, "temp": temp}
    except Exception as e:
        print(f"Error gathering stats: {e}")
        return {}

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Successfully connected to MQTT Broker!")
        client.subscribe(COMMAND_TOPIC)
        print(f"Subscribed to: {COMMAND_TOPIC}")
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    print(f"Command Received: {msg.payload.decode()}")
    try:
        payload = json.loads(msg.payload.decode())
        action = payload.get("action")

        if action == "reboot":
            print("⚠️ REBOOT COMMAND RECEIVED. Rebooting in 2 seconds...")
            client.publish(STATUS_TOPIC, json.dumps({"status": "rebooting"}))
            time.sleep(2)
            # Execute reboot
            os.system('reboot')
        
        elif action == "ping":
            # Immediate heartbeat response
            stats = get_system_stats()
            client.publish(STATUS_TOPIC, json.dumps({
                "status": "online",
                "response": "pong",
                "timestamp": time.time(),
                "telemetry": stats
            }))

    except Exception as e:
        print(f"Error processing command: {e}")

def main():
    parser = argparse.ArgumentParser(description="Hub System Monitor & Telemetry")
    parser.add_argument("--broker", required=True)
    parser.add_argument("--port", type=int, default=8883)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    
    args = parser.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "hub-system-monitor")
    client.username_pw_set(args.user, args.password)
    client.tls_set()
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to {args.broker}...")
    try:
        client.connect(args.broker, args.port, 60)
        client.loop_start()
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    print("System Monitor Started.")
    
    try:
        while True:
            stats = get_system_stats()
            payload = {
                "status": "online",
                "timestamp": time.time(),
                "telemetry": stats
            }
            # Retain=True ensures the web app sees status immediately on load
            client.publish(STATUS_TOPIC, json.dumps(payload), qos=1, retain=True)
            
            # Send heartbeat every 30 seconds
            time.sleep(30) 
            
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        client.publish(STATUS_TOPIC, json.dumps({"status": "offline"}), retain=True)
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    main()