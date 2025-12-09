#!/usr/bin/env python3
import sys
import os
import time
import signal
import subprocess
import paho.mqtt.client as mqtt
import requests
import threading

# --- CONFIGURATION ---
CONFIG_FILE = "/etc/montana-hub/camera_config.env"
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# Global handles
ffmpeg_process = None
current_instance = ""
current_fps_state = "OFF"  # Track what we *want* the state to be

def load_config(instance_name):
    try:
        with open(CONFIG_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{instance_name}="):
                    parts = line.split('=', 1)[1].split('|')
                    if len(parts) >= 3:
                        return {
                            'ip': parts[0].strip(),
                            'path': parts[1].strip(),
                            'output': parts[2].strip(),
                            'default_mode': parts[3].strip() if len(parts) > 3 else "OFF"
                        }
    except Exception as e:
        print(f"Error reading config: {e}")
    return None

def take_snapshot(config):
    # Parse ID: "cam2-sd-remote" -> "cam2"
    # We want the snapshot to update the CARD, regardless of SD/HD
    cam_id_short = current_instance.split("-")[0] 
    
    print(f"[{current_instance}] Taking Snapshot for {cam_id_short}...")
    
    # 1. Define paths
    rtsp_url = f"rtsp://{config['ip']}:8554{config['path']}"
    temp_img = f"/tmp/{current_instance}.jpg"
    
    # WARNING: Use the VPN IP of the VPS here
    upload_url = "http://10.0.0.3:8000/api/upload/snapshot" 

    # 2. Run FFmpeg to grab ONE frame
    # -ss 00:00:01 skips the first second to avoid "green/grey" garbage frames
    cmd = [
        "/usr/bin/ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-ss", "00:00:01.500", 
        "-vframes", "1",
        "-q:v", "2", 
        temp_img
    ]
    
    try:
        subprocess.run(cmd, timeout=10, check=True)
        
        # 3. Upload to VPS
        if os.path.exists(temp_img):
            with open(temp_img, 'rb') as f:
                # We send 'cam1' or 'cam2' so the web app knows which card to update
                r = requests.post(upload_url, files={'file': f}, data={'camera_id': cam_id_short}, timeout=5)
            os.remove(temp_img) # Delete from Pi immediately
            
    except Exception as e:
        print(f"[{current_instance}] Snapshot Failed: {e}")

def stop_ffmpeg():
    global ffmpeg_process
    if ffmpeg_process:
        # Only print if we are killing an active process
        if ffmpeg_process.poll() is None: 
            print(f"[{current_instance}] Stopping FFmpeg...")
            ffmpeg_process.send_signal(signal.SIGTERM)
            try:
                ffmpeg_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ffmpeg_process.kill()
        
        ffmpeg_process = None

def start_ffmpeg(config, fps_mode):
    global ffmpeg_process, current_fps_state
    
    # Check if we are already running this mode efficiently
    if fps_mode == current_fps_state and ffmpeg_process is not None:
        if ffmpeg_process.poll() is None:
            return  # Already running happily

    stop_ffmpeg()
    time.sleep(2)   # give the RTSP server a moment to close the old socket
    current_fps_state = fps_mode

    if fps_mode == "OFF":
        print(f"[{current_instance}] State set to OFF.")
        return

    input_url = f"rtsp://{config['ip']}:8554{config['path']}"
    print(f"[{current_instance}] Starting Stream @ {fps_mode} FPS")

    cmd = [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",      # Cleaner logs
        "-nostdin",
        
        # --- INPUT STABILITY FLAGS ---
        "-err_detect", "ignore_err", # Drop bad frames silently, don't spam logs
        "-rtsp_transport", "tcp",
        "-stimeout", "2000000",
        "-rtsp_flags", "prefer_tcp",
        "-allowed_media_types", "video", # Only look for video!
        "-analyzeduration", "10M",
        "-probesize", "10M",
        "-fflags", "+genpts+igndts+discardcorrupt",
        # "-reorder_queue_size", "0",
        
        # Input Source
        "-i", input_url,
        
        # --- VIDEO PROCESSING ---
        "-map", "0:v:0",             # Map video stream 0
        "-an",                       # Disable Audio 
        "-vf", f"fps={fps_mode}",    # The Variable FPS logic
        "-c:v", "libx264",           # Must re-encode to change FPS
        "-preset", "ultrafast",      # Save CPU
        "-tune", "zerolatency",      # Low delay
        "-pix_fmt", "yuv420p",       # Ensure compatibility with web players
        "-g", "60",                  # Force a Keyframe every 60 frames (recovery)
        
        # --- OUTPUT FORMATTING ---
        "-bsf:v", "h264_mp4toannexb", # Helps with streaming compatibility
        "-f", "flv" if "rtmp" in config['output'] else "mpegts",
    ]

    if "udp://" in config['output']:
        cmd.extend([
            "-mpegts_flags", "+resend_headers",
            "-flush_packets", "1",
            "-muxpreload", "0",
            "-muxdelay", "0",
            config['output']
        ])
    else:
        # Just the output URL for RTMP/TCP
        cmd.append(config['output'])

    # Launch without blocking
    ffmpeg_process = subprocess.Popen(cmd)

def parse_fps_payload(payload):
    payload = payload.upper()
    if payload == "LOW": return 0.1
    elif payload == "MEDIUM": return 1
    elif payload == "HIGH": return 20
    elif payload == "OFF": return "OFF"
    else: 
        try: return float(payload)
        except: return "OFF"

def on_message(client, userdata, msg):
    gloabel current_fps_state
    payload = msg.payload.decode()
    
    if payload == "SNAPSHOT":
        print(f"[{current_instance}] Received MQTT: SNAPSHOT. Killing Live Stream.")

        # 1. KILL the data hog (The Live Stream)
        stop_ffmpeg()
        
        # 2. Tell Watchdog to stay asleep
        current_fps_state = "OFF"

        # 3. Wait a moment for the Camera's RTSP socket to free up
        # (Wyze cameras struggle with 2 simultaneous connections)
        time.sleep(1)

        # Run in thread so we can click fast without blocking
        threading.Thread(target=take_snapshot, args=(userdata['config'],)).start()
    else:
        print(f"[{current_instance}] Received MQTT: {payload}")
        fps = parse_fps_payload(payload)
        start_ffmpeg(userdata['config'], fps)

def main():
    global current_instance, current_fps_state
    if len(sys.argv) < 2:
        print("Usage: camera_manager.py <INSTANCE_NAME>")
        sys.exit(1)

    current_instance = sys.argv[1]
    config = load_config(current_instance)
    
    if not config:
        print(f"Error: Configuration for {current_instance} not found.")
        sys.exit(1)

    # 1. Set Initial State
    initial_fps = parse_fps_payload(config['default_mode'])
    print(f"[{current_instance}] Booting with Default Mode: {config['default_mode']}")
    start_ffmpeg(config, initial_fps)

    # 2. MQTT Setup (Running in Background Thread)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata={'config': config})
    client.on_message = on_message
    
    topic = f"cabin/cameras/{current_instance}/control"
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.subscribe(topic)
        client.loop_start() 
    except Exception as e:
        print(f"MQTT Connection Failed: {e}")

    # 3. Watchdog Loop (The Main Thread)
    print(f"[{current_instance}] Service Started. Monitoring process...")
    stream_is_stable = False
    try:
        while True:
            time.sleep(5) # Check every 5 seconds
            
            # If we WANT to be streaming...
            if current_fps_state != "OFF":
                # ...but the process is dead
                if ffmpeg_process is None or ffmpeg_process.poll() is not None:
                    stream_is_stable = False # Reset flag
                    print(f"[{current_instance}] Stream died (Network issue?). Restarting...")
                    start_ffmpeg(config, current_fps_state)
                
                # ...and the process IS running
                elif not stream_is_stable:
                    # It's running, and we haven't announced it yet
                    print(f"[{current_instance}] SUCCESS: Connection Established. Stream is Stable.")
                    stream_is_stable = True

    except KeyboardInterrupt:
        stop_ffmpeg()
        client.loop_stop()

if __name__ == "__main__":
    main()