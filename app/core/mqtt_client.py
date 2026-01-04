import json
import logging
from typing import Callable, Optional
import paho.mqtt.client as mqtt
from app.config import settings

logger = logging.getLogger(__name__)


class MQTTClient:
    def __init__(self):
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.message_handlers: dict[str, Callable] = {}
        self.is_connected = False
        
        # Set credentials if provided
        if settings.mqtt_username and settings.mqtt_password:
            self.client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client receives a CONNACK response from the server"""
        if rc == 0:
            self.is_connected = True
            logger.info("MQTT Client connected successfully")
            # Subscribe to topics
            self.client.subscribe(settings.mqtt_topic_sensors)
            self.client.subscribe(settings.mqtt_topic_camera)
            self.client.subscribe(settings.mqtt_topic_arm)
            logger.info(f"Subscribed to topics: {settings.mqtt_topic_sensors}, {settings.mqtt_topic_camera}, {settings.mqtt_topic_arm}")
        else:
            logger.error(f"Failed to connect to MQTT broker, return code {rc}")
    
    def _on_message(self, client, userdata, msg):
        """Callback for when a PUBLISH message is received from the server"""
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            payload = msg.payload.decode()
        
        logger.debug(f"Received message on topic {topic}: {payload}")
        
        # Call registered handlers
        for topic_pattern, handler in self.message_handlers.items():
            if self._topic_matches(topic, topic_pattern):
                try:
                    handler(topic, payload)
                except Exception as e:
                    logger.error(f"Error in message handler for {topic_pattern}: {e}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the server"""
        self.is_connected = False
        logger.warning(f"MQTT Client disconnected, return code {rc}")
    
    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """Check if a topic matches a pattern (supports # and + wildcards)"""
        if pattern == topic:
            return True
        if pattern.endswith("#"):
            prefix = pattern[:-1]
            return topic.startswith(prefix)
        # Simple matching for now, can be enhanced
        return False
    
    def connect(self):
        """Connect to MQTT broker"""
        try:
            self.client.connect(settings.mqtt_broker_host, settings.mqtt_broker_port, 60)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Error connecting to MQTT broker: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        self.client.loop_stop()
        self.client.disconnect()
        self.is_connected = False
    
    def subscribe(self, topic: str, handler: Optional[Callable] = None):
        """Subscribe to a topic and optionally register a handler"""
        self.client.subscribe(topic)
        if handler:
            self.message_handlers[topic] = handler
    
    def publish(self, topic: str, payload: dict, qos: int = 0):
        """Publish a message to a topic"""
        if not self.is_connected:
            logger.warning("MQTT client not connected, cannot publish")
            return False
        
        try:
            message = json.dumps(payload) if isinstance(payload, dict) else payload
            result = self.client.publish(topic, message, qos)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"Error publishing to {topic}: {e}")
            return False
    
    def register_handler(self, topic_pattern: str, handler: Callable):
        """Register a message handler for a topic pattern"""
        self.message_handlers[topic_pattern] = handler


# Global MQTT client instance
mqtt_client = MQTTClient()

