import unittest
import numpy as np
import os
import sys

# Add project path to import modules
sys.path.append(os.path.dirname(__file__))

from classifier import classify_detections
from analytics import AnalyticsTracker
from preprocess import preprocess_frame
from capture import image_acquisition

class TestMetalInspectionUnits(unittest.TestCase):

    def test_classifier_good_product(self):
        """Verify that empty YOLO detections classify as PASS / GOOD."""
        status, defects, person_boxes = classify_detections([])
        self.assertEqual(status, "PASS")
        self.assertEqual(defects, [])
        self.assertEqual(person_boxes, [])

    def test_classifier_defect_dent(self):
        """Verify that a heuristic Dent object is mapped directly to a Dent defect and FAIL status."""
        raw_detections = [
            {"class_name": "Dent", "confidence": 0.88, "bbox": [50, 60, 200, 220]}
        ]
        status, defects, person_boxes = classify_detections(raw_detections)
        self.assertEqual(status, "FAIL")
        self.assertEqual(len(defects), 1)
        self.assertEqual(defects[0]["type"], "Dent")
        self.assertEqual(defects[0]["confidence"], 0.88)
        self.assertEqual(defects[0]["bbox"], [50, 60, 200, 220])
        self.assertEqual(person_boxes, [])

    def test_classifier_privacy_person(self):
        """Verify that a COCO person object maps to privacy blur box instead of a defect."""
        raw_detections = [
            {"class_name": "person", "class_id": 0, "confidence": 0.95, "bbox": [10, 10, 100, 400]}
        ]
        status, defects, person_boxes = classify_detections(raw_detections)
        self.assertEqual(status, "PASS")
        self.assertEqual(defects, [])
        self.assertEqual(len(person_boxes), 1)
        self.assertEqual(person_boxes[0], [10, 10, 100, 400])

    def test_analytics_tracker_accumulation(self):
        """Verify that the in-memory analytics tracker updates counts and defect rates correctly."""
        tracker = AnalyticsTracker()
        self.assertEqual(tracker.total, 0)
        
        # Update with a PASS
        tracker.update("PASS", [])
        self.assertEqual(tracker.total, 1)
        self.assertEqual(tracker.passed, 1)
        self.assertEqual(tracker.failed, 0)
        self.assertEqual(tracker.get_summary()["defect_rate"], 0.0)

        # Update with a FAIL
        defects = [{"type": "Dent", "confidence": 0.8, "bbox": [0,0,10,10]}]
        tracker.update("FAIL", defects)
        self.assertEqual(tracker.total, 2)
        self.assertEqual(tracker.passed, 1)
        self.assertEqual(tracker.failed, 1)
        self.assertEqual(tracker.get_summary()["defect_rate"], 50.0)
        self.assertEqual(tracker.defect_counts["Dent"], 1)

    def test_preprocess_resize(self):
        """Verify that preprocessing standardizes frame dimensions correctly."""
        dummy_frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
        processed = preprocess_frame(dummy_frame, target_size=(640, 480))
        self.assertIsNotNone(processed)
        self.assertEqual(processed.shape, (480, 640, 3))

    def test_synthetic_frame_generation(self):
        """Verify that synthetic frame generator creates valid metal surface textures."""
        frame = image_acquisition._generate_synthetic_frame()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.shape, (480, 640, 3))
        self.assertEqual(frame.dtype, np.uint8)

if __name__ == "__main__":
    unittest.main()
