# Paste this block into:
# /home/pi/smart_fire_system/integration/smart_fire_system/config.py
# when Pi is on a DIFFERENT network than your backend laptop.

MQTT_ENABLED = True

# Option A (recommended): public/tunneled broker reachable by both sides.
MQTT_BROKER_HOST = "REPLACE_PUBLIC_MQTT_HOST"
MQTT_BROKER_PORT = 1883

# Option B (quick tests): disable MQTT path if not needed.
# MQTT_ENABLED = False

MQTT_TOPIC_FIRE = "camera/pi"
MQTT_QOS = 1
MQTT_DEVICE_ID = 1
MQTT_CAMERA_ID = 1

# Must be your PUBLIC backend URL (ngrok/cloudflared/deployed domain),
# not Basmala.local and not LAN IP.
BACKEND_BASE_URL = "https://REPLACE_PUBLIC_BACKEND_URL"
FIRE_FRAME_UPLOAD_API_KEY = "REPLACE_WITH_YOUR_KEY"

# Built-in stream served by smart_fire_main.py
ENABLE_MJPEG_STREAM = True
MJPEG_STREAM_HOST = "0.0.0.0"
MJPEG_STREAM_PORT = 5000
MJPEG_JPEG_QUALITY = 85
