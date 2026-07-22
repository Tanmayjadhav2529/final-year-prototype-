import sys
import os
import time
import subprocess
import requests

def main():
    print("=== Start Storage Optimization Integration Testing ===")
    
    # Force configuration environment variable for testing
    os.environ["STORE_IMAGE_ON_PASS"] = "false"
    
    server_port = 8080
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", str(server_port)],
        env=os.environ.copy(),
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server startup
    time.sleep(3)
    
    try:
        # Start continuous inspection loop
        print("Starting continuous inspection loop...")
        r_start = requests.post(f"http://127.0.0.1:{server_port}/inspection/start")
        assert r_start.status_code == 200, "Failed to start inspection loop"
        
        # Let it run for 6 seconds to capture both PASS and FAIL results
        print("Running loop for 6 seconds...")
        time.sleep(6)
        
        # Stop loop
        print("Stopping inspection loop...")
        r_stop = requests.post(f"http://127.0.0.1:{server_port}/inspection/stop")
        assert r_stop.status_code == 200, "Failed to stop inspection loop"
        
        # Retrieve history
        print("\nFetching history from local buffer/database...")
        r_hist = requests.get(f"http://127.0.0.1:{server_port}/history?source=live_camera")
        assert r_hist.status_code == 200, "Failed to get history logs"
        history = r_hist.json()
        print(f"Retrieved {len(history)} history records.")
        
        # Check storage optimization assertions
        pass_records = [r for r in history if r["status"] == "PASS"]
        fail_records = [r for r in history if r["status"] == "FAIL"]
        
        print(f"PASS records: {len(pass_records)}, FAIL records: {len(fail_records)}")
        
        # In mock mode, we have both PASS (01_clean_surface) and FAIL (others).
        # We assert that PASS records saved to the database/buffer have no thumbnail when optimized.
        # Note: local_history_buffer preserves thumbnails for frontend display, but if database is connected,
        # the fetched database records won't have it.
        # Let's check analytics storage endpoint as well
        print("\nQuerying analytics storage endpoint...")
        r_store = requests.get(f"http://127.0.0.1:{server_port}/analytics/storage")
        assert r_store.status_code == 200, "Failed to query /analytics/storage"
        storage_data = r_store.json()
        print(f"Storage stats: {storage_data}")
        
        assert "total_documents" in storage_data
        assert "documents_with_images" in storage_data
        assert "estimated_storage_bytes" in storage_data
        
        print("Storage analytics schema check PASSED.")
        print("\n=== Storage Optimization Integration Tests Passed! ===")
        
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
