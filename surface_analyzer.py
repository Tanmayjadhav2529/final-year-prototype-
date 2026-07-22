import logging
import cv2
import numpy as np

logger = logging.getLogger("metal_inspection.surface_analyzer")

# --- Tunable thresholds ---
RUST_RATIO_THRESHOLD = 0.04      # fraction of frame in rust/oxidation color range
EDGE_RATIO_THRESHOLD = 0.015     # fraction of frame that is a Canny edge pixel
HIGH_VAR_RATIO_THRESHOLD = 0.03  # fraction of frame with high local texture variance

# HSV range covering typical rust/oxidation (orange-brown) coloration
_LOWER_RUST = np.array([5, 60, 40])
_UPPER_RUST = np.array([25, 255, 220])


def analyze_surface(frame_bgr: np.ndarray) -> list:
    """
    Classical computer-vision heuristics that flag surface anomalies (rust/corrosion,
    heavy scratching/cracking) that a COCO-trained object detector has no way to see,
    since none of these are "objects" in its training set -- YOLO only ever reports
    zero detections on a texture photo, which the demo-mode classifier then reads as
    a clean PASS.

    This is intentionally a coarse, whole-frame heuristic meant to catch obviously
    damaged surfaces (e.g. manual photo uploads of rusted/scratched sheet). It is NOT
    a substitute for a properly custom-trained defect model: it won't precisely
    localize individual defects or reliably distinguish Scratch vs Crack vs Dent --
    it can only say "this looks like rust" or "this looks visually damaged" with a
    rough bounding region.

    Returns a list of defect dicts using the same schema as classify_detections():
        [{"type": str, "confidence": float, "bbox": [x1, y1, x2, y2]}, ...]
    """
    if frame_bgr is None:
        return []

    h, w = frame_bgr.shape[:2]
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

    # Signal 1: rust / corrosion coloration
    rust_mask = cv2.inRange(hsv, _LOWER_RUST, _UPPER_RUST)
    rust_ratio = cv2.countNonZero(rust_mask) / (h * w)

    # Signal 2: edge density (Canny)
    edges = cv2.Canny(gray, 40, 120)
    edge_ratio = cv2.countNonZero(edges) / (h * w)

    # Signal 3: local contrast / texture variance
    f32 = gray.astype(np.float32)
    mean = cv2.blur(f32, (15, 15))
    sqmean = cv2.blur(f32 ** 2, (15, 15))
    variance = np.clip(sqmean - mean ** 2, 0, None)
    std_map = np.sqrt(variance)
    high_var_ratio = float(np.mean(std_map > 18))

    logger.debug(
        f"Surface analysis signals -> rust_ratio={rust_ratio:.4f}, "
        f"edge_ratio={edge_ratio:.4f}, high_var_ratio={high_var_ratio:.4f}"
    )

    defects = []

    if rust_ratio > RUST_RATIO_THRESHOLD:
        ys, xs = np.where(rust_mask > 0)
        bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else [0, 0, w - 1, h - 1]
        confidence = round(min(0.97, 0.55 + rust_ratio * 0.5), 4)
        defects.append({
            "type": "Rust/Corrosion (Surface Analysis)",
            "confidence": confidence,
            "bbox": bbox
        })
    elif edge_ratio > EDGE_RATIO_THRESHOLD or high_var_ratio > HIGH_VAR_RATIO_THRESHOLD:
        ys, xs = np.where(edges > 0)
        bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else [0, 0, w - 1, h - 1]
        confidence = round(min(0.9, 0.4 + max(edge_ratio, high_var_ratio)), 4)
        defects.append({
            "type": "Scratch/Crack (Surface Analysis)",
            "confidence": confidence,
            "bbox": bbox
        })

    return defects
