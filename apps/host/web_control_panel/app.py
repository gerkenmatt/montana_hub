# app.py

import cv2
import uvicorn
import paho.mqtt.client as mqtt
import json
import asyncio
import numpy as np 
import time
import threading
from fastapi import FastAPI, Request, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

# --- Configuration ---
MQTT_BROKER = "montanaiothub.cloud"
MQTT_PORT = 8883
MQTT_USER = "montana_mqtt_hub"
MQTT_PASS = "nixon1001"
MQTT_STATUS_TOPIC = "cabin/camera/+/detection"
MQTT_SETTINGS_TOPIC = "cabin/hub/settings"

PI_VIDEO_URL_1 = "tcp://10.0.0.2:9192" 
PI_VIDEO_URL_2 = "tcp://10.0.0.2:9193" 
# ---------------------

app = FastAPI()
templates = Jinja2Templates(directory="templates")
queue = asyncio.Queue()
mqtt_client = None

# --- 1. The Robust Video Camera Class ---

class VideoCamera(threading.Thread):
    def __init__(self, url):
        threading.Thread.__init__(self)
        self.url = url
        self.current_frame = None
        self.running = True
        self.lock = threading.Lock()
        
        # Create a placeholder image (Red "Connecting...")
        self.placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(self.placeholder, "Connecting to Pi...", (100, 240), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        _, buffer = cv2.imencode('.jpg', self.placeholder)
        self.current_frame = buffer.tobytes()

    def run(self):
        print(f"Starting persistent connection to {self.url}")
        while self.running:
            cap = cv2.VideoCapture(self.url)
            
            # Optimization: Don't buffer old frames
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                print(f"Failed to connect to {self.url}. Retrying in 5s...")
                time.sleep(5)
                continue

            print(f"Connected to {self.url}")
            
            while self.running:
                success, frame = cap.read()
                if not success:
                    print(f"Stream lost {self.url}. Reconnecting...")
                    break
                
                # Encode to JPEG
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    with self.lock:
                        self.current_frame = buffer.tobytes()
                
                # Small sleep to prevent CPU hogging
                time.sleep(0.01) 
            
            cap.release()

    def get_frame(self):
        with self.lock:
            return self.current_frame

# --- Instantiate the Global Cameras ---
# These start connecting immediately when the script runs
cam1 = VideoCamera(PI_VIDEO_URL_1)
cam1.daemon = True # Kill thread when main app exits
cam1.start()

cam2 = VideoCamera(PI_VIDEO_URL_2)
cam2.daemon = True
cam2.start()

# ----------------------------------------

class EmailSetting(BaseModel):
    enabled: bool

# --- MQTT Logic (Unchanged) ---
def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected to MQTT Broker!")
    client.subscribe(MQTT_STATUS_TOPIC)
    print(f"Subscribed to {MQTT_STATUS_TOPIC}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        camera_id = msg.topic.split('/')[2]
        payload['camera_id'] = camera_id 
        queue.put_nowait(json.dumps(payload))
    except Exception as e:
        print(f"Error in on_message: {e}")

@app.on_event("startup")
def start_mqtt_client():
    global mqtt_client
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "web-control-panel-client")
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_client.tls_set()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start() 
    except Exception as e:
        print(f"Failed to connect to MQTT: {e}")

@app.post("/api/settings/email")
async def set_email_notifications(setting: EmailSetting):
    if mqtt_client:
        state = "on" if setting.enabled else "off"
        payload = json.dumps({"notifications": state})
        mqtt_client.publish(MQTT_SETTINGS_TOPIC, payload, qos=1, retain=True)
        print(f"Command Sent: Email Notifications {state.upper()}")
        return {"status": "success", "state": state}
    return {"status": "error", "message": "MQTT not connected"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            message_str = await queue.get()
            await websocket.send_text(message_str)
    except WebSocketDisconnect:
        pass

# --- Video Stream Generators ---

async def generate_frames_from_camera(camera):
    """Yields the latest frame from the persistent camera object."""
    while True:
        frame = camera.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        
        # This controls the refresh rate for the browser
        # 0.05 = 20 FPS. Adjust if needed.
        await asyncio.sleep(0.05)

@app.get("/video_feed_1")
async def video_feed_1():
    return StreamingResponse(generate_frames_from_camera(cam1), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/video_feed_2")
async def video_feed_2():
    return StreamingResponse(generate_frames_from_camera(cam2), media_type="multipart/x-mixed-replace; boundary=frame")

# --- Main HTML ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)