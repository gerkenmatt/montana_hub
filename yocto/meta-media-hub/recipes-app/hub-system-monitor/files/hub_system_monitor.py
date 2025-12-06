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
UPLINK_INTERFACES = ["wlan1", "wwan0", "eth0", "usb0"]

def get_system_stats():
    """Gathers system health metrics."""
    try:
        cpu_pct = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        temp = 0.0
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                celsius = float(f.read()) / 1000.0
                temp = round((celsius * 9/5) + 32, 1)
        except:
            pass 

        # Calculate Total Bytes
        net_sent_bytes = 0
        net_stats = psutil.net_io_counters(pernic=True)
        for iface in UPLINK_INTERFACES:
            if iface in net_stats:
                net_sent_bytes += net_stats[iface].bytes_sent
        
        net_sent_mb = round(net_sent_bytes / (1024 * 1024), 1)

        return {
            "cpu": cpu_pct, 
            "ram": ram.percent, 
            "disk": disk.percent, 
            "temp": temp,
            "net_sent": net_sent_mb,
            "net_raw": net_sent_bytes # <-- Needed for rate calc
        }
    except Exception as e:
        print(f"Error gathering stats: {e}")
        return {}

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Successfully connected to MQTT Broker!")
        client.subscribe(COMMAND_TOPIC)
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if payload.get("action") == "reboot":
            print("⚠️ REBOOT COMMAND RECEIVED.")
            client.publish(STATUS_TOPIC, json.dumps({"status": "rebooting"}))
            time.sleep(2)
            os.system('reboot')
    except: pass

def main():
    parser = argparse.ArgumentParser()
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

    try:
        client.connect(args.broker, args.port, 60)
        client.loop_start()
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    print("System Monitor Started.")
    
    # Initialize "Previous" state
    stats = get_system_stats()
    last_bytes = stats.get("net_raw", 0)
    last_time = time.time()
    
    try:
        while True:
            # Sleep first (establishes the time delta)
            time.sleep(3)
            
            current_time = time.time()
            stats = get_system_stats()
            current_bytes = stats.get("net_raw", 0)
            
            # --- Calculate Rate ---
            delta_bytes = current_bytes - last_bytes
            delta_time = current_time - last_time
            
            rate_mb_min = 0.0
            if delta_time > 0 and delta_bytes >= 0:
                # (Bytes / Seconds) * 60 = Bytes/Min
                # Bytes/Min / 1024 / 1024 = MB/Min
                rate_mb_min = (delta_bytes / delta_time * 60) / 1048576
            
            # Add rate to payload
            stats["net_rate"] = round(rate_mb_min, 2)
            
            # Update "Previous" state
            last_bytes = current_bytes
            last_time = current_time
            
            # Remove raw bytes to keep JSON clean
            if "net_raw" in stats: del stats["net_raw"]

            payload = {
                "status": "online",
                "timestamp": current_time,
                "telemetry": stats
            }
            client.publish(STATUS_TOPIC, json.dumps(payload), qos=1, retain=True)
            
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(STATUS_TOPIC, json.dumps({"status": "offline"}), retain=True)
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    main()