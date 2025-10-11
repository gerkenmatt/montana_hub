# detect_human.py
import cv2
import numpy as np
import argparse
import time

cv2.setNumThreads(1)

# --- Configuration ---
# Set the default paths to the model files installed by your other Yocto recipe
DEFAULT_MODEL_PATH = "/usr/share/human-detector/"
DEFAULT_CONF_THRESHOLD = 0.5  # Confidence threshold
DEFAULT_NMS_THRESHOLD = 0.4   # Non-maximum suppression threshold

def main(stream_url, model_path, confidence, nms):
    """
    Connects to a video stream, detects humans, and prints a status code.
    Prints '1' if a human is detected, '0' otherwise.
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
        print(f"ERROR: Could not load model. Check paths. Error: {e}")
        return

    # --- Build GStreamer Pipeline using decodebin ---
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
        print(f"ERROR: Invalid stream URL format. Expected 'tcp://host:port'. Error: {e}")
        return

    # --- Connect to Stream using the pipeline ---
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        print(f"ERROR: Cannot open GStreamer pipeline.")
        return

    print(f"INFO: Successfully connected to stream. Starting detection loop...")

    # --- Detection Loop ---
    last_status = -1 
    frame_idx = 0
    while True:
        try:
            ret, frame = cap.read()
            if not ret:
                print("WARNING: Pipeline source ended. Check ffmpeg service.")
                time.sleep(5)
                cap.release()
                cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                continue

            human_detected = False

            frame_idx += 1
            if frame_idx % 5:               # run DNN every 5th frame to cut load 80%
                continue

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

            # Output Signal (Overwriting the current line)
            current_status = "HUMAN DETECTED" if human_detected else "CLEAR"

            # Use '\r' (carriage return) to jump to the start of the line
            print(f"STATUS: {current_status}\r", end="", flush=True)

        except KeyboardInterrupt:
            print("\nINFO: Exiting.")
            break
        except Exception as e:
            print(f"ERROR: An error occurred in the loop: {e}")
            time.sleep(5)

    cap.release()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect humans in a network stream and output a status signal.")
    parser.add_argument("--stream", type=str, required=True, help="URL of the TCP or RTSP stream.")
    parser.add_argument("--model-path", type=str, default=DEFAULT_MODEL_PATH, help="Path to the directory containing model files.")
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONF_THRESHOLD, help="Minimum detection confidence.")
    parser.add_argument("--nms", type=float, default=DEFAULT_NMS_THRESHOLD, help="Non-Maximum Suppression threshold.")
    
    args = parser.parse_args()
    main(args.stream, args.model_path, args.confidence, args.nms)