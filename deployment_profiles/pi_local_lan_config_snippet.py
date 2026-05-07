# Paste this block into:
# /home/pi/smart_fire_system/integration/smart_fire_system/config.py
# when Pi and backend laptop are on the SAME LAN.

MQTT_ENABLED = True
MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC_FIRE = "camera/pi"
MQTT_QOS = 1
MQTT_DEVICE_ID = 1
MQTT_CAMERA_ID = 1

# Backend frame upload/API base from Pi -> backend laptop on same LAN.
# Prefer hostname first; fallback to LAN IP if mDNS fails.
BACKEND_BASE_URL = "http://Basmala.local:8000"
# BACKEND_BASE_URL = "http://192.168.100.4:8000"

FIRE_FRAME_UPLOAD_API_KEY = "REPLACE_WITH_YOUR_KEY"

# Built-in stream served by smart_fire_main.py
ENABLE_MJPEG_STREAM = True
MJPEG_STREAM_HOST = "0.0.0.0"
MJPEG_STREAM_PORT = 5000
MJPEG_JPEG_QUALITY = 85
