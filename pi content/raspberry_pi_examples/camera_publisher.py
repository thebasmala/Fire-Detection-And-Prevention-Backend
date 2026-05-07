#!/usr/bin/env python3
"""
Raspberry Pi Camera Publisher
Captures images and publishes to MQTT broker
"""

import paho.mqtt.client as mqtt
import time
import json
import base64
import sys
from datetime import datetime

# Configuration - UPDATE THESE VALUES
# Broker runs on Raspberry Pi in your setup.
MQTT_BROKER = "raspberrypi.local"
MQTT_PORT = 1883
MQTT_TOPIC = "camera/entrance"
DEVICE_ID = 1  # Must match a row in your DB (devices table); change if yours differs

# Try importing camera libraries
try:
    from picamera2 import Picamera2
    import numpy as np
    CAMERA_AVAILABLE = True
except ImportError:
    print("Warning: picamera2 not available. Install with: pip install picamera2")
    print("Using simulated camera for testing.")
    CAMERA_AVAILABLE = False

def capture_image_simulated():
    """Simulate image capture (for testing without camera)"""
    # Create a simple test image (red square to simulate fire)
    import io
    from PIL import Image, ImageDraw
    
    img = Image.new('RGB', (640, 480), color='black')
    draw = ImageDraw.Draw(img)
    # Draw a red rectangle (simulating fire)
    draw.rectangle([200, 150, 400, 300], fill='red')
    
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    return img_byte_arr.getvalue()

def capture_image():
    """Capture image from Raspberry Pi camera"""
    if not CAMERA_AVAILABLE:
        return capture_image_simulated()
    
    try:
        picam2 = Picamera2()
        picam2.start()
        time.sleep(1)  # Allow camera to initialize
        
        # Capture image
        image = picam2.capture_image()
        
        # Convert to bytes
        import io
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG')
        img_bytes = img_byte_arr.getvalue()
        
        picam2.stop()
        return img_bytes
    except Exception as e:
        print(f"Error capturing image: {e}")
        return capture_image_simulated()

def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker"""
    if rc == 0:
        print(f"✅ Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
    else:
        print(f"❌ Failed to connect, return code {rc}")
        sys.exit(1)

def publish_camera_image():
    """Main function to publish camera images"""
    client = mqtt.Client()
    client.on_connect = on_connect
    
    try:
        print(f"Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        print(f"📹 Publishing camera images to topic: {MQTT_TOPIC}")
        print("Press Ctrl+C to stop\n")
        
        frame_count = 0
        
        while True:
            # Capture image
            image_bytes = capture_image()
            
            # Encode to base64
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # Create message payload (matches backend's expected format)
            payload = {
                "device_id": DEVICE_ID,
                "image_data": image_base64,
                "metadata": {
                    "location": "Entrance Hall",
                    "timestamp": datetime.utcnow().isoformat(),
                    "format": "jpeg",
                    "frame_number": frame_count
                }
            }
            
            # Publish to MQTT
            # Note: Large images may need chunking for MQTT
            # Consider using HTTP for large images instead
            result = client.publish(MQTT_TOPIC, json.dumps(payload), qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                size_kb = len(image_bytes) / 1024
                print(f"✅ Published image #{frame_count} ({size_kb:.1f} KB)")
            else:
                print(f"❌ Failed to publish: {result.rc}")
            
            frame_count += 1
            
            # Wait before next capture (10 seconds)
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping camera publisher...")
        client.loop_stop()
        client.disconnect()
        print("✅ Disconnected")
    except Exception as e:
        print(f"❌ Error: {e}")
        client.loop_stop()
        client.disconnect()
        sys.exit(1)

if __name__ == "__main__":
    publish_camera_image()

