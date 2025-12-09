# app.py

import cv2
import uvicorn
import paho.mqtt.client as mqtt
import json
import asyncio
import numpy as np 
import time
import threading
from fastapi import FastAPI, Request, Response, Form, File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import base64

# --- Configuration ---
MQTT_BROKER = "montanaiothub.cloud"
MQTT_PORT = 8883
MQTT_USER = "montana_mqtt_hub"
MQTT_PASS = "nixon1001"
MQTT_STATUS_TOPIC = "cabin/hub/status" 
MQTT_DETECTION_TOPIC = "cabin/camera/+/detection"
MQTT_SETTINGS_TOPIC = "cabin/hub/settings"
MQTT_COMMAND_TOPIC = "cabin/hub/command"
PI_BROKER_IP = "10.0.0.2"

# --- Camera Stream Ports (External/Remote TCP) ---
URL_CAM1_SD = "tcp://10.0.0.2:9190"
URL_CAM1_HD = "tcp://10.0.0.2:9192"
URL_CAM2_SD = "tcp://10.0.0.2:9191"
URL_CAM2_HD = "tcp://10.0.0.2:9193"
# ---------------------

app = FastAPI()
templates = Jinja2Templates(directory="templates")
queue = asyncio.Queue()
mqtt_client = None

# --- 1. ALWAYS-ON Video Camera Class ---
# This class starts immediately and NEVER stops reading frames.
# This ensures the TCP buffer never fills up.

class AlwaysOnCamera(threading.Thread):
    def __init__(self, url, name):
        threading.Thread.__init__(self)
        self.url = url
        self.name = name
        self.lock = threading.Lock()
        self.running = True
        self.enabled = False
        self.current_frame = None
        
        # Create placeholders
        self.img_connecting = self._make_placeholder("Connecting...", (50, 100, 200)) 
        self.img_offline = self._make_placeholder("OFFLINE", (0, 0, 255)) 
        self.img_disabled = self._make_placeholder("STREAM OFF", (30, 30, 30))
        self.current_frame = self.img_connecting

        # START IMMEDIATELY
        self.daemon = True
        self.start()

    def set_state(self, is_enabled):
        """Enable or Disable the network connection attempts"""
        self.enabled = is_enabled
        if not is_enabled:
            with self.lock:
                self.current_frame = self.img_disabled
        print(f"[{self.name}] State set to {'ENABLED' if is_enabled else 'DISABLED'}")

    def _make_placeholder(self, text, color):
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(img, (0,0), (640,480), color, 10) 
        font = cv2.FONT_HERSHEY_SIMPLEX
        textsize = cv2.getTextSize(text, font, 1, 2)[0]
        textX = (img.shape[1] - textsize[0]) // 2
        textY = (img.shape[0] + textsize[1]) // 2
        cv2.putText(img, text, (textX, textY), font, 1, (255, 255, 255), 2)
        _, buf = cv2.imencode('.jpg', img)
        return buf.tobytes()

    def run(self):
        print(f"[{self.name}] Thread started (Waiting for Enable signal)")
        while self.running:
            # 1. SLEEP MODE: If disabled, just wait and do nothing
            if not self.enabled:
                time.sleep(1)
                continue

            # 2. ACTIVE MODE: Try to connect
            cap = cv2.VideoCapture(self.url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                # Only log if we are supposed to be connected
                if self.enabled:
                    print(f"[{self.name}] Failed to connect. Retrying in 5s...")
                    with self.lock:
                        self.current_frame = self.img_connecting
                time.sleep(5)
                continue

            print(f"[{self.name}] Stream CONNECTED")
            
            while self.running and self.enabled: # Check enabled inside loop too!
                success, frame = cap.read()
                
                if not success:
                    print(f"[{self.name}] Stream lost. Reconnecting...")
                    break 
                
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    with self.lock:
                        self.current_frame = buffer.tobytes()
                
                time.sleep(0.005) 
            
            cap.release()

    def get_frame(self):
        with self.lock:
            return self.current_frame

# --- Instantiate Cameras ---
# We store them in a dict called 'cameras' for easy lookup by the API
cameras = {
    "cam1-sd": AlwaysOnCamera(URL_CAM1_SD, "Cam1 SD"),
    "cam1-hd": AlwaysOnCamera(URL_CAM1_HD, "Cam1 HD"),
    "cam2-sd": AlwaysOnCamera(URL_CAM2_SD, "Cam2 SD"),
    "cam2-hd": AlwaysOnCamera(URL_CAM2_HD, "Cam2 HD")
}

# Create pointers so the existing feed routes below still work
cam1_sd = cameras["cam1-sd"]
cam1_hd = cameras["cam1-hd"]
cam2_sd = cameras["cam2-sd"]
cam2_hd = cameras["cam2-hd"]

# --- MQTT Logic (Unchanged) ---
class EmailSetting(BaseModel):
    enabled: bool

class UploadSetting(BaseModel):
    enabled: bool

class CameraControl(BaseModel):
    camera_id: str  # e.g., "cam1"
    stream_type: str # "sd" or "hd"
    mode: str       # "OFF", "LOW", "MEDIUM", "HIGH"

def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected to MQTT Broker!")
    client.subscribe(MQTT_STATUS_TOPIC)    
    client.subscribe(MQTT_DETECTION_TOPIC) 
    print(f"Subscribed to {MQTT_STATUS_TOPIC} and {MQTT_DETECTION_TOPIC}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        if "camera" in msg.topic:
            payload['type'] = 'detection'
            payload['camera_id'] = msg.topic.split('/')[2]
        elif "status" in msg.topic:
            payload['type'] = 'telemetry'
        queue.put_nowait(json.dumps(payload))
    except Exception as e: 
        print(f"Error processing message: {e}")

@app.on_event("startup")
def start_mqtt():
    global mqtt_client
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "web-control")
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_client.tls_set()
    mqtt_client.on_connect = on_connect 
    mqtt_client.on_message = on_message
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except: pass

# --- API Endpoints (Unchanged) ---
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

@app.post("/api/system/reboot")
async def reboot_system():
    if mqtt_client:
        mqtt_client.publish(MQTT_COMMAND_TOPIC, json.dumps({"action": "reboot"}), qos=1)
        return {"status": "success"}
    return {"status": "error"}

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_text(await queue.get())
    except WebSocketDisconnect: pass

@app.post("/api/camera/control")
async def control_camera_endpoint(cmd: CameraControl):
    """
    Sends command via the Main Cloud Broker (montanaiothub.cloud).
    The Pi must be bridging this topic or connected to the cloud for this to work.
    """
    # 1. Construct IDs
    instance_id_remote = f"{cmd.camera_id}-{cmd.stream_type}-remote"
    
    mqtt_topic = f"cabin/cameras/{instance_id_remote}/control"
    
    # 2. Toggle Local State (so the web app viewer wakes up)
    local_cam_id = f"{cmd.camera_id}-{cmd.stream_type}"
    target_cam = cameras.get(local_cam_id)
    
    if target_cam:
        if cmd.mode in ["OFF", "SNAPSHOT", "LOW"]:
            target_cam.set_state(False)
        else:
            target_cam.set_state(True)
    
    # 3. Publish to Cloud Broker using the existing global client
    if mqtt_client and mqtt_client.is_connected():
        print(f"Publishing {cmd.mode} to CLOUD: {mqtt_topic}")
        # Retain=True ensures the Pi picks it up even if it momentarily loses internet
        mqtt_client.publish(mqtt_topic, cmd.mode, qos=1, retain=True)
        return {"status": "success", "target": instance_id_remote, "mode": cmd.mode}
    else:
        print("Error: Cloud MQTT client is not connected.")
        return {"status": "error", "detail": "Cloud MQTT not connected"}

@app.post("/api/upload/snapshot")
async def upload_snapshot(camera_id: str = Form(...), file: UploadFile = File(...)):
    try:
        print(f"INFO: Receiving snapshot for {camera_id}...")
        
        # 1. Read file into RAM
        contents = await file.read()
        
        # 2. Convert to Base64 for the Browser
        b64_string = base64.b64encode(contents).decode('utf-8')
        
        # 3. Create the WebSocket Payload
        payload = {
            "type": "snapshot",
            "camera_id": camera_id,
            "image": b64_string
        }
        
        # 4. Push to WebSocket Queue (Instant update for browser)
        await queue.put(json.dumps(payload))
        
        return {"status": "success"}
        
    except Exception as e:
        print(f"ERROR: Snapshot processing failed: {e}")
        return {"status": "error", "detail": str(e)}

# --- Video Stream Generator ---
async def gen_frames(camera):
    try:
        while True:
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + camera.get_frame() + b'\r\n')
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        pass

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
    uvicorn.run(app, host="0.0.0.0", port=8000)