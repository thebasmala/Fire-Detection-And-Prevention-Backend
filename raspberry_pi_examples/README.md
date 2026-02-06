# Raspberry Pi Scripts

These scripts run on your Raspberry Pi to communicate with the FastAPI backend.

## Setup

1. **Install dependencies on Raspberry Pi:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Update configuration in each script:**
   - `MQTT_BROKER`: Your backend's IP address or domain
   - `MQTT_PORT`: Usually 1883
   - `DEVICE_ID`: Match with device ID in your database
   - `SENSOR_ID`: Match with sensor ID in your database

3. **Set up MQTT Broker:**
   - Install Mosquitto: `sudo apt-get install mosquitto mosquitto-clients`
   - Or use a cloud MQTT broker (HiveMQ, CloudMQTT, etc.)

## Scripts

### sensor_publisher.py
- Reads sensor data (temperature, smoke, etc.)
- Publishes to MQTT topic: `sensors/#`
- Backend receives and stores readings

**Usage:**
```bash
python3 sensor_publisher.py
```

### camera_publisher.py
- Captures images from Raspberry Pi camera
- Publishes to MQTT topic: `camera/#`
- Backend receives and processes with AI models

**Usage:**
```bash
python3 camera_publisher.py
```

## Testing Without Hardware

Both scripts work in simulation mode if hardware is not available:
- Sensor: Generates random temperature values
- Camera: Creates test images

## Integration with Backend

1. **Start MQTT broker** (if running locally)
2. **Start FastAPI backend** (your main project)
3. **Run these scripts on Raspberry Pi**
4. **Backend automatically receives and processes data**

## Next Steps

- Connect actual sensors to GPIO pins
- Connect Raspberry Pi camera module
- Implement AI model inference
- Add error handling and reconnection logic

