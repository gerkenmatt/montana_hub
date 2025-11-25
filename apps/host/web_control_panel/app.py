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

# --- NEW: Define all 4 Streams ---
# Camera 1 (Front Door)
URL_CAM1_SD = "tcp://10.0.0.2:9190"
URL_CAM1_HD = "tcp://10.0.0.2:9192"

# Camera 2 (Driveway)
URL_CAM2_SD = "tcp://10.0.0.2:9191"
URL_CAM2_HD = "tcp://10.0.0.2:9193"
# ---------------------

app = FastAPI()
templates = Jinja2Templates(directory="templates")
queue = asyncio.Queue()
mqtt_client = None

# --- Video Camera Class (Persistent Connection) ---
class VideoCamera(threading.Thread):
    def __init__(self, url):
        threading.Thread.__init__(self)
        self.url = url
        self.current_frame = None
        self.running = True
        self.lock = threading.Lock()
        
        # Placeholder image
        self.placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(self.placeholder, "Connecting...", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
        _, buf = cv2.imencode('.jpg', self.placeholder)
        self.current_frame = buf.tobytes()

    def run(self):
        while self.running:
            cap = cv2.VideoCapture(self.url)
            if not cap.isOpened():
                time.sleep(5)
                continue
            while self.running:
                success, frame = cap.read()
                if not success: break
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    with self.lock: self.current_frame = buffer.tobytes()
                time.sleep(0.01)
            cap.release()
    
    def get_frame(self):
        with self.lock: return self.current_frame

# --- NEW: Instantiate 4 Cameras ---
# We keep connections open to all 4 to prevent "Connection Refused" lag
cam1_sd = VideoCamera(URL_CAM1_SD)
cam1_sd.daemon = True; cam1_sd.start()

cam1_hd = VideoCamera(URL_CAM1_HD)
cam1_hd.daemon = True; cam1_hd.start()

cam2_sd = VideoCamera(URL_CAM2_SD)
cam2_sd.daemon = True; cam2_sd.start()

cam2_hd = VideoCamera(URL_CAM2_HD)
cam2_hd.daemon = True; cam2_hd.start()

# --- MQTT Logic (Unchanged) ---
class EmailSetting(BaseModel):
    enabled: bool

class UploadSetting(BaseModel):
    enabled: bool

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        payload['camera_id'] = msg.topic.split('/')[2]
        queue.put_nowait(json.dumps(payload))
    except: pass

@app.on_event("startup")
def start_mqtt():
    global mqtt_client
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "web-control")
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_client.tls_set()
    mqtt_client.on_message = on_message
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.subscribe(MQTT_STATUS_TOPIC)
        mqtt_client.loop_start()
    except: pass

@app.post("/api/settings/email")
async def set_email(setting: EmailSetting):
    if mqtt_client:
        state = "on" if setting.enabled else "off"
        mqtt_client.publish(MQTT_SETTINGS_TOPIC, json.dumps({"notifications": state}), qos=1, retain=True)
        return {"status": "success"}
    return {"status": "error"}

@app.post("/api/settings/upload")
async def set_upload(setting: UploadSetting):
    if mqtt_client:
        state = "on" if setting.enabled else "off"
        mqtt_client.publish(MQTT_SETTINGS_TOPIC, json.dumps({"upload": state}), qos=1, retain=True)
        return {"status": "success"}
    return {"status": "error"}

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_text(await queue.get())
    except WebSocketDisconnect: pass

# --- Video Stream Generator ---
async def gen_frames(camera):
    while True:
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + camera.get_frame() + b'\r\n')
        await asyncio.sleep(0.05)

# --- NEW: 4 Distinct Endpoints ---
@app.get("/feed/cam1/sd")
async def feed1_sd(): return StreamingResponse(gen_frames(cam1_sd), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/feed/cam1/hd")
async def feed1_hd(): return StreamingResponse(gen_frames(cam1_hd), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/feed/cam2/sd")
async def feed2_sd(): return StreamingResponse(gen_frames(cam2_sd), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/feed/cam2/hd")
async def feed2_hd(): return StreamingResponse(gen_frames(cam2_hd), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/", response_class=HTMLResponse)
async def root(request: Request): return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)