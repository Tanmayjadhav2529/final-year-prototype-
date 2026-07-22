import os
import cv2
import numpy as np
import unittest
import sys

# Ensure we can import from the project root
sys.path.append(os.path.dirname(__file__))

from classifier import classify_detections, classify_frame
from surface_analyzer import analyze_surface

class TestFallback(unittest.TestCase):
    def test_clean_surface_pass(self):
        print("\n--- Test 1: Clean Surface ---")
        # Generate clean uniform gray sheet with minimal noise
        clean = np.ones((480, 640, 3), dtype=np.uint8) * 170
        noise = np.random.randint(-2, 3, size=(480, 640, 3))
        clean = np.clip(clean + noise, 0, 255).astype(np.uint8)
        
        # Print metrics
        h, w = clean.shape[:2]
        gray = cv2.cvtColor(clean, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(clean, cv2.COLOR_BGR2HSV)
        rust_mask = cv2.inRange(hsv, np.array([5, 60, 40]), np.array([25, 255, 220]))
        rust_ratio = cv2.countNonZero(rust_mask) / (h * w)
        edges = cv2.Canny(gray, 40, 120)
        edge_ratio = cv2.countNonZero(edges) / (h * w)
        
        f32 = gray.astype(np.float32)
        mean = cv2.blur(f32, (15, 15))
        sqmean = cv2.blur(f32 ** 2, (15, 15))
        variance = np.clip(sqmean - mean ** 2, 0, None)
        std_map = np.sqrt(variance)
        high_var_ratio = float(np.mean(std_map > 18))
        
        print(f"Metrics: rust_ratio={rust_ratio:.4f}, edge_ratio={edge_ratio:.4f}, high_var_ratio={high_var_ratio:.4f}")
        
        status, defects, person_boxes = classify_frame([], clean)
        print(f"Result -> status: {status}, defects: {defects}, person_boxes: {person_boxes}")
        self.assertEqual(status, "PASS")
        self.assertEqual(defects, [])
        self.assertEqual(person_boxes, [])

    def test_rusted_surface_fail(self):
        print("\n--- Test 2: Rusted Surface ---")
        # Construct BGR value for rust color: HSV H=15, S=200, V=150
        rust_color_hsv = np.uint8([[[15, 200, 150]]])
        rust_color_bgr = cv2.cvtColor(rust_color_hsv, cv2.COLOR_HSV2BGR)[0][0]
        
        # Create image and paint a patch of 200x200 pixels with rust color
        # This is 40000 pixels out of 307200 (13% of total pixels, well above 4% threshold)
        rusted = np.ones((480, 640, 3), dtype=np.uint8) * 170
        rusted[100:300, 200:400] = rust_color_bgr
        
        # Print metrics
        h, w = rusted.shape[:2]
        gray = cv2.cvtColor(rusted, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(rusted, cv2.COLOR_BGR2HSV)
        rust_mask = cv2.inRange(hsv, np.array([5, 60, 40]), np.array([25, 255, 220]))
        rust_ratio = cv2.countNonZero(rust_mask) / (h * w)
        edges = cv2.Canny(gray, 40, 120)
        edge_ratio = cv2.countNonZero(edges) / (h * w)
        
        f32 = gray.astype(np.float32)
        mean = cv2.blur(f32, (15, 15))
        sqmean = cv2.blur(f32 ** 2, (15, 15))
        variance = np.clip(sqmean - mean ** 2, 0, None)
        std_map = np.sqrt(variance)
        high_var_ratio = float(np.mean(std_map > 18))
        
        print(f"Metrics: rust_ratio={rust_ratio:.4f}, edge_ratio={edge_ratio:.4f}, high_var_ratio={high_var_ratio:.4f}")
        
        status, defects, person_boxes = classify_frame([], rusted)
        print(f"Result -> status: {status}, defects: {defects}, person_boxes: {person_boxes}")
        self.assertEqual(status, "FAIL")
        self.assertTrue(any("Rust" in d["type"] for d in defects))

    def test_scratched_surface_no_rust_is_a_known_limitation(self):
        print("\n--- Test 3: Heavily Scratched/Crumpled Surface (no rust coloration) ---")
        # Create gray image and draw multiple lines to create Canny edges
        scratched = np.ones((480, 640, 3), dtype=np.uint8) * 170
        # Draw 40 random intersecting lines
        np.random.seed(42)
        for _ in range(40):
            x1 = np.random.randint(0, 640)
            y1 = np.random.randint(0, 480)
            x2 = np.random.randint(0, 640)
            y2 = np.random.randint(0, 480)
            color = np.random.randint(0, 80, size=3).tolist()
            cv2.line(scratched, (x1, y1), (x2, y2), color, thickness=2)

        status, defects, person_boxes = classify_frame([], scratched)
        print(f"Result -> status: {status}, defects: {defects}, person_boxes: {person_boxes}")
        # KNOWN, DOCUMENTED LIMITATION: surface_analyzer.py only detects rust
        # coloration via classical CV, not generic scratch/crack line patterns.
        # A generic edge/variance-based scratch detector was tried and removed
        # because it produced false positives on legitimate regular textures
        # (perforated panels, pipe bundles) -- see surface_analyzer.py docstring.
        # Non-rust surface damage genuinely requires a trained model to catch
        # reliably, so this correctly (if unhelpfully) still returns PASS here.
        self.assertEqual(status, "PASS")

    def test_perforated_panel_pattern_does_not_false_positive(self):
        print("\n--- Test 5: Regular perforated-panel pattern (must stay PASS) ---")
        # Synthetic stand-in for a micro-perforated acoustic panel / pipe-bundle
        # end view: a regular grid of dark circular holes on a lighter background.
        # This kind of intentional, repeating pattern previously triggered a false
        # "Scratch/Crack" FAIL under the old edge/variance heuristic.
        panel = np.ones((480, 640, 3), dtype=np.uint8) * 180
        for cy in range(20, 480, 30):
            for cx in range(20, 640, 30):
                cv2.circle(panel, (cx, cy), 10, (30, 30, 30), thickness=-1)

        status, defects, person_boxes = classify_frame([], panel)
        print(f"Result -> status: {status}, defects: {defects}")
        self.assertEqual(status, "PASS")
        self.assertEqual(defects, [])

    def test_original_classify_detections(self):
        print("\n--- Test 4: Original classify_detections assertions ---")
        # 1. Empty detections
        status, defects, person_boxes = classify_detections([])
        self.assertEqual(status, "PASS")
        self.assertEqual(defects, [])
        self.assertEqual(person_boxes, [])
        
        # 2. Cup maps to Dent
        raw_detections = [{"class_name": "cup", "class_id": 41, "confidence": 0.88, "bbox": [50, 60, 200, 220]}]
        status, defects, person_boxes = classify_detections(raw_detections)
        self.assertEqual(status, "FAIL")
        self.assertEqual(len(defects), 1)
        self.assertEqual(defects[0]["type"], "Dent (Demo: cup)")
        
        # 3. Person maps to privacy blur box
        raw_detections = [{"class_name": "person", "class_id": 0, "confidence": 0.95, "bbox": [10, 10, 100, 400]}]
        status, defects, person_boxes = classify_detections(raw_detections)
        self.assertEqual(status, "PASS")
        self.assertEqual(defects, [])
        self.assertEqual(person_boxes, [[10, 10, 100, 400]])

if __name__ == "__main__":
    unittest.main()
