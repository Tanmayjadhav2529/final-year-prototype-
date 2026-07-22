import os
import logging
from ultralytics import YOLO

logger = logging.getLogger("metal_inspection.detector")

class DefectDetector:
    def __init__(self):
        self.model_path = os.getenv("MODEL_PATH", "yolov8n.pt")
        self.conf_threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.25"))
        self.model = None

    def load_model(self):
        """Loads the YOLO model into memory. Triggers download if missing."""
        if self.model is None:
            try:
                logger.info(f"Loading YOLO model from '{self.model_path}'...")
                # This will automatically download weights (e.g. yolov8n.pt) if not found.
                self.model = YOLO(self.model_path)
                logger.info("YOLO model loaded successfully.")
            except Exception as e:
                logger.error(f"Error loading YOLO model: {e}")
                raise e

    def detect(self, frame) -> list:
        """Runs YOLO inference on a frame and extracts bounding box results."""
        self.load_model()
        if self.model is None:
            return []
            
        try:
            # Run prediction; verbose=False prevents console flooding
            results = self.model(frame, conf=self.conf_threshold, verbose=False)
            detections = []
            
            if not results:
                return detections
                
            result = results[0]
            for box in result.boxes:
                # Extract coordinates
                xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = self.model.names[cls_id]
                
                detections.append({
                    "bbox": [int(x) for x in xyxy],
                    "confidence": conf,
                    "class_id": cls_id,
                    "class_name": cls_name
                })
            return detections
        except Exception as e:
            logger.error(f"Error running inference: {e}")
            return []

    def is_privacy_class(self, class_name) -> bool:
        """Helper to check if a class is flagged for privacy blurring."""
        privacy_classes = [c.strip().lower() for c in os.getenv("PRIVACY_BLUR_CLASSES", "person").split(",")]
        return class_name.lower() in privacy_classes

defect_detector = DefectDetector()
