# MetalSense — Real-Time Metal Surface Inspection & Defect Detection System

MetalSense is a full-stack working prototype for a **Real-Time Metal Surface Inspection & Defect Detection System**. It implements a continuous, non-blocking asynchronous inspection loop (Capture → Preprocess → Detect → Classify → Store → Publish → Web Dashboard Update) rather than a single request/response cycle.

---

## 🚀 Key Prototype Features & Robust Fallbacks

The system is designed to work in **any developer environment** out-of-the-box, with or without specialized hardware:

1. **Demo Mode (YOLOv8 & Defect Emulation)**:
   - Since custom metal-defect weights are not included, the prototype defaults to `yolov8n.pt` (pre-trained on COCO).
   - The system maps detected objects above `CONFIDENCE_THRESHOLD` (e.g. phone, cup, person, bottle) to simulated defects (`Scratch`, `Dent`, `Crack`, `Pinhole`) and marks the product status as **FAIL** (BAD).
   - If no objects are in the frame, it is marked as **PASS** (GOOD).
2. **Webcam Mocking (Auto-detect / Force Mode)**:
   - If `MOCK_MODE=true` (in `.env`) or if no physical webcam is detected, the capture module automatically cycles through a folder of generated metal surface sample images (`mock_images/`) containing clean sheets and simulated defect markings.
   - If the folder is empty, the system dynamically generates synthetic brushed-metal textures in memory so it remains fully functional.
3. **Database Offline Resiliency**:
   - If MongoDB is offline, the system logs warnings, attempts reconnection with exponential backoff in a background thread, and runs in a degraded offline mode.
   - It caches the last 50 inspection logs in a local in-memory buffer so the **History Logs** and **Stats Summary** tables still work on the dashboard.
4. **MQTT Offline Resiliency**:
   - If the MQTT Broker is offline, the system logs warnings and queues messages in an internal asyncio queue. It automatically retries connections with backoff in a background loop without blocking the main inspection task.

---

## 📁 Module Directory Structure

| Module | File | Description |
| :--- | :--- | :--- |
| **Image Acquisition** | [capture.py](file:///C:/Users/a1eirnqz/.gemini/antigravity/scratch/metal-inspection/capture.py) | Captures webcam feed (OpenCV) or cycles mock images / generates textures. |
| **Image Preprocessing** | [preprocess.py](file:///C:/Users/a1eirnqz/.gemini/antigravity/scratch/metal-inspection/preprocess.py) | Normalizes and resizes frames for inference. |
| **Defect Detection (YOLO)** | [detector.py](file:///C:/Users/a1eirnqz/.gemini/antigravity/scratch/metal-inspection/detector.py) | Executes Ultralytics YOLOv8 object detection on processed frames. |
| **Defect Classification** | [classifier.py](file:///C:/Users/a1eirnqz/.gemini/antigravity/scratch/metal-inspection/classifier.py) | Implements DEMO MODE rules mapping COCO objects to simulated defects. |
| **Data Storage (MongoDB)** | [db.py](file:///C:/Users/a1eirnqz/.gemini/antigravity/scratch/metal-inspection/db.py) | Async DB interface using `motor`. Handles reconnects and writes. |
| **Real-Time Comms (MQTT)** | [mqtt_client.py](file:///C:/Users/a1eirnqz/.gemini/antigravity/scratch/metal-inspection/mqtt_client.py) | Background MQTT publishing client using `aiomqtt`. |
| **Live Feed (WebSocket)** | [ws_manager.py](file:///C:/Users/a1eirnqz/.gemini/antigravity/scratch/metal-inspection/ws_manager.py) | Broadcasts real-time frames, metadata, and counters to browsers. |
| **Analytics & History** | [analytics.py](file:///C:/Users/a1eirnqz/.gemini/antigravity/scratch/metal-inspection/analytics.py) | Manages in-memory stats tracker and DB aggregation queries. |
| **Web Server App** | [main.py](file:///C:/Users/a1eirnqz/.gemini/antigravity/scratch/metal-inspection/main.py) | Entry point exposing FastAPI, WebSocket endpoints, and static HTML UI. |

---

## ⚙️ Quick Start Instructions

### Prerequisites
- Python 3.11+
- (Optional) Docker for MongoDB + MQTT Broker

### Step 1: Clone and Install Dependencies
Navigate to your project directory:
```bash
# Install required Python libraries
pip install -r requirements.txt
```

### Step 2: Spin Up Infrastructure (Optional)
If you have Docker installed, spin up MongoDB and Eclipse Mosquitto MQTT Broker:
```bash
docker-compose up -d
```
*Note: If you do not run Docker, the system will log reconnect warnings but function normally in offline mode.*

### Step 3: Run the Application
Start the FastAPI server:
```bash
python main.py
```
Or run using uvicorn:
```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

On start, the server will automatically download `yolov8n.pt` and generate five mock images under `mock_images/` representing clean and defective sheets.

### Step 4: Open the Dashboard
Open your web browser and go to:
[http://127.0.0.1:8000](http://127.0.0.1:8000)

Click **Start Inspection** to activate the continuous inspection loop.

---

## 📡 API Reference & Comms

### REST Endpoints
- `POST /inspection/start`: Starts the continuous inspection background task.
- `POST /inspection/stop`: Stops the continuous inspection background task.
- `GET /inspection/status`: Returns system running modes and DB/MQTT statuses.
- `GET /history`: Returns logs (filterable by `status`, `defect_type`, `date_start`, `date_end`).
- `GET /analytics/summary`: Compiles cumulative inspection totals and ratios.

### WebSocket Channel
- `WS /ws/dashboard`: Real-time duplex channel broadcasting frames (`image_base64`), metadata, and stats counters.

### MQTT Topics
- `inspection/results`: Publishes JSON document payload of each frame inspection.
- `inspection/status`: Publishes inspection loop state updates (`{"status": "running" | "stopped"}`).
