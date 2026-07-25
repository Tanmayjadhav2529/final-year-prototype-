import os
import json
from dotenv import load_dotenv

load_dotenv(override=True)

DEFAULTS = {
    "mode": "live" if os.getenv("MOCK_MODE", "true").lower() != "true" else "mock",
    "camera_index": int(os.getenv("CAMERA_INDEX", "0")),
    "resolution": os.getenv("CAMERA_RESOLUTION", "640x480")
}

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")


def load_settings():
    # Try settings.json first, fall back to env defaults
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Merge with defaults
                out = DEFAULTS.copy()
                out.update({k: v for k, v in data.items() if v is not None})
                return out
    except Exception:
        pass
    return DEFAULTS.copy()


def save_settings(mode: str, camera_index: int, resolution: str):
    payload = {
        "mode": mode,
        "camera_index": int(camera_index),
        "resolution": resolution
    }
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return True
    except Exception:
        return False
