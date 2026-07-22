import os
import cv2
import numpy as np
import logging

logger = logging.getLogger("metal_inspection.heuristic_detector")

def detect_defects_heuristic(frame) -> list:
    """
    Analyzes pixel data of a frame using classical Computer Vision algorithms
    to detect scratches, dents, cracks, and pinholes.
    
    Returns:
        list of dict: [{"class_name": ..., "confidence": ..., "bbox": [x1, y1, x2, y2]}]
    """
    if frame is None:
        return []

    # Get configuration parameters from environment with safe fallbacks
    canny_low = int(os.getenv("CANNY_THRESH_LOW", "50"))
    canny_high = int(os.getenv("CANNY_THRESH_HIGH", "150"))
    hough_thresh = int(os.getenv("HOUGH_THRESH", "35"))
    hough_min_len = int(os.getenv("HOUGH_MIN_LINE_LEN", "30"))
    hough_max_gap = int(os.getenv("HOUGH_MAX_LINE_GAP", "5"))
    
    crack_min_len = int(os.getenv("CRACK_MIN_LEN", "40"))
    scratch_min_len = int(os.getenv("SCRATCH_MIN_LEN", "15"))
    scratch_max_len = int(os.getenv("SCRATCH_MAX_LEN", "150"))
    
    pinhole_thresh = int(os.getenv("PINHOLE_THRESH", "70"))
    blob_min_area = int(os.getenv("BLOB_MIN_AREA", "5"))
    blob_max_area = int(os.getenv("BLOB_MAX_AREA", "120"))
    pinhole_min_circ = float(os.getenv("PINHOLE_MIN_CIRCULARITY", "0.65"))
    
    dent_dog_thresh = int(os.getenv("DENT_DOG_THRESH", "12"))
    dent_min_area = int(os.getenv("DENT_MIN_AREA", "120"))
    dent_max_area = int(os.getenv("DENT_MAX_AREA", "3000"))
    dent_max_edge_ratio = float(os.getenv("DENT_MAX_EDGE_RATIO", "0.03"))

    # Convert frame to grayscale
    if len(frame.shape) == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame.copy()

    detections = []
    crack_boxes = []

    # 1. Edge & Line Analysis (Scratches & Cracks)
    edges = cv2.Canny(gray, canny_low, canny_high)
    
    # Hough Line Transform for Cracks
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=hough_thresh, 
                           minLineLength=hough_min_len, maxLineGap=hough_max_gap)
    
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            if length >= crack_min_len:
                bbox = [int(min(x1, x2)), int(min(y1, y2)), int(max(x1, x2)), int(max(y1, y2))]
                detections.append({
                    "class_name": "Crack",
                    "confidence": float(round(min(0.95, length / 150.0), 4)),
                    "bbox": bbox
                })
                crack_boxes.append(bbox)

    # Contours analysis on Canny edges for Scratches
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        perimeter = cv2.arcLength(contour, False)
        if scratch_min_len <= perimeter <= scratch_max_len:
            x, y, w, h = cv2.boundingRect(contour)
            bbox = [int(x), int(y), int(x + w), int(y + h)]
            
            # Verify if this contour overlaps significantly with a crack detection
            overlap = False
            for cb in crack_boxes:
                if not (bbox[2] < cb[0] or bbox[0] > cb[2] or bbox[3] < cb[1] or bbox[1] > cb[3]):
                    overlap = True
                    break
            
            if not overlap:
                detections.append({
                    "class_name": "Scratch",
                    "confidence": float(round(min(0.90, perimeter / 100.0), 4)),
                    "bbox": bbox
                })

    # 2. Thresholding / Dark Circular Blob analysis (Pinholes)
    _, thresh = cv2.threshold(gray, pinhole_thresh, 255, cv2.THRESH_BINARY_INV)
    pinhole_contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in pinhole_contours:
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        if blob_min_area <= area <= blob_max_area and perimeter > 0:
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            if circularity >= pinhole_min_circ:
                x, y, w, h = cv2.boundingRect(contour)
                detections.append({
                    "class_name": "Pinhole",
                    "confidence": float(round(min(0.95, circularity), 4)),
                    "bbox": [int(x), int(y), int(x + w), int(y + h)]
                })

    # 3. Difference of Gaussians Shading Gradient Analysis (Dents)
    dog = cv2.absdiff(cv2.GaussianBlur(gray, (5, 5), 0), cv2.GaussianBlur(gray, (21, 21), 0))
    _, dog_thresh = cv2.threshold(dog, dent_dog_thresh, 255, cv2.THRESH_BINARY)
    dent_contours, _ = cv2.findContours(dog_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in dent_contours:
        area = cv2.contourArea(contour)
        if dent_min_area <= area <= dent_max_area:
            x, y, w, h = cv2.boundingRect(contour)
            
            # Retrieve Canny edge response inside the region to screen out cracks/scratches
            roi_edges = edges[y:y+h, x:x+w]
            num_edge_pixels = np.sum(roi_edges > 0)
            edge_ratio = num_edge_pixels / (w * h) if (w * h) > 0 else 1.0
            
            if edge_ratio < dent_max_edge_ratio:
                detections.append({
                    "class_name": "Dent",
                    "confidence": float(round(min(0.95, area / dent_max_area), 4)),
                    "bbox": [int(x), int(y), int(x + w), int(y + h)]
                })

    logger.debug(f"Heuristic detections found: {len(detections)}")
    return detections
