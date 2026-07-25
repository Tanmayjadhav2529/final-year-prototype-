import os
import cv2
import numpy as np
import asyncio
import logging
import base64
import uuid
import json
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("metal_inspection.main")

from dotenv import find_dotenv
resolved_path = find_dotenv()
logger.info(f"Loaded .env from: {resolved_path}")
logger.info(f"Raw MOCK_MODE value from environment: {os.getenv('MOCK_MODE')!r}")


# Import system modules
from db import db_manager
from mqtt_client import mqtt_manager
from ws_manager import ws_manager
from capture import image_acquisition
from preprocess import preprocess_frame
from detector import defect_detector
from classifier import classify_detections, classify_frame
from analytics import analytics_tracker, get_db_summary
import settings as settings_store

app = FastAPI(
    title="Real-Time Metal Surface Inspection API",
    description="Backend for continuous metal surface inspection & defect detection.",
    version="1.0.0"
)

# Enable CORS for development ease
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global states
inspection_running = False
stream_task = None
inference_task = None
# In-memory history buffer for offline mode (holds last 50 inspections)
local_history_buffer = []
local_manual_uploads = []

# Shared frame and results variables
shared_raw_frame = None
shared_defects = []
shared_status = "PASS"
shared_person_boxes = []

def apply_privacy_blur(img, boxes):
    """Applies a strong Gaussian blur to privacy ROI bounding boxes."""
    if not boxes or img is None:
        return img
    h, w = img.shape[:2]
    for box in boxes:
        x1 = max(0, min(box[0], w - 1))
        y1 = max(0, min(box[1], h - 1))
        x2 = max(0, min(box[2], w - 1))
        y2 = max(0, min(box[3], h - 1))
        
        if x2 - x1 > 2 and y2 - y1 > 2:
            roi = img[y1:y2, x1:x2]
            kw = 51
            if kw >= (x2 - x1):
                kw = (x2 - x1) | 1
                if kw >= (x2 - x1):
                    kw = max(3, kw - 2)
            kh = 51
            if kh >= (y2 - y1):
                kh = (y2 - y1) | 1
                if kh >= (y2 - y1):
                    kh = max(3, kh - 2)
                    
            blurred_roi = cv2.GaussianBlur(roi, (kw, kh), 0)
            img[y1:y2, x1:x2] = blurred_roi
    return img

@app.on_event("startup")
def startup_event():
    """Startup hook to initiate background connections."""
    # Connect to MongoDB & MQTT broker in the background
    db_manager.start_connection()
    mqtt_manager.start()

@app.on_event("shutdown")
def shutdown_event():
    """Shutdown hook to release resources."""
    global inspection_running
    inspection_running = False
    image_acquisition.release()

async def stream_loop():
    """High-speed streaming loop that captures and broadcasts frames to WebSockets."""
    global inspection_running, shared_raw_frame, shared_defects, shared_status, shared_person_boxes
    logger.info("Continuous video streaming loop active.")
    
    while inspection_running:
        try:
            # 1. Capture frame (offloaded to thread)
            raw_frame = await asyncio.to_thread(image_acquisition.capture_frame)
            if raw_frame is None:
                await asyncio.sleep(0.05)
                continue
                
            # Update shared frame for the inference loop
            shared_raw_frame = raw_frame
            
            # 2. Preprocess (resize and standard formatting)
            processed_frame = preprocess_frame(raw_frame)
            if processed_frame is None:
                await asyncio.sleep(0.05)
                continue
                
            # 3. Copy shared variables locally to avoid collision during overlay rendering
            local_defects = list(shared_defects)
            local_status = shared_status
            local_person_boxes = list(shared_person_boxes)
            
            # 4. Apply privacy blur and overlay latest defects bounding boxes and labels
            overlay_frame = processed_frame.copy()
            overlay_frame = apply_privacy_blur(overlay_frame, local_person_boxes)
            
            for defect in local_defects:
                bbox = defect["bbox"]
                dtype = defect["type"]
                conf = defect["confidence"]
                
                # Draw defect bounding box
                cv2.rectangle(overlay_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 0, 255), 2)
                
                # Bbox label
                label = f"{dtype} ({conf:.2%})"
                cv2.putText(overlay_frame, label, (bbox[0], bbox[1] - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)
            
            # 5. JPEG encode with quality=70 (offloaded to thread)
            def encode_jpeg(img):
                _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
                return base64.b64encode(buf).decode('utf-8')
                
            image_base64 = await asyncio.to_thread(encode_jpeg, overlay_frame)
            
            # 6. Broadcast feed update to WebSockets (metrics/charts are omitted here)
            ws_payload = {
                "image_base64": image_base64,
                "status": local_status,
                "defects": local_defects
            }
            await ws_manager.broadcast(ws_payload)
            
        except Exception as e:
            logger.error(f"Error in stream loop cycle: {e}", exc_info=True)
            
        # Broadcast at ~100ms interval (approx. 10 FPS) for smooth streaming
        await asyncio.sleep(0.1)
        
    logger.info("Continuous video streaming loop idle.")


async def inference_loop():
    """Lower-speed loop running YOLO inference and updating database, MQTT, and charts."""
    global inspection_running, shared_raw_frame, shared_defects, shared_status, shared_person_boxes, local_history_buffer
    logger.info("Continuous YOLO inference loop active.")
    
    loop_interval = float(os.getenv("LOOP_INTERVAL_SECONDS", "1.5"))
    await mqtt_manager.publish_status("running")
    
    while inspection_running:
        try:
            local_frame = shared_raw_frame
            if local_frame is None:
                await asyncio.sleep(0.1)
                continue
                
            processed_frame = preprocess_frame(local_frame)
            if processed_frame is None:
                await asyncio.sleep(0.1)
                continue
                
            # 1. Run YOLO inference (offloaded to thread)
            detections = await asyncio.to_thread(defect_detector.detect, processed_frame)
            
            # 2. Map detections to defect categories & classify GOOD/BAD
            status, defects, person_boxes = classify_frame(detections, processed_frame)
            logger.info(f"Raw detections: {[d['class_name'] for d in detections]} | status: {status} | defects: {defects} | person_boxes: {len(person_boxes)}")
            
            # Update shared parameters for the stream loop
            shared_defects = defects
            shared_status = status
            shared_person_boxes = person_boxes
            
            # 3. Create overlay frame with privacy blur applied for thumbnail & database storage
            overlay_frame = processed_frame.copy()
            overlay_frame = apply_privacy_blur(overlay_frame, person_boxes)
            
            for defect in defects:
                bbox = defect["bbox"]
                dtype = defect["type"]
                conf = defect["confidence"]
                cv2.rectangle(overlay_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 0, 255), 2)
                label = f"{dtype} ({conf:.2%})"
                cv2.putText(overlay_frame, label, (bbox[0], bbox[1] - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)
                            
            # 4. Generate thumbnail base64 and full base64 images (offloaded to threads)
            def encode_jpeg(img):
                _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
                return base64.b64encode(buf).decode('utf-8')
                
            image_base64 = await asyncio.to_thread(encode_jpeg, overlay_frame)
            
            # Generate thumbnail only if status is FAIL or store_image_on_pass is True
            store_image_on_pass = os.getenv("STORE_IMAGE_ON_PASS", "false").lower() == "true"
            if status == "FAIL" or store_image_on_pass:
                def generate_thumb(img):
                    thumb = cv2.resize(img, (160, 120))
                    _, buf = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    return base64.b64encode(buf).decode('utf-8')
                thumb_base64 = await asyncio.to_thread(generate_thumb, overlay_frame)
            else:
                thumb_base64 = None
            
            # 5. Populate inspection log
            timestamp = datetime.utcnow().isoformat() + "Z"
            product_id = f"PRD-{uuid.uuid4().hex[:8].upper()}"
            
            inspection_result = {
                "timestamp": timestamp,
                "product_id": product_id,
                "status": status,
                "defects": defects,
                "image_thumbnail_base64": thumb_base64,
                "source": "live_camera"
            }
            
            # Save into local buffer
            local_history_buffer.insert(0, inspection_result)
            if len(local_history_buffer) > 50:
                local_history_buffer.pop()
                
            # Build database document (branching on status and configuration)
            if status == "FAIL" or store_image_on_pass:
                db_document = inspection_result
            else:
                db_document = {
                    "timestamp": timestamp,
                    "product_id": product_id,
                    "status": status,
                    "source": "live_camera",
                    "image_thumbnail_base64": None
                }
                
            # 6. Database and MQTT writes (background non-blocking tasks)
            asyncio.create_task(db_manager.save_inspection(db_document))
            asyncio.create_task(mqtt_manager.publish("inspection/results", json.dumps(inspection_result)))
            
            # 7. Update metrics
            analytics_tracker.update(status, defects)
            
            # 8. Broadcast full payload containing product_id and metrics updates
            ws_payload = {
                "timestamp": timestamp,
                "product_id": product_id,
                "status": status,
                "defects": defects,
                "image_base64": image_base64,
                "counters": analytics_tracker.get_summary()
            }
            await ws_manager.broadcast(ws_payload)
            
        except Exception as e:
            logger.error(f"Error in inference loop cycle: {e}", exc_info=True)
            
        await asyncio.sleep(loop_interval)
        
    await mqtt_manager.publish_status("stopped")
    image_acquisition.release()
    logger.info("Continuous YOLO inference loop idle.")


# API endpoints
@app.post("/inspection/start")
async def start_inspection():
    global inspection_running, stream_task, inference_task
    if inspection_running:
        return JSONResponse({"status": "already_running", "message": "Inspection is already running."})
        
    inspection_running = True
    image_acquisition.init_capture()
    
    stream_task = asyncio.create_task(stream_loop())
    inference_task = asyncio.create_task(inference_loop())
    
    return JSONResponse({"status": "started", "message": "Inspection loop started successfully."})


@app.post("/inspection/stop")
async def stop_inspection():
    global inspection_running
    if not inspection_running:
        return JSONResponse({"status": "already_stopped", "message": "Inspection is not running."})
        
    inspection_running = False
    return JSONResponse({"status": "stopped", "message": "Inspection loop stop requested."})

@app.get("/inspection/status")
async def get_status():
    global inspection_running
    return {
        "running": inspection_running,
        "mode": "mock" if image_acquisition.mock_mode else "webcam",
        "mongodb_connected": db_manager.connected,
        "mqtt_connected": mqtt_manager.connected
        ,"role": os.getenv("LAPTOP_ROLE", "")
    }


@app.get("/settings/camera")
async def get_camera_settings():
    cfg = settings_store.load_settings()
    # Provide runtime live status from image_acquisition
    runtime = {
        "mode": "mock" if image_acquisition.mock_mode else "live",
        "camera_index": image_acquisition.camera_index,
        "resolution": getattr(image_acquisition, "resolution", cfg.get("resolution")),
        "available_cameras": []
    }
    return {**cfg, **runtime}


@app.post("/settings/camera")
async def post_camera_settings(payload: dict):
    """Apply camera-related settings live and persist them.

    Payload keys: mode (live|mock), camera_index (int), resolution (e.g. "640x480")
    If inspection is running, the function will stop loops briefly to apply new settings,
    then attempt to restart the inspection to preserve prior running state.
    """
    global inspection_running, stream_task, inference_task
    try:
        mode = payload.get("mode") or payload.get("mock_mode") or "live"
        camera_index = int(payload.get("camera_index", image_acquisition.camera_index))
        resolution = payload.get("resolution", getattr(image_acquisition, "resolution", "640x480"))

        prev_running = inspection_running
        if prev_running:
            # Signal loops to stop and release camera immediately
            inspection_running = False
            try:
                image_acquisition.release()
            except Exception:
                pass

        # Apply settings to acquisition device
        image_acquisition.init_capture(mode=("mock" if mode == "mock" else "live"), camera_index=camera_index, resolution=resolution)

        # Persist settings
        settings_store.save_settings(mode if mode in ("live", "mock") else ("mock" if mode==True else "live"), camera_index, resolution)

        # Decide result
        camera_opened = not image_acquisition.mock_mode

        # If inspection was running before, attempt to restart it (respecting fallback to mock)
        if prev_running:
            inspection_running = True
            # Start tasks again
            stream_task = asyncio.create_task(stream_loop())
            inference_task = asyncio.create_task(inference_loop())

        return JSONResponse({"status": "ok", "camera_opened": camera_opened, "mode": ("mock" if image_acquisition.mock_mode else "live")})
    except Exception as e:
        logger.error(f"Failed to apply camera settings: {e}", exc_info=True)
        # Ensure we are in a safe mock mode
        image_acquisition.mock_mode = True
        settings_store.save_settings("mock", image_acquisition.camera_index, getattr(image_acquisition, "resolution", "640x480"))
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/settings/camera/scan")
async def scan_cameras():
    try:
        results = await asyncio.to_thread(image_acquisition.scan_cameras)
        return {"results": results}
    except Exception as e:
        logger.error(f"Camera scan failed: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/history")
async def get_history(
    status: str = Query(None, description="Filter by status (PASS | FAIL)"),
    defect_type: str = Query(None, description="Filter by defect type (Scratch | Dent | Crack | Pinhole)"),
    date_start: str = Query(None, description="Start date ISO string"),
    date_end: str = Query(None, description="End date ISO string"),
    source: str = Query("live_camera", description="Filter by source (live_camera | manual_upload)")
):
    """
    Returns filtered history.
    Queries MongoDB if online, otherwise queries the local in-memory history buffers.
    """
    # 1. Build query filters
    filters = {}
    if status:
        filters["status"] = status
    if defect_type:
        filters["defects.type"] = {"$regex": defect_type, "$options": "i"}
    if source:
        filters["source"] = source
        
    if date_start or date_end:
        time_filter = {}
        if date_start:
            time_filter["$gte"] = date_start
        if date_end:
            time_filter["$lte"] = date_end
        filters["timestamp"] = time_filter

    # 2. Try fetching from MongoDB if connected
    if db_manager.connected:
        db_history = await db_manager.get_history(filters, limit=50)
        return db_history

    # 3. Fallback to local in-memory buffers
    logger.debug(f"Retrieving historical logs from local buffer for {source} (DB offline).")
    filtered_list = []
    target_buffer = local_manual_uploads if source == "manual_upload" else local_history_buffer
    
    for item in target_buffer:
        # Check status filter
        if status and item["status"] != status:
            continue
        # Check defect type filter
        if defect_type:
            has_defect = any(defect_type.lower() in d["type"].lower() for d in item["defects"])
            if not has_defect:
                continue
        # Check date range filter
        if date_start and item["timestamp"] < date_start:
            continue
        if date_end and item["timestamp"] > date_end:
            continue
            
        filtered_list.append(item)
    return filtered_list


@app.get("/analytics/summary")
async def get_analytics_summary(source: str = Query("live_camera", description="Filter by source (live_camera | manual_upload)")):
    """
    Compiles database analytics.
    Queries MongoDB if connected, otherwise falls back to local in-memory tracking.
    """
    if not db_manager.connected:
        if source == "manual_upload":
            total = len(local_manual_uploads)
            passed = sum(1 for item in local_manual_uploads if item["status"] == "PASS")
            failed = total - passed
            defect_rate = (failed / total * 100) if total > 0 else 0.0
            
            defect_counts = {
                "Scratch": 0,
                "Dent": 0,
                "Crack": 0,
                "Pinhole": 0,
                "Unknown": 0
            }
            for item in local_manual_uploads:
                for defect in item.get("defects", []):
                    dtype = defect.get("type", "")
                    matched = False
                    for key in defect_counts.keys():
                        if key in dtype:
                            defect_counts[key] += 1
                            matched = True
                            break
                    if not matched:
                        defect_counts["Unknown"] += 1
            
            summary = {
                "total": total,
                "passed": passed,
                "failed": failed,
                "defect_rate": round(defect_rate, 2),
                "defect_counts": defect_counts
            }
        else:
            summary = analytics_tracker.get_summary()
    else:
        summary = await get_db_summary(db_manager, source=source)
        
    # Add system statuses
    summary["system"] = {
        "mongodb_connected": db_manager.connected,
        "mqtt_connected": mqtt_manager.connected,
        "inspection_running": inspection_running
    }
    return summary


@app.post("/inspection/upload")
async def inspect_uploaded_image(file: UploadFile = File(...)):
    """
    Accepts an uploaded image, processes it, detects defects, saves the result
    to MongoDB, publishes to MQTT manual_results topic, and returns result.
    """
    try:
        contents = await file.read()
        
        # Decode image using PIL for broad format support (AVIF, WebP, etc.)
        def decode_image_pil(data, filename):
            import io
            from PIL import Image
            import pillow_avif  # Register AVIF plugin explicitly
            
            try:
                # Open image using BytesIO
                pil_img = Image.open(io.BytesIO(data))
                # Convert to RGB (in case of RGBA/Grayscale etc.)
                rgb_img = pil_img.convert("RGB")
                # Convert to NumPy array
                np_arr = np.array(rgb_img)
                # Convert RGB to BGR for OpenCV / YOLO
                return cv2.cvtColor(np_arr, cv2.COLOR_RGB2BGR)
            except Exception as e:
                logger.error(f"Pillow failed to decode upload file {filename}: {e}", exc_info=True)
                return None
                
        raw_frame = await asyncio.to_thread(decode_image_pil, contents, file.filename)
        if raw_frame is None:
            _, ext = os.path.splitext(file.filename)
            ext_str = ext.upper() if ext else "unknown"
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": f"Unsupported or corrupted image format: {ext_str}. Supported: JPG, PNG, WEBP, AVIF, BMP, TIFF."
                }
            )
            
        processed_frame = preprocess_frame(raw_frame)
        if processed_frame is None:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Failed to preprocess image."}
            )
            
        # Run YOLO detector (offloaded to thread)
        detections = await asyncio.to_thread(defect_detector.detect, processed_frame)
        
        # Defect mapping and classification
        status, defects, _ = classify_frame(detections, processed_frame)
        
        # Draw bounding boxes
        overlay_frame = processed_frame.copy()
        for defect in defects:
            bbox = defect["bbox"]
            dtype = defect["type"]
            conf = defect["confidence"]
            cv2.rectangle(overlay_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 0, 255), 2)
            label = f"{dtype} ({conf:.2%})"
            cv2.putText(overlay_frame, label, (bbox[0], bbox[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)
                        
        # Generate thumbnail and base64 full frame (offloaded to threads)
        def generate_thumb(img):
            thumb = cv2.resize(img, (160, 120))
            _, buf = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return base64.b64encode(buf).decode('utf-8')
            
        def encode_jpeg(img):
            _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return base64.b64encode(buf).decode('utf-8')
            
        thumb_base64 = await asyncio.to_thread(generate_thumb, overlay_frame)
        image_base64 = await asyncio.to_thread(encode_jpeg, overlay_frame)
        
        timestamp = datetime.utcnow().isoformat() + "Z"
        product_id = f"PRD-{uuid.uuid4().hex[:8].upper()}"
        
        inspection_result = {
            "timestamp": timestamp,
            "product_id": product_id,
            "status": status,
            "defects": defects,
            "image_thumbnail_base64": thumb_base64,
            "source": "manual_upload"
        }
        
        # Save to local manual uploads fallback list
        local_manual_uploads.insert(0, inspection_result)
        if len(local_manual_uploads) > 50:
            local_manual_uploads.pop()
            
        # Save to Database in background
        asyncio.create_task(db_manager.save_inspection(inspection_result))
        
        # Publish to MQTT manual results topic in background
        asyncio.create_task(mqtt_manager.publish("inspection/manual_results", json.dumps(inspection_result)))
        
        return {
            "timestamp": timestamp,
            "product_id": product_id,
            "status": status,
            "defects": defects,
            "image_base64": image_base64,
            "source": "manual_upload"
        }
        
    except Exception as e:
        logger.error(f"Error in inspect_uploaded_image: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Inspection failed: {str(e)}"}
        )
@app.get("/analytics/storage")
async def get_analytics_storage():
    """
    Returns database storage statistics:
    - total document count
    - count of documents containing images (image_thumbnail_base64 is not null/None)
    - estimated storage size in bytes
    """
    total_count = 0
    images_count = 0
    estimated_size_bytes = 0
    
    if db_manager.connected and db_manager.db is not None:
        try:
            collection = db_manager.db[db_manager.collection_name]
            
            # Get counts
            total_count = await collection.count_documents({})
            images_count = await collection.count_documents({
                "image_thumbnail_base64": {"$ne": None}
            })
            
            # Get collStats using db.command
            stats = await db_manager.db.command("collStats", db_manager.collection_name)
            estimated_size_bytes = stats.get("size", 0)
        except Exception as e:
            logger.error(f"Error retrieving storage stats from MongoDB: {e}", exc_info=True)
            # Fallback to local count if error
            total_count = len(local_history_buffer) + len(local_manual_uploads)
            images_count = sum(1 for item in (local_history_buffer + local_manual_uploads) 
                              if item.get("image_thumbnail_base64") is not None)
            estimated_size_bytes = total_count * 150000
    else:
        # Fallback to local counts when offline
        total_count = len(local_history_buffer) + len(local_manual_uploads)
        images_count = sum(1 for item in (local_history_buffer + local_manual_uploads) 
                          if item.get("image_thumbnail_base64") is not None)
        estimated_size_bytes = total_count * 150000
        
    return {
        "total_documents": total_count,
        "documents_with_images": images_count,
        "estimated_storage_bytes": estimated_size_bytes,
        "mongodb_connected": db_manager.connected
    }

@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    """Websocket connection channel to broadcast inspection ticks and stats updates."""
    await ws_manager.connect(websocket)
    try:
        # Instantly send current statuses and counters on connection
        await websocket.send_json({
            "event": "connected",
            "counters": analytics_tracker.get_summary(),
            "system_status": {
                "mongodb_connected": db_manager.connected,
                "mqtt_connected": mqtt_manager.connected,
                "inspection_running": inspection_running
            }
        })
        while True:
            # Keep connection open, read messages if client sends any controls
            data = await websocket.receive_text()
            # We can handle ping/pong if needed, or simple status requests
            msg = json.loads(data)
            if msg.get("action") == "get_status":
                await websocket.send_json({
                    "event": "status_update",
                    "counters": analytics_tracker.get_summary(),
                    "system_status": {
                        "mongodb_connected": db_manager.connected,
                        "mqtt_connected": mqtt_manager.connected,
                        "inspection_running": inspection_running
                    }
                })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)

# Cache-Control Middleware to disable static file caching in dev mode
@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Mount frontend files under /static
static_path = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_path, exist_ok=True)

# Serve index.html at root route
@app.get("/")
async def read_index():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(static_path, "index.html"))

app.mount("/static", StaticFiles(directory=static_path), name="static")

if __name__ == "__main__":
    import uvicorn
    # Print a beautiful, highlighted clickable localhost link in the console
    print("\n" + "="*60)
    print("🚀 Real-Time Metal Surface Inspection Dashboard Ready!")
    print("👉 Click to open: http://127.0.0.1:8080")
    print("="*60 + "\n")
    
    # Run uvicorn bound to 127.0.0.1 so it outputs a clickable localhost link
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
