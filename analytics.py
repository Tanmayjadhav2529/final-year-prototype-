import logging
from datetime import datetime

logger = logging.getLogger("metal_inspection.analytics")

class AnalyticsTracker:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.defect_counts = {
            "Scratch": 0,
            "Dent": 0,
            "Crack": 0,
            "Pinhole": 0,
            "Unknown": 0
        }

    def update(self, status: str, defects: list):
        """Update in-memory counters with a new inspection result."""
        self.total += 1
        if status == "PASS":
            self.passed += 1
        else:
            self.failed += 1
            
        for defect in defects:
            dtype = defect.get("type", "")
            matched = False
            for key in self.defect_counts.keys():
                if key in dtype:
                    self.defect_counts[key] += 1
                    matched = True
                    break
            if not matched:
                self.defect_counts["Unknown"] += 1

    def get_summary(self) -> dict:
        """Returns the in-memory statistics summary."""
        defect_rate = (self.failed / self.total * 100) if self.total > 0 else 0.0
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "defect_rate": round(defect_rate, 2),
            "defect_counts": self.defect_counts
        }

    def reset(self):
        """Resets all in-memory stats."""
        self.total = 0
        self.passed = 0
        self.failed = 0
        for key in self.defect_counts:
            self.defect_counts[key] = 0

analytics_tracker = AnalyticsTracker()

async def get_db_summary(db_manager, source: str = "live_camera") -> dict:
    """
    Attempts to compile inspection stats from MongoDB database records.
    Falls back to current in-memory counters if MongoDB is unavailable.
    """
    if not db_manager.connected or db_manager.db is None:
        logger.debug("Database offline. Returning in-memory analytics summary.")
        return analytics_tracker.get_summary()
        
    try:
        collection = db_manager.db[db_manager.collection_name]
        
        # Build match stage based on source parameter
        if source == "live_camera":
            match_filter = {"$or": [{"source": "live_camera"}, {"source": {"$exists": False}}]}
        else:
            match_filter = {"source": source}

        # Aggregation pipeline to get counts and defects in a single pass
        pipeline = [
            {"$match": match_filter},
            {
                "$facet": {
                    "totals": [
                        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
                    ],
                    "defects": [
                        {"$unwind": "$defects"},
                        {"$group": {"_id": "$defects.type", "count": {"$sum": 1}}}
                    ]
                }
            }
        ]
        
        cursor = collection.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        if not result:
            return analytics_tracker.get_summary()
            
        data = result[0]
        total = 0
        passed = 0
        failed = 0
        for item in data.get("totals", []):
            count = item["count"]
            total += count
            if item["_id"] == "PASS":
                passed = count
            elif item["_id"] == "FAIL":
                failed = count
                
        defect_counts = {
            "Scratch": 0,
            "Dent": 0,
            "Crack": 0,
            "Pinhole": 0,
            "Unknown": 0
        }
        
        for item in data.get("defects", []):
            dtype = item["_id"]
            count = item["count"]
            matched = False
            for key in defect_counts.keys():
                if key in dtype:
                    defect_counts[key] += count
                    matched = True
                    break
            if not matched:
                defect_counts["Unknown"] += count
                
        defect_rate = (failed / total * 100) if total > 0 else 0.0
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "defect_rate": round(defect_rate, 2),
            "defect_counts": defect_counts
        }
    except Exception as e:
        logger.error(f"Failed to aggregate database stats: {e}. Falling back to in-memory stats.")
        return analytics_tracker.get_summary()
