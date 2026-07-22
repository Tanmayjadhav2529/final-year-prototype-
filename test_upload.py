import sys
import os
import time
import subprocess
import requests
import io
from PIL import Image

def create_dummy_image():
    # Create a simple red 100x100 square image
    img = Image.new('RGB', (100, 100), color='red')
    byte_arr = io.BytesIO()
    img.save(byte_arr, format='JPEG')
    byte_arr.seek(0)
    return byte_arr

def main():
    print("=== Start On-Demand Image Upload Integration Testing ===")
    
    server_port = 8080
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", str(server_port)],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to startup
    time.sleep(3)
    
    try:
        # Check upload endpoint
        print("Uploading dummy image for inspection...")
        files = {'file': ('dummy.jpg', create_dummy_image(), 'image/jpeg')}
        r = requests.post(f"http://127.0.0.1:{server_port}/inspection/upload", files=files)
        
        print(f"Status Code: {r.status_code}")
        payload = r.json()
        print(f"Response Payload keys: {list(payload.keys())}")
        
        # Verify schema
        assert r.status_code == 200, "Upload endpoint failed"
        assert payload["status"] in ["PASS", "FAIL"], "Status must be PASS or FAIL"
        assert "image_base64" in payload, "Missing overlay image base64"
        assert payload["source"] == "manual_upload", "Source must be tagged manual_upload"
        print("Upload endpoint PASSED.")
        
        # Check manual history
        print("\nChecking manual uploads history logs...")
        r_hist = requests.get(f"http://127.0.0.1:{server_port}/history?source=manual_upload")
        hist_data = r_hist.json()
        print(f"History records found: {len(hist_data)}")
        assert r_hist.status_code == 200, "History query failed"
        assert len(hist_data) >= 1, "Uploaded record not found in manual history"
        assert hist_data[0]["source"] == "manual_upload", "Incorrect source tag in history logs"
        print("Manual history logs filter PASSED.")
        
        # Check manual analytics summary
        print("\nChecking manual uploads analytics summary...")
        r_anal = requests.get(f"http://127.0.0.1:{server_port}/analytics/summary?source=manual_upload")
        anal_data = r_anal.json()
        print(f"Analytics summary payload: {anal_data}")
        assert r_anal.status_code == 200, "Analytics summary query failed"
        assert int(anal_data["total"]) >= 1, "Manual uploads total count mismatch"
        print("Manual analytics summary PASSED.")
        
        print("\n=== All Image Upload Integration Tests Passed! ===")
        
    except Exception as e:
        print(f"\n❌ Integration Test FAILED: {e}")
        sys.exit(1)
    finally:
        print("Terminating server...")
        server_process.terminate()
        server_process.wait()
        print("Server terminated.")

if __name__ == "__main__":
    main()
