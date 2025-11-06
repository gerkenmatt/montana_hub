#!/usr/bin/env python3

# human_detector.py
import cv2
import numpy as np
import argparse
import time
import paho.mqtt.client as mqtt  # New import
import json                      # New import
import sys

cv2.setNumThreads(1)

# --- Configuration ---
DEFAULT_MODEL_PATH = "/usr/share/human-detector/"
DEFAULT_CONF_THRESHOLD = 0.5
DEFAULT_NMS_THRESHOLD = 0.4

def connect_mqtt(broker, port, user, password, client_id):
    """Establishes and returns a connection to the MQTT broker."""
    print(f"INFO: Connecting to MQTT broker at {broker}...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id)
    client.username_pw_set(user, password)
    client.tls_set()
    try:
        client.connect(broker, port, 60)
        client.loop_start()
        print("INFO: MQTT connection successful.")
        return client
    except Exception as e:
        print(f"ERROR: Could not connect to MQTT broker: {e}", file=sys.stderr)
        return None

def main(stream_url, model_path, confidence, nms, camera_id, broker, port, user, password):
    """
    Connects to a video stream, detects humans, and publishes MQTT alerts.
    """
    # --- Load YOLO Model (same as your script) ---
    try:
        weights_path = f"{model_path}/yolov4-tiny.weights"
        cfg_path = f"{model_path}/yolov4-tiny.cfg"
        names_path = f"{model_path}/coco.names"
        
        net = cv2.dnn.readNet(weights_path, cfg_path)
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

        with open(names_path, "r") as f:
            classes = [line.strip() for line in f.readlines()]
        
        output_layers = [net.getLayerNames()[i - 1] for i in net.getUnconnectedOutLayers()]
        print(f"INFO: Model loaded successfully. Looking for 'person' class.")
    except Exception as e:
        print(f"ERROR: Could not load model. Error: {e}", file=sys.stderr)
        return

    # --- Connect to MQTT ---
    mqtt_client_id = f"pi-detector-{camera_id}"
    mqtt_topic = f"cabin/camera/{camera_id}/detection"
    mqtt_client = connect_mqtt(broker, port, user, password, mqtt_client_id)
    if not mqtt_client:
        return # Exit if MQTT connection fails

    # --- Build GStreamer Pipeline (same as your script) ---
    try:
        parts = stream_url.replace("tcp://", "").split(":")
        host = parts[0]
        port_num = int(parts[1])
        pipeline = (
            f"tcpclientsrc host={host} port={port_num} ! "
            "tsdemux ! h264parse ! avdec_h264 ! videoconvert ! "
            "video/x-raw,format=BGR ! queue max-size-buffers=1 leaky=downstream ! "
            "appsink sync=false max-buffers=1 drop=true"
        )
        print(f"INFO: Using GStreamer pipeline: {pipeline}")
    except Exception as e:
        print(f"ERROR: Invalid stream URL. Error: {e}", file=sys.stderr)
        return

    # --- Connect to Stream ---
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        print(f"ERROR: Cannot open GStreamer pipeline.", file=sys.stderr)
        return

    print(f"INFO: Successfully connected to stream. Starting detection loop...")

    # --- Detection Loop ---
    last_status = "unknown"  # Holds the last state ('clear' or 'detected')
    frame_idx = 0
    while True:
        try:
            ret, frame = cap.read()
            if not ret:
                print("WARNING: Pipeline source ended. Check ffmpeg service. Reconnecting...")
                time.sleep(5)
                cap.release()
                cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                continue

            human_detected = False
            
            # --- Frame skipping (same as your script) ---
            frame_idx += 1
            if frame_idx % 5:
                continue

            # --- DNN Processing (same as your script) ---
            blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (320, 320), swapRB=True, crop=False)
            net.setInput(blob)
            layer_outputs = net.forward(output_layers)

            for output in layer_outputs:
                for detection in output:
                    scores = detection[5:]
                    class_id = np.argmax(scores)
                    conf = scores[class_id]

                    if classes[class_id] == "person" and conf > confidence:
                        human_detected = True
                        break
                if human_detected:
                    break
            
            # --- NEW: Stateful MQTT Publishing Logic ---
            current_status = "detected" if human_detected else "clear"
            
            if current_status != last_status:
                print(f"INFO: Status change. New status: {current_status.upper()}")
                payload = json.dumps({
                    "event": f"person_{current_status}",
                    "camera_id": camera_id,
                    "timestamp": time.time()
                })
                
                if mqtt_client:
                    mqtt_client.publish(mqtt_topic, payload, qos=1, retain=True)
                
                last_status = current_status
            
            # Print to stdout as well, for 'systemctl status' debugging
            print(f"STATUS: {current_status.upper()}\r", end="", flush=True)

        except KeyboardInterrupt:
            print("\nINFO: Exiting.")
            break
        except Exception as e:
            print(f"ERROR: An error occurred in the loop: {e}", file=sys.stderr)
            time.sleep(5)

    cap.release()
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    print("INFO: Shutdown complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect humans and publish MQTT alerts.")
    parser.add_argument("--stream", type=str, required=True, help="URL of the TCP stream.")
    parser.add_argument("--camera-id", type=str, required=True, help="Friendly name for this camera (e.g., 'camera1').")
    parser.add_argument("--model-path", type=str, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONF_THRESHOLD)
    parser.add_argument("--nms", type=float, default=DEFAULT_NMS_THRESHOLD)
    
    # New MQTT arguments
    parser.add_argument("--broker", type=str, required=True, help="MQTT broker address.")
    parser.add_argument("--port", type=int, default=8883, help="MQTT broker port.")
    parser.add_argument("--user", type=str, required=True, help="MQTT username.")
    parser.add_argument("--password", type=str, required=True, help="MQTT password.")
    
    args = parser.parse_args()
    main(args.stream, args.model_path, args.confidence, args.nms,
         args.camera_id, args.broker, args.port, args.user, args.password)