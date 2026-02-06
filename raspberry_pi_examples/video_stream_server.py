#!/usr/bin/env python3
"""
Raspberry Pi Video Stream Server
Creates HTTP MJPEG stream that backend can access
"""

from flask import Flask, Response
from picamera2 import Picamera2
import cv2
import threading
import time

app = Flask(__name__)

# Initialize camera
try:
    picam2 = Picamera2()
    # Configure camera
    config = picam2.create_video_configuration(
        main={"size": (640, 480)},
        controls={"FrameRate": 30}
    )
    picam2.configure(config)
    picam2.start()
    CAMERA_AVAILABLE = True
    print("✅ Camera initialized")
except Exception as e:
    print(f"⚠️  Camera not available: {e}")
    print("Using simulated camera for testing")
    CAMERA_AVAILABLE = False

def generate_frames():
    """Generate video frames for MJPEG stream"""
    if not CAMERA_AVAILABLE:
        # Simulate frames for testing
        import numpy as np
        while True:
            # Create a simple test frame
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "Camera Not Available", (150, 240), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.033)  # ~30 fps
        return
    
    while True:
        try:
            # Capture frame from camera
            frame = picam2.capture_array()
            
            # Convert RGB to BGR for OpenCV
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
            # Optional: Add timestamp or overlay
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(frame_bgr, timestamp, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Encode frame as JPEG
            ret, buffer = cv2.imencode('.jpg', frame_bgr, 
                                      [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ret:
                continue
            
            frame_bytes = buffer.tobytes()
            
            # Yield frame in MJPEG format
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                   
        except Exception as e:
            print(f"Error generating frame: {e}")
            time.sleep(0.1)
            continue

@app.route('/video_feed')
def video_feed():
    """Video streaming route - MJPEG stream"""
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/health')
def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "camera_available": CAMERA_AVAILABLE
    }

if __name__ == '__main__':
    print("🎥 Starting video stream server...")
    print("📹 Stream available at: http://0.0.0.0:5000/video_feed")
    print("🔍 Health check: http://0.0.0.0:5000/health")
    print("Press Ctrl+C to stop\n")
    
    # Run on all interfaces so backend can access it
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)



