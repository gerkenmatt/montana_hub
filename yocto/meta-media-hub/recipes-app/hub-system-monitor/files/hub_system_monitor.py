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

# Define which interfaces count as "Internet Data"
# wlan1 = Home Wi-Fi (Current testing)
# wwan0 = Cellular Data (Future Waveshare HAT)
# eth0  = Ethernet (If plugged in)
UPLINK_INTERFACES = ["wlan1", "wwan0", "eth0", "usb0"]

def get_system_stats():
    """Gathers system health metrics."""
    try:
        # CPU Load
        # interval=None compares cpu times since the last call.
        # This effectively gives us the average usage over the last 3 seconds.
        cpu_pct = psutil.cpu_percent(interval=None)
        
        # Memory Usage
        ram = psutil.virtual_memory()
        ram_pct = ram.percent
        
        # Disk Usage (Root partition)
        disk = psutil.disk_usage('/')
        disk_pct = disk.percent
        
        # CPU Temperature (Raspberry Pi specific)
        temp = 0.0
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                celsius = float(f.read()) / 1000.0
                # Convert to Fahrenheit
                temp = round((celsius * 9/5) + 32, 1)
        except:
            pass 

        # --- Network Usage ---
        # Only count bytes sent over the Internet Uplink interfaces.
        # This ignores:
        #   - lo (Internal loopback traffic)
        #   - wlan0 (Local camera traffic - FREE)
        #   - wg0 (VPN traffic - counting this AND wlan1 would double-count)
        net_sent_bytes = 0
        net_stats = psutil.net_io_counters(pernic=True)
        
        for iface in UPLINK_INTERFACES:
            if iface in net_stats:
                net_sent_bytes += net_stats[iface].bytes_sent
        
        # Convert to Megabytes (MB)
        net_sent_mb = round(net_sent_bytes / (1024 * 1024), 1)

        return {
            "cpu": cpu_pct, 
            "ram": ram_pct, 
            "disk": disk_pct, 
            "temp": temp,
            "net_sent": net_sent_mb
        }
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
            os.system('reboot')
        
        elif action == "ping":
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
    
    # Call once at startup to initialize psutil's internal timers
    # The first call to cpu_percent(None) always returns 0.0
    get_system_stats()
    
    try:
        while True:
            stats = get_system_stats()
            payload = {
                "status": "online",
                "timestamp": time.time(),
                "telemetry": stats
            }
            client.publish(STATUS_TOPIC, json.dumps(payload), qos=1, retain=True)
            
            # Update every 3 seconds
            time.sleep(3) 
            
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        client.publish(STATUS_TOPIC, json.dumps({"status": "offline"}), retain=True)
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    main()