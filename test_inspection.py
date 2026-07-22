import subprocess
import time
import requests
import sys

def test_pipeline():
    print("=== Start Integration Testing ===")
    
    # 1. Launch uvicorn server in a subprocess
    # Run main:app on port 8000
    log_file = open("uvicorn_test.log", "w")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=log_file,
        stderr=log_file
    )
    
    # Wait for the server to spin up
    print("Waiting for server to startup...")
    time.sleep(5)
    
    base_url = "http://127.0.0.1:8000"
    
    try:
        # 2. Check initial status
        print("Checking initial status...")
        res = requests.get(f"{base_url}/inspection/status")
        print("Status Code:", res.status_code)
        status_data = res.json()
        print("Response Payload:", status_data)
        assert res.status_code == 200
        assert status_data["running"] is False
        print("Initial status check PASSED.")
        
        # 3. Start inspection loop
        print("\nSending request to start continuous inspection loop...")
        res = requests.post(f"{base_url}/inspection/start")
        print("Start Code:", res.status_code)
        start_data = res.json()
        print("Response Payload:", start_data)
        assert res.status_code == 200
        assert start_data["status"] == "started"
        print("Start loop command PASSED.")
        
        # 4. Wait for loop to run several cycles
        print("\nAllowing continuous loop to capture and run inference (sleeping 8s)...")
        time.sleep(8)
        
        # 5. Check running status
        print("\nChecking running status...")
        res = requests.get(f"{base_url}/inspection/status")
        status_data = res.json()
        print("Response Payload:", status_data)
        assert status_data["running"] is True
        print("Running status check PASSED.")
        
        # 6. Retrieve analytics summary
        print("\nRetrieving analytics summary...")
        res = requests.get(f"{base_url}/analytics/summary")
        analytics_data = res.json()
        print("Response Payload:", analytics_data)
        assert res.status_code == 200
        assert analytics_data["total"] > 0
        print("Analytics summary check PASSED.")
        
        # 7. Retrieve history
        print("\nRetrieving inspection history logs...")
        res = requests.get(f"{base_url}/history")
        history_data = res.json()
        print(f"Retrieved {len(history_data)} inspection records.")
        if history_data:
            print("Latest record sample:", history_data[0])
        assert res.status_code == 200
        assert len(history_data) > 0
        print("History logs check PASSED.")
        
        # 8. Stop inspection loop
        print("\nSending request to stop continuous inspection loop...")
        res = requests.post(f"{base_url}/inspection/stop")
        print("Stop Code:", res.status_code)
        stop_data = res.json()
        print("Response Payload:", stop_data)
        assert res.status_code == 200
        assert stop_data["status"] == "stopped"
        print("Stop loop command PASSED.")
        
        # 9. Verify stopped status
        print("\nVerifying loop is stopped...")
        res = requests.get(f"{base_url}/inspection/status")
        status_data = res.json()
        print("Response Payload:", status_data)
        assert status_data["running"] is False
        print("Stopped status check PASSED.")
        
        print("\n=== Integration Tests Completed Successfully! ===")
        
    except AssertionError as e:
        print("\n!!! Assertion failure during integration test execution !!!")
        raise e
    except Exception as e:
        print("\n!!! Error occurred during integration testing !!!", e)
        raise e
    finally:
        print("\nTerminating uvicorn server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
            print("Server process terminated cleanly.")
        except subprocess.TimeoutExpired:
            server_process.kill()
            print("Server process force-killed.")
        log_file.close()

if __name__ == "__main__":
    test_pipeline()
