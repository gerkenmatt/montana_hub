# meta-media-hub/recipes-app/human-detector/files/human_detector.py

import cv2
import numpy as np
import argparse
import time
import paho.mqtt.client as mqtt
import json
import sys
import os
import subprocess
from threading import Thread
import smtplib, ssl
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import requests 

cv2.setNumThreads(1)

# --- Configuration ---
DEFAULT_MODEL_PATH = "/usr/share/human-detector/"
DEFAULT_CONF_THRESHOLD = 0.5
DEFAULT_NMS_THRESHOLD = 0.4
NOTIFICATION_COOLDOWN = 30 # Seconds
MQTT_SETTINGS_TOPIC = "cabin/hub/settings"

# VPS Storage Endpoint (Use the VPN IP of my VPS)
VPS_UPLOAD_URL = "http://10.0.0.1:8080/api/upload"

g_notifications_enabled = False 

def on_settings_message(client, userdata, msg):
    """Called when a new message is received on the settings topic."""
    global g_notifications_enabled
    try:
        payload = json.loads(msg.payload.decode())
        status = payload.get("notifications", "off").lower()
        g_notifications_enabled = (status == "on")
        print(f"INFO: [Settings Update] Email notifications set to: {g_notifications_enabled}")
    except Exception as e:
        print(f"ERROR: Could not parse settings message: {e}", file=sys.stderr)

def send_notification_thread(args, confidence_score):
    """
    Records clip, Uploads to VPS, and Emails it.
    """
    print("INFO: [Notify Thread] Starting process...")
    try:
        camera_id = args.camera_id
        clip_path = f"/tmp/{camera_id}_clip.mp4"

        # --- 1. Record 3-second clip ---
        print(f"INFO: [Notify Thread] Recording 3s clip from {args.rtsp_url}...")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-rtsp_transport", "tcp",
            "-i", args.rtsp_url,
            "-t", "3", "-c:v", "copy", "-an",
            clip_path
        ]
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=15)
        
        if not os.path.exists(clip_path):
            print(f"ERROR: [Notify Thread] Failed to create clip. FFmpeg output:\n{result.stderr}", file=sys.stderr)
            return

        print(f"INFO: [Notify Thread] Clip saved to {clip_path}")

        # --- 2. Upload to VPS (Cloud NVR) ---
        # This happens EVERY time a person is detected, ensuring history is saved.
        print(f"INFO: [Notify Thread] Uploading to {VPS_UPLOAD_URL}...")
        try:
            with open(clip_path, 'rb') as f:
                files = {'file': (f'{camera_id}_clip.mp4', f, 'video/mp4')}
                data = {
                    'camera_id': camera_id,
                    'confidence': str(confidence_score),
                    'timestamp': str(time.time())
                }
                # 10 second timeout so we don't hang if VPS is down
                r = requests.post(VPS_UPLOAD_URL, files=files, data=data, timeout=10)
                
                if r.status_code == 200:
                    print(f"INFO: [Notify Thread] VPS Upload Successful.")
                else:
                    print(f"ERROR: [Notify Thread] VPS Upload failed: {r.status_code} - {r.text}")
        except Exception as e:
            print(f"ERROR: [Notify Thread] Could not upload to VPS (Server might be down): {e}")

        # --- 3. Send Email (Only if enabled) ---
        if g_notifications_enabled:
            print("INFO: [Notify Thread] Email is ON. Sending...")
            
            msg = MIMEMultipart()
            msg['From'] = args.email_user
            msg['To'] = args.email_to
            confidence_percent = confidence_score * 100
            msg['Subject'] = f"Security Alert: Person Detected on {camera_id} ({confidence_percent:.0f}%)"
            
            with open(clip_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename=detection_clip.mp4")
            msg.attach(part)

            print("INFO: [Notify Thread] Connecting to SMTP server...")
            context = ssl.create_default_context()
            with smtplib.SMTP(args.email_smtp_server, args.email_smtp_port) as server:
                server.starttls(context=context)
                server.login(args.email_user, args.email_pass)
                server.sendmail(args.email_user, args.email_to, msg.as_string())
                print("INFO: [Notify Thread] Email notification sent successfully.")
        else:
             print("INFO: [Notify Thread] Email skipped (Switch is OFF).")

    except Exception as e:
        print(f"ERROR: [Notify Thread] General Exception: {e}", file=sys.stderr)
    
    finally:
        # --- 4. Clean up the clip ---
        if os.path.exists(clip_path):
            os.remove(clip_path)

def connect_mqtt(broker, port, user, password, camera_id):
    """Connects to the MQTT broker."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, f"human-detector-{camera_id}")
    client.username_pw_set(user, password)
    client.tls_set()
    client.on_message = on_settings_message # Register callback
    try:
        client.connect(broker, port, 60)
        client.subscribe(MQTT_SETTINGS_TOPIC) # Subscribe to settings
        print(f"INFO: Subscribed to settings topic: {MQTT_SETTINGS_TOPIC}")
        print(f"INFO: Successfully connected to MQTT broker at {broker}")
        client.loop_start()
        return client
    except Exception as e:
        print(f"ERROR: Could not connect to MQTT broker: {e}")
        return None

def main(args, mqtt_client):
    stream_url = args.stream
    model_path = args.model_path
    confidence = args.confidence
    nms = args.nms
    camera_id = args.camera_id

    try:
        weights_path = f"{model_path}/yolov4-tiny.weights"
        cfg_path = f"{model_path}/yolov4-tiny.cfg"
        names_path = f"{model_path}/coco.names"
        net = cv2.dnn.readNet(weights_path, cfg_path)
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        with open(names_path, "r") as f:
            classes = [line.strip() for line in f.readlines()]
        layer_names = net.getLayerNames()
        output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]
        print(f"INFO: Model loaded successfully. Looking for 'person' class.")
    except Exception as e:
        print(f"ERROR: Could not load model. Check paths. Error: {e}", file=sys.stderr)
        return

    # --- Build GStreamer Pipeline ---
    try:
        if "udp://" in stream_url:
            # --- UDP Pipeline ---
            port = stream_url.split(":")[-1]
            pipeline = (
                f"udpsrc port={port} ! "
                "tsdemux ! h264parse ! avdec_h264 ! videoconvert ! "
                "video/x-raw,format=BGR ! queue max-size-buffers=1 leaky=downstream ! "
                "appsink sync=false max-buffers=1 drop=true"
            )
            print(f"INFO: Using UDP GStreamer pipeline: port={port}")
        else:
            # --- TCP Pipeline (Legacy support) ---
            parts = stream_url.replace("tcp://", "").split(":")
            host = parts[0]
            port = int(parts[1])
            pipeline = (
                f"tcpclientsrc host={host} port={port} ! "
                "tsdemux ! h264parse ! avdec_h264 ! videoconvert ! "
                "video/x-raw,format=BGR ! queue max-size-buffers=1 leaky=downstream ! "
                "appsink sync=false max-buffers=1 drop=true"
            )
            print(f"INFO: Using TCP GStreamer pipeline: {pipeline}")
            
    except Exception as e:
        print(f"ERROR: Invalid stream URL. {e}", file=sys.stderr)
        return

    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        print(f"ERROR: Cannot open GStreamer pipeline.", file=sys.stderr)
        return

    print(f"INFO: Successfully connected to stream. Starting detection loop...")

    frame_idx = 0
    last_detection_state = None 
    detection_topic = f"cabin/camera/{camera_id}/detection" 
    last_notification_time = 0

    while True:
        try:
            ret, frame = cap.read()
            if not ret:
                print("WARNING: Stream lost. Reconnecting...", file=sys.stderr)
                time.sleep(5)
                cap.release()
                cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                continue

            frame_idx += 1
            if frame_idx % 5: continue

            current_detection_state = False 
            max_confidence = 0.0
            
            blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (320, 320), swapRB=True, crop=False)
            net.setInput(blob)
            layer_outputs = net.forward(output_layers)

            for output in layer_outputs:
                for detection in output:
                    scores = detection[5:]
                    class_id = np.argmax(scores)
                    conf = scores[class_id]
                    if classes[class_id] == "person" and conf > confidence:
                        current_detection_state = True
                        if conf > max_confidence: max_confidence = conf
            
            current_time = time.time()

            # --- MQTT Publish Logic ---
            if current_detection_state != last_detection_state:
                last_detection_state = current_detection_state
                if current_detection_state:
                    print(f"INFO: State Change: HUMAN DETECTED ({max_confidence*100:.0f}%). Publishing to {detection_topic}")
                    payload = json.dumps({"event": "person_detected", "camera_id": camera_id, "confidence": float(max_confidence), "timestamp": current_time})
                else:
                    print(f"INFO: State Change: CLEAR. Publishing to {detection_topic}")
                    payload = json.dumps({"event": "clear", "timestamp": current_time})
                
                if mqtt_client:
                    mqtt_client.publish(detection_topic, payload, qos=1, retain=True)

            # --- Trigger Notification Thread ---
            if current_detection_state:
                if (current_time - last_notification_time) > NOTIFICATION_COOLDOWN:
                    print(f"INFO: Cooldown expired. Triggering notification thread...")
                    last_notification_time = current_time 
                    # Call the new combined function
                    thread = Thread(target=send_notification_thread, args=(args, max_confidence))
                    thread.start()

        except KeyboardInterrupt:
            print("\nINFO: Exiting.")
            break
        except Exception as e:
            print(f"ERROR: Loop exception: {e}", file=sys.stderr)
            time.sleep(5)

    if mqtt_client:
        mqtt_client.loop_stop()
    cap.release()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect humans and publish MQTT alerts.")
    # (Arguments are the same as before)
    parser.add_argument("--stream", type=str, required=True, help="URL of the TCP or RTSP stream.")
    parser.add_argument("--model-path", type=str, default=DEFAULT_MODEL_PATH, help="Path to the directory containing model files.")
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONF_THRESHOLD, help="Minimum detection confidence.")
    parser.add_argument("--nms", type=float, default=DEFAULT_NMS_THRESHOLD, help="Non-Maximum Suppression threshold.")
    parser.add_argument("--broker", required=True, help="MQTT broker address")
    parser.add_argument("--port", type=int, default=8883, help="MQTT broker port")
    parser.add_argument("--user", required=True, help="MQTT username")
    parser.add_argument("--password", required=True, help="MQTT password")
    parser.add_argument("--camera-id", required=True, help="Unique ID for this camera (e.g., camera1)")
    parser.add_argument("--rtsp-url", type=str, required=True, help="RTSP URL (for video clip)")
    parser.add_argument("--email-user", required=True, help="Sender email address")
    parser.add_argument("--email-pass", required=True, help="Sender email password")
    parser.add_argument("--email-to", required=True, help="Recipient email address")
    parser.add_argument("--email-smtp-server", required=True, help="SMTP server")
    parser.add_argument("--email-smtp-port", type=int, required=True, help="SMTP port")
    
    args = parser.parse_args()

    client = connect_mqtt(args.broker, args.port, args.user, args.password, args.camera_id)
    if not client:
        print("ERROR: Failed to connect to MQTT. Exiting.", file=sys.stderr)
        sys.exit(1)

    main(args, client)