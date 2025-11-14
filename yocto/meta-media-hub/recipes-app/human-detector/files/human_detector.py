# meta-media-hub/recipes-app/human-detector/files/human_detector.py

import cv2
import numpy as np
import argparse
import time
import paho.mqtt.client as mqtt
import json
import sys

cv2.setNumThreads(1)

# --- Configuration ---
DEFAULT_MODEL_PATH = "/usr/share/human-detector/"
DEFAULT_CONF_THRESHOLD = 0.5
DEFAULT_NMS_THRESHOLD = 0.4

# --- MQTT Client Setup ---
def connect_mqtt(broker, port, user, password, camera_id):
    """Connects to the MQTT broker."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, f"human-detector-{camera_id}")
    client.username_pw_set(user, password)
    client.tls_set()
    
    try:
        client.connect(broker, port, 60)
        print(f"INFO: Successfully connected to MQTT broker at {broker}")
        client.loop_start()
        return client
    except Exception as e:
        print(f"ERROR: Could not connect to MQTT broker: {e}")
        return None

def main(stream_url, model_path, confidence, nms, mqtt_client, camera_id):
    """
    Connects to a video stream, detects humans, and publishes MQTT alerts.
    """
    # --- Load YOLO Model ---
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
        parts = stream_url.replace("tcp://", "").split(":")
        host = parts[0]
        port = int(parts[1])
        pipeline = (
            f"tcpclientsrc host={host} port={port} ! "
            "tsdemux ! h264parse ! avdec_h264 ! videoconvert ! "
            "video/x-raw,format=BGR ! queue max-size-buffers=1 leaky=downstream ! "
            "appsink sync=false max-buffers=1 drop=true"
        )
        print(f"INFO: Using GStreamer pipeline: {pipeline}")
    except Exception as e:
        print(f"ERROR: Invalid stream URL. {e}", file=sys.stderr)
        return

    # --- Connect to Stream ---
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        print(f"ERROR: Cannot open GStreamer pipeline.", file=sys.stderr)
        return

    print(f"INFO: Successfully connected to stream. Starting detection loop...")

    # --- Detection Loop ---
    frame_idx = 0
    last_detection_state = None 
    detection_topic = f"cabin/camera/{camera_id}/detection" 

    while True:
        try:
            ret, frame = cap.read()
            if not ret:
                print("WARNING: Pipeline source ended. Reconnecting...", file=sys.stderr)
                time.sleep(5)
                cap.release()
                cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                continue

            # Only run detection every 5th frame to save CPU
            frame_idx += 1
            if frame_idx % 5:
                continue

            current_detection_state = False 
            max_confidence = 0.0  # <-- **NEW**: Track highest confidence score
            
            blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (320, 320), swapRB=True, crop=False)
            net.setInput(blob)
            layer_outputs = net.forward(output_layers)

            for output in layer_outputs:
                for detection in output:
                    scores = detection[5:]
                    class_id = np.argmax(scores)
                    conf = scores[class_id]
                    if classes[class_id] == "person" and conf > confidence:
                        current_detection_state = True # Human detected
                        if conf > max_confidence:  # <-- **NEW**: Store highest score
                            max_confidence = conf

            # --- MQTT Publish Logic ---
            if current_detection_state != last_detection_state:
                last_detection_state = current_detection_state
                
                if current_detection_state:
                    print(f"INFO: State Change: HUMAN DETECTED ({max_confidence*100:.0f}%). Publishing to {detection_topic}")
                    # <-- **MODIFIED**: Add confidence to payload
                    payload = json.dumps({
                        "event": "person_detected",
                        "camera_id": camera_id,
                        "confidence": float(max_confidence), 
                        "timestamp": time.time()
                    })
                else:
                    print(f"INFO: State Change: CLEAR. Publishing to {detection_topic}")
                    payload = json.dumps({"event": "clear", "timestamp": time.time()})
                
                if mqtt_client:
                    mqtt_client.publish(detection_topic, payload, qos=1, retain=True)

        except KeyboardInterrupt:
            print("\nINFO: Exiting.")
            break
        except Exception as e:
            print(f"ERROR: An error occurred in the loop: {e}", file=sys.stderr)
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
    
    # --- NEW: MQTT args ---
    # These are passed in by the .service file
    parser.add_argument("--broker", required=True, help="MQTT broker address")
    parser.add_argument("--port", type=int, default=8883, help="MQTT broker port")
    parser.add_argument("--user", required=True, help="MQTT username")
    parser.add_argument("--password", required=True, help="MQTT password")
    parser.add_argument("--camera-id", required=True, help="Unique ID for this camera (e.g., camera1)")
    
    args = parser.parse_args()

    # (MQTT connection)
    client = connect_mqtt(args.broker, args.port, args.user, args.password, args.camera_id)
    if not client:
        print("ERROR: Failed to connect to MQTT. Exiting.", file=sys.stderr)
        sys.exit(1)
        
    main(args.stream, args.model_path, args.confidence, args.nms, client, args.camera_id)