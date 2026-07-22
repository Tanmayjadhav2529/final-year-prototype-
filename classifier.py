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
        cls_name = det.get("class_name", "").lower()
        if cls_name in privacy_classes:
            person_detections.append(det)
        else:
            object_detections.append(det)
            
    person_boxes = [det["bbox"] for det in person_detections]
    
    if not object_detections:
        return "PASS", [], person_boxes

    mapped_defects = []
    for det in object_detections:
        cls_name = det.get("class_name", "").lower()
        cls_id = det.get("class_id", 0)
        
        # Systematic mapping of common COCO items to defect types for demo clarity
        if any(item in cls_name for item in ["person", "hand", "face", "finger"]):
            defect_type = "Scratch"
        elif any(item in cls_name for item in ["cup", "bottle", "bowl", "can", "mug"]):
            defect_type = "Dent"
        elif any(item in cls_name for item in ["phone", "laptop", "remote", "keyboard"]):
            defect_type = "Crack"
        elif any(item in cls_name for item in ["pen", "scissors", "tie", "fork", "knife"]):
            defect_type = "Pinhole"
        else:
            # Modulo fallback mapping based on class index
            defect_type = DEFECT_TYPES[cls_id % len(DEFECT_TYPES)]
            
        mapped_defects.append({
            "type": f"{defect_type} (Demo: {det['class_name']})",
            "confidence": round(det["confidence"], 4),
            "bbox": det["bbox"]
        })

    logger.debug(f"Classified detections. Status: FAIL, Defects: {mapped_defects}")
    return "FAIL", mapped_defects, person_boxes


def classify_frame(detections: list, frame) -> tuple:
    """
    Coordinating function that runs classify_detections first.
    If the result is PASS and frame is not None, runs analyze_surface
    as a texture analysis fallback path.
    """
    status, defects, person_boxes = classify_detections(detections)
    if status == "PASS" and frame is not None:
        from surface_analyzer import analyze_surface
        surface_defects = analyze_surface(frame)
        if surface_defects:
            logger.info("YOLO detected PASS, but classical CV surface fallback detected defects.")
            return "FAIL", surface_defects, person_boxes
            
    return status, defects, person_boxes
