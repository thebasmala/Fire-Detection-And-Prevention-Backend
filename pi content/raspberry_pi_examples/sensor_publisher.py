#!/usr/bin/env python3
"""
Raspberry Pi Sensor Publisher
Publishes sensor readings to MQTT broker
"""

import paho.mqtt.client as mqtt
import time
import json
import sys
from datetime import datetime

# Configuration - UPDATE THESE VALUES
# Broker runs on Raspberry Pi in your setup.
MQTT_BROKER = "raspberrypi.local"
MQTT_PORT = 1883
MQTT_TOPIC = "sensors/temp1"
DEVICE_ID = 1  # Must match a row in your DB (devices table)
SENSOR_ID = 1  # Must match a row in your DB (sensors table)

# Try importing GPIO libraries (install if needed: pip install RPi.GPIO gpiozero)
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    print("Warning: RPi.GPIO not available. Using simulated sensor data.")
    GPIO_AVAILABLE = False

def read_temperature_simulated():
    """Simulate temperature reading (for testing without hardware)"""
    import random
    # Simulate temperature between 20-30°C with occasional spike
    base_temp = 25.0
    if random.random() < 0.1:  # 10% chance of high temperature
        return base_temp + random.uniform(50, 60)  # Fire condition
    return base_temp + random.uniform(-2, 2)

def read_temperature():
    """Read temperature from actual sensor"""
    if not GPIO_AVAILABLE:
        return read_temperature_simulated()
    
    # Example: Read from analog sensor via MCP3008 ADC
    # from gpiozero import MCP3008
    # adc = MCP3008(channel=0)
    # voltage = adc.value * 3.3
    # temperature = (voltage - 0.5) * 100
    # return temperature
    
    # For now, use simulated
    return read_temperature_simulated()

def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker"""
    if rc == 0:
        print(f"✅ Connected to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")
    else:
        print(f"❌ Failed to connect, return code {rc}")
        sys.exit(1)

def on_disconnect(client, userdata, rc):
    """Callback when disconnected"""
    print("⚠️  Disconnected from MQTT broker")

def publish_sensor_reading():
    """Main function to publish sensor readings"""
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    try:
        print(f"Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        
        print(f"📡 Publishing to topic: {MQTT_TOPIC}")
        print("Press Ctrl+C to stop\n")
        
        while True:
            # Read sensor value
            value = read_temperature()
            
            # Create message payload (matches backend's expected format)
            payload = {
                "sensor_id": SENSOR_ID,
                "device_id": DEVICE_ID,
                "value": round(value, 2),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Publish to MQTT
            result = client.publish(MQTT_TOPIC, json.dumps(payload), qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                status = "✅" if value < 30 else "🔥"  # Fire emoji if high temp
                print(f"{status} Published: {value}°C (Sensor ID: {SENSOR_ID})")
            else:
                print(f"❌ Failed to publish: {result.rc}")
            
            # Wait before next reading (5 seconds)
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping sensor publisher...")
        client.loop_stop()
        client.disconnect()
        print("✅ Disconnected")
    except Exception as e:
        print(f"❌ Error: {e}")
        client.loop_stop()
        client.disconnect()
        sys.exit(1)

if __name__ == "__main__":
    publish_sensor_reading()

