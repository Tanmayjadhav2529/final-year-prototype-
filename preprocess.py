import cv2
import numpy as np

def preprocess_frame(frame: np.ndarray, target_size=(640, 480)) -> np.ndarray:
    """
    Preprocess the frame for YOLO inference and dashboard display.
    Resizes the image to a standardized target size.
    """
    if frame is None:
        return None
        
    # Resize frame
    resized = cv2.resize(frame, target_size)
    
    # We can also add minor contrast enhancement (CLAHE) to help make surface details clearer
    # but we will keep standard color structure so that YOLO is not negatively impacted.
    return resized
