import logging

logger = logging.getLogger("metal_inspection.classifier")

# Standard defect categories
DEFECT_TYPES = ["Scratch", "Dent", "Crack", "Pinhole"]

def classify_detections(detections: list) -> tuple:
    """
    Analyzes raw YOLO object detections and classifies the product as PASS or FAIL.
    
    DEMO MODE RULE:
    - If any object is detected above the confidence threshold, the product status 
      is classified as "FAIL" (BAD), and the detected object is mapped to a simulated
      defect type (Scratch, Dent, Crack, Pinhole) based on its class.
    - If no objects are detected, the status is "PASS" (GOOD).
    
    Returns:
        tuple: (status: "PASS" | "FAIL", defects: list, person_boxes: list)
        defects schema: [{"type": "...", "confidence": 0.0, "bbox": [x1, y1, x2, y2]}]
        person_boxes schema: [[x1, y1, x2, y2], ...]
    """
    import os
    privacy_classes = [c.strip().lower() for c in os.getenv("PRIVACY_BLUR_CLASSES", "person").split(",")]
    
    person_detections = []
    object_detections = []
    
    for det in detections:
        cls_name = det.get("class_name", "")
        # Check if it's a privacy class
        if cls_name.lower() in privacy_classes:
            person_detections.append(det)
        # Check if it is a valid defect category from the heuristic detector
        elif cls_name in DEFECT_TYPES:
            object_detections.append(det)
            
    person_boxes = [det["bbox"] for det in person_detections]
    
    if not object_detections:
        return "PASS", [], person_boxes

    mapped_defects = []
    for det in object_detections:
        mapped_defects.append({
            "type": det["class_name"],
            "confidence": round(det["confidence"], 4),
            "bbox": det["bbox"]
        })

    logger.debug(f"Classified detections. Status: FAIL, Defects: {mapped_defects}")
    return "FAIL", mapped_defects, person_boxes
