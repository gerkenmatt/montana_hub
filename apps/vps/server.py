# server.py (Run this on the VPS)
import uvicorn
import shutil
import os
import json
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Setup storage
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIP_DIR = os.path.join(BASE_DIR, "static/clips")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")

# Mount static files so they can be viewed via URL
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, 'w') as f:
        json.dump([], f)

@app.post("/api/upload")
async def upload_clip(
    camera_id: str = Form(...), 
    confidence: float = Form(...), 
    timestamp: float = Form(...),
    file: UploadFile = File(...)
):
    try:
        filename = f"{camera_id}_{int(timestamp)}.mp4"
        file_path = os.path.join(CLIP_DIR, filename)

        with open(file_path, "wb+") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Update History
        new_event = {
            "camera_id": camera_id,
            "confidence": confidence,
            "timestamp": timestamp,
            # Note: This URL assumes you access via VPN IP 10.0.0.1
            "video_url": f"http://10.0.0.1:8080/static/clips/{filename}",
            "date_string": datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(HISTORY_FILE, 'r') as f:
            history = json.load(f)

        history.insert(0, new_event)
        if len(history) > 100: # Keep last 100 events
            history = history[:100]

        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f)

        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/history")
async def get_history():
    with open(HISTORY_FILE, 'r') as f:
        return json.load(f)

@app.delete("/api/delete/{camera_id}/{timestamp}")
async def delete_event(camera_id: str, timestamp: float):
    """Deletes a clip file and its history entry."""
    try:
        # 1. Reconstruct the filename
        filename = f"{camera_id}_{int(float(timestamp))}.mp4"
        file_path = os.path.join(CLIP_DIR, filename)

        # 2. Delete the file from disk
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted file: {filename}")
        else:
            print(f"File not found (might have been deleted already): {filename}")

        # 3. Remove from History JSON
        with open(HISTORY_FILE, 'r') as f:
            history = json.load(f)

        # Filter out the item with the matching timestamp and camera_id
        # We use a list comprehension to keep everything THAT DOES NOT MATCH
        history = [h for h in history if not (h['timestamp'] == timestamp and h['camera_id'] == camera_id)]

        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f)

        return {"status": "success"}

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    # Listen on the WireGuard Interface IP (10.0.0.1)
    uvicorn.run(app, host="10.0.0.1", port=8080)
