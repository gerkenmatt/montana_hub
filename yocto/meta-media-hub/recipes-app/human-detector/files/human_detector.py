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
from hailo_platform import (HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams, InputVStreamParams, OutputVStreamParams, FormatType)

cv2.setNumThreads(1)

# --- Configuration ---
DEFAULT_MODEL_PATH = "/usr/share/human-detector/yolov8s.hef"
DEFAULT_CONF_THRESHOLD = 0.5
DEFAULT_NMS_THRESHOLD = 0.4
NOTIFICATION_COOLDOWN = 30 # Seconds
MQTT_SETTINGS_TOPIC = "cabin/hub/settings"
VPS_UPLOAD_URL = "http://10.0.0.1:8080/api/upload"

g_notifications_enabled = False     # Default Email OFF
g_upload_enabled = False            # Default Upload OFF 


# --- HAILO DETECTOR CLASS ---
class HailoDetector:
    def __init__(self, hef_path, confidence_thresh=0.5, nms_thresh=0.4):
        self.hef = HEF(hef_path)
        self.target = VDevice()
        
        self.configure_params = ConfigureParams.create_from_hef(hef=self.hef, interface=HailoStreamInterface.PCIe)
        self.network_groups = self.target.configure(self.hef, self.configure_params)
        self.network_group = self.network_groups[0]
        
        self.input_vstream_params = self.network_group.make_input_vstream_params({}, format_type=FormatType.FLOAT32)
        self.output_vstream_params = self.network_group.make_output_vstream_params({}, format_type=FormatType.FLOAT32)
        
        self.input_vstreams_info = self.hef.get_input_vstream_infos()
        self.output_vstreams_info = self.hef.get_output_vstream_infos()
        
        self.conf_thresh = confidence_thresh
        self.nms_thresh = nms_thresh

    def preprocess(self, image):
        # Hailo models expect strict input sizes (usually 640x640 for YOLOv8)
        height, width, _ = self.input_vstreams_info[0].shape
        
        # Resize and pad to maintain aspect ratio
        h, w = image.shape[:2]
        scale = min(width / w, height / h)
        nw, nh = int(w * scale), int(h * scale)
        image_resized = cv2.resize(image, (nw, nh))
        
        # Create canvas
        image_padded = np.full((height, width, 3), 114, dtype=np.uint8)
        dw, dh = (width - nw) // 2, (height - nh) // 2
        image_padded[dh:nh+dh, dw:nw+dw, :] = image_resized
        
        # Convert BGR (OpenCV) to RGB (Hailo) and normalize if required
        input_data = cv2.cvtColor(image_padded, cv2.COLOR_BGR2RGB)
        input_data = np.expand_dims(input_data, axis=0).astype(np.float32)
        return input_data, scale, dw, dh

    def detect(self, image):
        input_data, scale, dw, dh = self.preprocess(image)
        
        # Run Inference
        with InferVStreams(self.network_group, self.input_vstream_params, self.output_vstream_params) as infer_pipeline:
            input_name = self.input_vstreams_info[0].name
            infer_results = infer_pipeline.infer({input_name: input_data})
            
            # YOLOv8s typically has one output tensor
            output_tensor = list(infer_results.values())[0] # Shape usually [1, 84, 8400]
            
        return self.postprocess_yolov8(output_tensor, scale, dw, dh)

    def postprocess_yolov8(self, output, scale, dw, dh):
        # Transpose output: [1, 84, 8400] -> [8400, 84]
        predictions = np.squeeze(output).T
        
        scores = np.max(predictions[:, 4:], axis=1)
        predictions = predictions[scores > self.conf_thresh, :]
        scores = scores[scores > self.conf_thresh]
        
        if len(scores) == 0:
            return [], 0.0

        class_ids = np.argmax(predictions[:, 4:], axis=1)
        
        # Filter for 'Person' class (Class ID 0 in COCO)
        person_indices = class_ids == 0
        predictions = predictions[person_indices]
        scores = scores[person_indices]
        
        if len(scores) == 0:
            return [], 0.0

        # Extract boxes
        boxes = predictions[:, :4]
        input_h, input_w, _ = self.input_vstreams_info[0].shape
        
        # Scale boxes back to original image
        boxes[:, 0] = (boxes[:, 0] - dw) / scale # x
        boxes[:, 1] = (boxes[:, 1] - dh) / scale # y
        boxes[:, 2] = (boxes[:, 2]) / scale      # w
        boxes[:, 3] = (boxes[:, 3]) / scale      # h
        
        # Convert cx,cy,w,h to x,y,w,h (Top-Left)
        boxes[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        boxes[:, 1] = boxes[:, 1] - boxes[:, 3] / 2

        # NMS
        indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), self.conf_thresh, self.nms_thresh)
        
        max_conf = 0.0
        detections = []
        for i in indices:
            max_conf = max(max_conf, scores[i])
            detections.append(True)
            
        return detections, max_conf

def on_settings_message(client, userdata, msg):
    """Called when a new message is received on the settings topic."""
    global g_notifications_enabled, g_upload_enabled
    try:
        payload = json.loads(msg.payload.decode())
        print(f"INFO: [Settings Received] {payload}")

        # Only update if the key exists in the payload
        if "notifications" in payload:
            status = payload["notifications"].lower()
            g_notifications_enabled = (status == "on")
            print(f"   > Email Notifications set to: {g_notifications_enabled}")
            
        if "upload" in payload:
            status = payload["upload"].lower()
            g_upload_enabled = (status == "on")
            print(f"   > Cloud Upload set to: {g_upload_enabled}")

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

        # --- 2. Upload to VPS ---
        if g_upload_enabled:
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
        else: 
            print("INFO: [Notify Thread] VPS Upload skipped (Switch is OFF).")

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
        print(f"INFO: Loading Hailo Model: {args.model_path}")
        detector = HailoDetector(args.model_path, args.confidence, args.nms)
        print("INFO: Hailo VDevice Initialized successfully.")
    except Exception as e:
        print(f"ERROR: Failed to initialize Hailo: {e}")
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
    last_detection_state = False
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
            if frame_idx % 3: continue

            current_detection_state = False 
            max_confidence = 0.0
            
            detections, max_confidence = detector.detect(frame)
            current_detection_state = len(detections) > 0
            
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