import os
import sys
import cv2
import numpy as np
import logging
import glob

logger = logging.getLogger("metal_inspection.capture")

class ImageAcquisition:
    def __init__(self):
        self.camera_index = int(os.getenv("CAMERA_INDEX", "0"))
        self.mock_mode = os.getenv("MOCK_MODE", "true").lower() == "true"
        logger.info(f"MOCK_MODE resolved to: {self.mock_mode}")
        self.cap = None

    def init_capture(self):
        """Initialize connection to webcam or prepare synthetic fallback."""
        if not self.mock_mode:
            try:
                logger.info(f"Attempting to open camera index {self.camera_index}...")
                # On Windows, explicitly request DirectShow instead of letting OpenCV
                # auto-select a backend (default MSMF can hang or fail to open reliably).
                if sys.platform.startswith("win"):
                    self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                else:
                    self.cap = cv2.VideoCapture(self.camera_index)
                # Check if open succeeded
                if not self.cap.isOpened():
                    logger.warning("Physical webcam could not be opened. Falling back to MOCK MODE.")
                    self.mock_mode = True
                else:
                    logger.info("Physical webcam opened successfully.")
            except Exception as e:
                logger.warning(f"Webcam initialization error: {e}. Falling back to MOCK MODE.")
                self.mock_mode = True

    def capture_frame(self) -> np.ndarray:
        """Captures a frame from webcam or retrieves a mock image."""
        if not self.mock_mode:
            if self.cap is None or not self.cap.isOpened():
                self.init_capture()
            
            if self.cap is not None and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    return frame
                else:
                    logger.warning("Failed to grab frame from physical webcam. Releasing and retrying...")
                    self.cap.release()
                    self.cap = None

        # Fallback / synthetic mode when no webcam is available.
        return self._generate_synthetic_frame()

    def _generate_synthetic_frame(self) -> np.ndarray:
        """Generates a synthetic metal surface frame with random textures and optional defect simulation."""
        # 640x480 gray image simulating a metal sheet
        frame = np.ones((480, 640, 3), dtype=np.uint8) * 170
        
        # Add a brushed texture (fine horizontal streaks)
        noise = np.random.randint(-15, 15, size=(480, 640, 3))
        frame = np.clip(frame + noise, 0, 255).astype(np.uint8)
        
        # Smooth horizontally to make it look brushed
        kernel = np.zeros((1, 15))
        kernel[0, :] = 1.0 / 15.0
        frame = cv2.filter2D(frame, -1, kernel)

        # Randomly draw a defect-like shape on 40% of frames
        if np.random.rand() < 0.4:
            defect_type = np.random.choice(["scratch", "dent", "crack", "pinhole"])
            # Draw something that YOLO can pick up (e.g. distinct shape/contrast)
            if defect_type == "scratch":
                x1, y1 = np.random.randint(50, 200), np.random.randint(50, 400)
                x2, y2 = np.random.randint(400, 600), np.random.randint(50, 400)
                cv2.line(frame, (x1, y1), (x2, y2), (40, 40, 40), thickness=3)
            elif defect_type == "dent":
                cx, cy = np.random.randint(150, 500), np.random.randint(100, 380)
                cv2.circle(frame, (cx, cy), 35, (100, 100, 100), thickness=-1)
                cv2.circle(frame, (cx-4, cy-4), 30, (140, 140, 140), thickness=-1)
            elif defect_type == "crack":
                # Jagged line
                x, y = np.random.randint(100, 300), np.random.randint(100, 300)
                for _ in range(5):
                    nx, ny = x + np.random.randint(20, 50), y + np.random.randint(-20, 20)
                    cv2.line(frame, (x, y), (nx, ny), (10, 10, 10), thickness=2)
                    x, y = nx, ny
            elif defect_type == "pinhole":
                cx, cy = np.random.randint(100, 540), np.random.randint(100, 380)
                cv2.circle(frame, (cx, cy), 8, (20, 20, 20), thickness=-1)
                
        return frame

    def release(self):
        """Releases the camera client resource."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            logger.info("Physical webcam released.")

image_acquisition = ImageAcquisition()
