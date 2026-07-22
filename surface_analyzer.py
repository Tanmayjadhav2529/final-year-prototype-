import logging
import cv2
import numpy as np

logger = logging.getLogger("metal_inspection.surface_analyzer")

# --- Tunable thresholds ---
RUST_RATIO_THRESHOLD = 0.04      # fraction of frame in rust/oxidation color range

# HSV range covering typical rust/oxidation (orange-brown) coloration
_LOWER_RUST = np.array([5, 60, 40])
_UPPER_RUST = np.array([25, 255, 220])


def analyze_surface(frame_bgr: np.ndarray) -> list:
    """
    Classical computer-vision fallback for the one surface condition a COCO-trained
    object detector genuinely cannot see: rust/corrosion coloration. YOLO only ever
    reports zero detections on a texture-only photo (there's no "rust" object class),
    which the demo-mode classifier then reads as a clean PASS -- this catches that
    specific case via an HSV color threshold for orange/brown oxidation.

    SCOPE LIMITATION (deliberate, not an oversight): this module does NOT attempt to
    detect scratches, cracks, dents, or pinholes via generic edge-density or local
    texture-variance signals. An earlier version tried that and produced false
    positives on legitimate, intentionally textured/patterned metal surfaces --
    confirmed on photos of stacked steel pipes and a micro-perforated acoustic
    panel, both of which are visually "busy" (lots of edges, high local contrast)
    but are not defects. Generic edge/variance metrics cannot reliably separate
    "random damage" from "regular manufactured texture" (grilles, mesh, pipe
    bundles, brushed/polished highlights) -- an FFT-periodicity check and an
    autocorrelation-based regularity check were both tried and their score ranges
    overlapped too much across test images to set a safe threshold. Reliably
    detecting non-rust surface damage requires a properly trained model on labeled
    examples, not a heuristic.

    Returns a list of defect dicts using the same schema as classify_detections():
        [{"type": str, "confidence": float, "bbox": [x1, y1, x2, y2]}, ...]
    """
    if frame_bgr is None:
        return []

    h, w = frame_bgr.shape[:2]
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

    rust_mask = cv2.inRange(hsv, _LOWER_RUST, _UPPER_RUST)
    rust_ratio = cv2.countNonZero(rust_mask) / (h * w)

    logger.debug(f"Surface analysis signal -> rust_ratio={rust_ratio:.4f}")

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

    return defects
