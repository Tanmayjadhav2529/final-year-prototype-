import sys
import os
import time
import subprocess
import requests
import io
from PIL import Image
import pillow_avif

def create_avif_image():
    img = Image.new('RGB', (100, 100), color='blue')
    byte_arr = io.BytesIO()
    img.save(byte_arr, format='AVIF')
    byte_arr.seek(0)
    return byte_arr

def main():
    print("=== Start AVIF Image Upload & Format Failure Integration Testing ===")
    
    server_port = 8080
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", str(server_port)],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server startup
    time.sleep(3)
    
    try:
        # 1. Test uploading a valid AVIF image
        print("Uploading a valid AVIF image...")
        files = {'file': ('test.avif', create_avif_image(), 'image/avif')}
        r = requests.post(f"http://127.0.0.1:{server_port}/inspection/upload", files=files)
        
        print(f"AVIF Response Code: {r.status_code}")
        payload = r.json()
        print(f"AVIF Response keys: {list(payload.keys())}")
        
        assert r.status_code == 200, "AVIF upload failed"
        assert payload["status"] in ["PASS", "FAIL"], "Status must be PASS or FAIL"
        assert "image_base64" in payload, "Missing base64 image representation"
        print("AVIF upload check PASSED.")
        
        # 2. Test uploading an unsupported format
        print("\nUploading an unsupported file format (.XYZ)...")
        files_bad = {'file': ('test.xyz', io.BytesIO(b"corrupted_data"), 'image/xyz')}
        r_bad = requests.post(f"http://127.0.0.1:{server_port}/inspection/upload", files=files_bad)
        
        print(f"Unsupported Response Code: {r_bad.status_code}")
        payload_bad = r_bad.json()
        print(f"Unsupported Response message: {payload_bad}")
        
        assert r_bad.status_code == 400, "Bad format check failed to return 400"
        expected_msg = "Unsupported or corrupted image format: .XYZ. Supported: JPG, PNG, WEBP, AVIF, BMP, TIFF."
        assert payload_bad["message"] == expected_msg, "Incorrect error message returned"
        print("Unsupported format error message check PASSED.")
        
        print("\n=== All AVIF & Format Failure Integration Tests Passed! ===")
        
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
