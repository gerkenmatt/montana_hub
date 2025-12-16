import cv2
import numpy as np
import time
import paho.mqtt.client as mqtt
import json
import sys
import os
import subprocess
import contextlib
import socket
from threading import Thread, Lock
import smtplib, ssl
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import requests 
from hailo_platform import (HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams, InputVStreamParams, OutputVStreamParams, FormatType)

# --- DEBUGGING: Enable GStreamer Logs ---
# Level 3 = FIXME, ERROR, and WARNING logs. 
# This will print exactly WHY the pipeline refuses to link or play.
# os.environ["GST_DEBUG"] = "3"

cv2.setNumThreads(1)

CONFIG_FILE = "/etc/human_detector/config.json"
hailo_lock = Lock()

# --- HAILO WRAPPER ---
class HailoDetector:
    def __init__(self, hef_path, confidence_thresh=0.60, nms_thresh=0.4):
        self.hef = HEF(hef_path)
        self.target = VDevice()
        self.configure_params = ConfigureParams.create_from_hef(hef=self.hef, interface=HailoStreamInterface.PCIe)
        self.network_groups = self.target.configure(self.hef, self.configure_params)
        self.network_group = self.network_groups[0]
        
        self.input_vstream_params = InputVStreamParams.make(self.network_group, format_type=FormatType.UINT8)
        self.output_vstream_params = OutputVStreamParams.make(self.network_group, format_type=FormatType.FLOAT32)
        
        self.input_vstreams_info = self.hef.get_input_vstream_infos()
        self.output_vstreams_info = self.hef.get_output_vstream_infos()
        self.conf_thresh = confidence_thresh
        self.nms_thresh = nms_thresh

    @contextlib.contextmanager
    def inference_context(self):
        with self.network_group.activate():
            with InferVStreams(self.network_group, self.input_vstream_params, self.output_vstream_params) as infer_pipeline:
                yield infer_pipeline

    def preprocess(self, image):
        height, width, _ = self.input_vstreams_info[0].shape
        h, w = image.shape[:2]
        
        # 1. Resize standard opencv way
        scale = min(width / w, height / h)
        nw, nh = int(w * scale), int(h * scale)
        image_resized = cv2.resize(image, (nw, nh))
        
        # 2. ALIGNMENT FIX: Manually allocate 4K-aligned memory
        # This prevents the Hailo driver from failing the VDMA map
        size_bytes = height * width * 3
        alignment = 4096
        
        # Create a raw byte buffer with extra padding
        import mmap
        buffer = bytearray(size_bytes + alignment)
        
        # Calculate the offset to the next 4096-byte boundary
        start_offset = (alignment - (id(buffer) % alignment)) % alignment
        
        # Create a numpy view into that perfectly aligned memory
        input_data = np.frombuffer(buffer, dtype=np.uint8, count=size_bytes, offset=start_offset).reshape((height, width, 3))
        
        # 3. Fill the aligned buffer with the image
        input_data.fill(114) # Gray padding
        dw, dh = (width - nw) // 2, (height - nh) // 2
        input_data[dh:nh+dh, dw:nw+dw, :] = image_resized
        
        # 4. Add batch dimension (H,W,C -> 1,H,W,C)
        input_data = np.expand_dims(input_data, axis=0)
        
        return input_data, scale, dw, dh
        
    def detect(self, image, infer_pipeline):
        input_data, scale, dw, dh = self.preprocess(image)
        input_name = self.input_vstreams_info[0].name
        
        with hailo_lock:
            infer_results = infer_pipeline.infer({input_name: input_data})
        
        def get_numpy_arrays(obj):
            arrays = []
            if isinstance(obj, np.ndarray):
                arrays.append(obj)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    arrays.extend(get_numpy_arrays(item))
            elif isinstance(obj, dict):
                for key in sorted(obj.keys()):
                    arrays.extend(get_numpy_arrays(obj[key]))
            return arrays

        raw_outputs = get_numpy_arrays(infer_results)
        valid_detections = []
        max_conf = 0.0

        for i, t in enumerate(raw_outputs):
            # Class Filtering (Index 0 = Person)
            if i != 0: continue 
            
            if t.size == 0: continue
            
            if t.shape == (1, 5):
                box = t[0]
                score = box[4]
                if score > self.conf_thresh:
                    valid_detections.append(box)
                    max_conf = max(max_conf, score)
            elif len(t.shape) == 2 and t.shape[1] == 5:
                for box in t:
                    score = box[4]
                    if score > self.conf_thresh:
                        valid_detections.append(box)
                        max_conf = max(max_conf, score)

        return valid_detections, max_conf

# --- NOTIFICATION WORKER ---
def send_notification(cam_config, email_config, vps_url, confidence_score):
    try:
        print(f"INFO: [{cam_config['id']}] Alert triggered.")
        clip_path = f"/tmp/{cam_config['id']}_clip.mp4"
        
        # Record Clip
        ffmpeg_cmd = ["ffmpeg", "-y", "-rtsp_transport", "tcp", "-i", cam_config['url'], "-t", "3", "-c:v", "copy", "-an", clip_path]
        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=15)
        
        if not os.path.exists(clip_path): return

        # VPS Upload
        if cam_config.get('upload_enabled', False):
            try:
                with open(clip_path, 'rb') as f:
                    files = {'file': (f"{cam_config['id']}_clip.mp4", f, 'video/mp4')}
                    data = {'camera_id': cam_config['id'], 'confidence': str(confidence_score), 'timestamp': str(time.time())}
                    requests.post(vps_url, files=files, data=data, timeout=10)
            except Exception as e: print(f"ERROR: VPS Upload failed: {e}")

        # Email
        if cam_config.get('email_enabled', False):
            msg = MIMEMultipart()
            msg['From'] = email_config['sender']
            msg['To'] = email_config['recipient']
            msg['Subject'] = f"Alert: {cam_config['id']} ({confidence_score*100:.0f}%)"
            
            with open(clip_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename=clip.mp4")
            msg.attach(part)

            context = ssl.create_default_context()
            with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                server.starttls(context=context)
                server.login(email_config['sender'], email_config['password'])
                server.sendmail(email_config['sender'], email_config['recipient'], msg.as_string())
            print(f"INFO: [{cam_config['id']}] Email sent.")

    except Exception as e:
        print(f"ERROR: Notification failed: {e}")
    finally:
        if os.path.exists(clip_path): os.remove(clip_path)

def wait_for_udp_data(port, timeout=2):
    """
    Blocks until actual video packets are arriving on the UDP port.
    Returns True if data detected, False if timed out.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        # Bind to 127.0.0.1 to match the FFmpeg output
        sock.bind(("127.0.0.1", int(port)))
        # Peek at the socket (recv one packet)
        _ = sock.recv(1024)
        sock.close()
        return True
    except socket.timeout:
        return False
    except Exception:
        # Port likely busy or permission denied
        return False
    finally:
        try: sock.close()
        except: pass

# --- CAMERA THREAD WORKER ---
def camera_worker(detector, infer_pipeline, client, cam_config, full_config):
    cam_id = cam_config['id']
    url = cam_config['url']
    print(f"INFO: [{cam_id}] Manager thread active.")

    while True:
        try:
            # --- STEP 1: Wait for Stream Data ---
            if "udp://" in url:
                port = url.split(":")[-1]
                print(f"INFO: [{cam_id}] Waiting for video data on port {port}...")
                while not wait_for_udp_data(port):
                    time.sleep(1) 
                print(f"INFO: [{cam_id}] Video data detected! Starting AI Pipeline...")
                
                # Buffer size 5MB to catch I-frames
                pipe = (f"udpsrc port={port} buffer-size=5242880 ! "
                        "tsdemux ! "
                        "h264parse config-interval=1 ! "
                        "avdec_h264 ! "
                        "videoconvert ! "
                        "video/x-raw,format=BGR ! "
                        "appsink sync=false drop=true max-buffers=1")
                cap = cv2.VideoCapture(pipe, cv2.CAP_GSTREAMER)
            else:
                cap = cv2.VideoCapture(url)

            if not cap.isOpened():
                print(f"WARNING: [{cam_id}] Failed to bind GStreamer. Retrying...")
                time.sleep(1)
                raise Exception("Bind failed")

            print(f"INFO: [{cam_id}] Stream Open. Flushing startup buffer...")
            for i in range(30):
                cap.read()
            
            ret, frame = cap.read()
            if not ret:
                 raise Exception("Stream failed during flush")

            print(f"INFO: [{cam_id}] Stream Stable. Starting Inference Loop.")
            
            frame_idx = 0
            is_detected = False
            cons_detects = 0
            cons_misses = 0
            last_notify = 0
            topic = f"cabin/camera/{cam_id}/detection"

            while True:
                # --- DEBUG POINT 1: Is GStreamer Stuck? ---
                if frame_idx < 20: print(f"DEBUG: [{cam_id}] Reading frame {frame_idx}...")
                
                ret, frame = cap.read()
                
                if not ret:
                    raise Exception("Stream read failed")
                if frame_idx < 20: print(f"DEBUG: [{cam_id}] Frame read success. Shape: {frame.shape}")

                frame_idx += 1
                if frame_idx % 3: continue 

                # --- DEBUG POINT 2: Is Hailo Stuck? ---
                if frame_idx < 20: print(f"DEBUG: [{cam_id}] Running Inference...")
                
                detections, conf = detector.detect(frame, infer_pipeline)
                
                if frame_idx < 20: print(f"DEBUG: [{cam_id}] Inference done. Detections: {len(detections)}")

                if len(detections) > 0:
                    cons_detects += 1
                    cons_misses = 0
                else:
                    cons_misses += 1
                    cons_detects = 0

                if not is_detected and cons_detects >= 3:
                    is_detected = True
                    print(f"INFO: [{cam_id}] HUMAN DETECTED ({conf*100:.0f}%).")
                    payload = json.dumps({"event": "person_detected", "camera_id": cam_id, "confidence": float(conf), "timestamp": time.time()})
                    client.publish(topic, payload, qos=1)
                    
                    if (time.time() - last_notify) > 30:
                        last_notify = time.time()
                        Thread(target=send_notification, args=(cam_config, full_config['email_config'], full_config.get('vps_url', ''), conf)).start()

                elif is_detected and cons_misses >= 5:
                    is_detected = False
                    print(f"INFO: [{cam_id}] CLEAR.")
                    payload = json.dumps({"event": "clear", "timestamp": time.time()})
                    client.publish(topic, payload, qos=1)

        except Exception as e:
            print(f"WARNING: [{cam_id}] Stream Lost: {e}. Re-scanning...")
            if 'cap' in locals() and cap: cap.release()
            time.sleep(2)

def main():
    if not os.path.exists(CONFIG_FILE):
        print(f"ERROR: Config file not found at {CONFIG_FILE}")
        sys.exit(1)

    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "human-detector-manager")
    client.username_pw_set(config['mqtt']['user'], config['mqtt']['password'])
    client.tls_set()
    try:
        client.connect(config['mqtt']['broker'], config['mqtt']['port'])
        client.loop_start()
    except Exception as e:
        print(f"ERROR: MQTT Init failed: {e}")
        sys.exit(1)

    print("INFO: Initializing Hailo...")
    detector = HailoDetector(config['model']['path'], config['model']['confidence'], config['model']['nms'])
    
    try:
        with detector.inference_context() as infer_pipeline:
            print("INFO: Hailo Active. Spawning threads...")
            threads = []
            
            for cam in config['cameras']:
                # --- TROUBLESHOOTING ISOLATION ---
                # Only allow camera 2 to start. Ignore everything else.
                if cam['id'] != "camera2":
                    print(f"INFO: Skipping {cam['id']} for troubleshooting.")
                    continue

                t = Thread(target=camera_worker, args=(detector, infer_pipeline, client, cam, config))
                t.daemon = True
                t.start()
                threads.append(t)
                time.sleep(2.0) 
            
            while True: time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nINFO: Exiting.")

if __name__ == "__main__":
    main()