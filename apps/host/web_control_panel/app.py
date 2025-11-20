# app.py

import cv2
import uvicorn
import paho.mqtt.client as mqtt
import json
import asyncio
import numpy as np 
import time
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.websockets import WebSocket, WebSocketDisconnect

# --- Configuration ---
MQTT_BROKER = "montanaiothub.cloud"
MQTT_PORT = 8883
MQTT_USER = "montana_mqtt_hub"
MQTT_PASS = "nixon1001"
MQTT_STATUS_TOPIC = "cabin/camera/+/detection"

# Update to your 1080p external ports
PI_VIDEO_URL_1 = "tcp://10.0.0.2:9192" # Camera 1 (1080p)
PI_VIDEO_URL_2 = "tcp://10.0.0.2:9193" # Camera 2 (1080p)
# ---------------------

app = FastAPI()
templates = Jinja2Templates(directory="templates")
queue = asyncio.Queue()

# --- 1. MQTT Bridge (Unchanged) ---
def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected to MQTT Broker!")
    client.subscribe(MQTT_STATUS_TOPIC)
    print(f"Subscribed to {MQTT_STATUS_TOPIC}")

def on_message(client, userdata, msg):
    try:
        # Add the topic so we know which camera sent the message
        payload = json.loads(msg.payload.decode('utf-8'))
        # Extract camera_id from topic: cabin/camera/camera1/detection
        camera_id = msg.topic.split('/')[2]
        payload['camera_id'] = camera_id # Ensure ID is in payload
        queue.put_nowait(json.dumps(payload))
    except Exception as e:
        print(f"Error in on_message: {e}")

@app.on_event("startup")
def start_mqtt_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "web-control-panel-client")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set()
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start() 
    except Exception as e:
        print(f"Failed to connect to MQTT: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Browser WebSocket connected.")
    try:
        while True:
            message_str = await queue.get()
            await websocket.send_text(message_str)
    except WebSocketDisconnect:
        print("Browser WebSocket disconnected.")

# --- 2. The Video Stream (MJPEG) ---

async def generate_video_frames(stream_url):
    """Connects to a specific video stream and yields JPEG frames."""
    cap = cv2.VideoCapture(stream_url)
    
    if not cap.isOpened():
        print(f"Error: Cannot open video stream at {stream_url}")
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(img, "Connection Failed", (100, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        _, buffer = cv2.imencode('.jpg', img)
        frame_bytes = buffer.tobytes()
        while True: # Keep yielding the error image so browser doesn't break
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            await asyncio.sleep(1)

    print(f"Video stream connected: {stream_url}")
    while True:
        try:
            success, frame = cap.read()
            if not success:
                print(f"Stream ended {stream_url}. Reconnecting...")
                cap.release()
                await asyncio.sleep(5)
                cap = cv2.VideoCapture(stream_url)
                continue
            
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret: continue
            
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            await asyncio.sleep(0.05) 

        except Exception as e:
            print(f"Error in video loop: {e}")
            break
    cap.release()

@app.get("/video_feed_1")
def video_feed_1():
    return StreamingResponse(generate_video_frames(PI_VIDEO_URL_1), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/video_feed_2")
def video_feed_2():
    return StreamingResponse(generate_video_frames(PI_VIDEO_URL_2), media_type="multipart/x-mixed-replace; boundary=frame")

# --- 3. The Main HTML Page ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)