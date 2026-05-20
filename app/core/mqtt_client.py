import json
import logging
import os
import ssl
import threading
import time
import uuid
from typing import Callable, Optional

import paho.mqtt.client as mqtt
from app.config import settings

logger = logging.getLogger(__name__)

MQTT_RECONNECT_INTERVAL_SEC = 5
_LEGACY_PAHO_WARNED = False

# MQTT CONNACK / disconnect reason codes (MQTT 3.1.1)
_MQTT_RC_MESSAGES = {
    1: "unacceptable protocol version",
    2: "identifier rejected",
    3: "server unavailable",
    4: "bad username or password",
    5: "not authorized (wrong credentials or insufficient HiveMQ permissions)",
}


def _mqtt_rc_message(rc: int) -> str:
    return _MQTT_RC_MESSAGES.get(rc, f"unknown error ({rc})")


def _cloud_mqtt_enabled() -> bool:
    """HiveMQ mode when both username and password are non-empty."""
    username = (settings.mqtt_username or "").strip()
    password = (settings.mqtt_password or "").strip()
    return bool(username and password)


def _create_mqtt_client(*, client_id: str) -> mqtt.Client:
    """Use Callback API v2 when paho-mqtt >= 1.6; else legacy Client (older installs)."""
    global _LEGACY_PAHO_WARNED
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    if not _LEGACY_PAHO_WARNED:
        _LEGACY_PAHO_WARNED = True
        logger.warning(
            "paho-mqtt is older than 1.6 (no CallbackAPIVersion); using legacy API. "
            "Upgrade with: pip install -U 'paho-mqtt>=1.6.1'"
        )
    return mqtt.Client(client_id=client_id)


def _mqtt_client_id() -> str:
    """HiveMQ Cloud needs a unique client id; local Mosquitto can reuse a stable id."""
    if _cloud_mqtt_enabled():
        return f"fire-api-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    return "fire-detection-api"


class MQTTClient:
    def __init__(self):
        self.client: Optional[mqtt.Client] = None
        self.message_handlers: dict[str, Callable] = {}
        self.is_connected = False
        self._stop_event = threading.Event()
        self._retry_thread: Optional[threading.Thread] = None
        self._loop_running = False
        self._connect_lock = threading.Lock()

    def mqtt_connected(self) -> bool:
        """True if the broker session is up (paho state + our on_connect flag)."""
        if self.client is not None:
            try:
                if hasattr(self.client, "is_connected") and self.client.is_connected():
                    self.is_connected = True
                    return True
            except Exception:
                pass
        return self.is_connected

    def _build_client(self) -> mqtt.Client:
        client = _create_mqtt_client(client_id=_mqtt_client_id())
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect

        if _cloud_mqtt_enabled():
            username = (settings.mqtt_username or "").strip()
            password = (settings.mqtt_password or "").strip()
            client.username_pw_set(username, password)
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            logger.info(
                "MQTT cloud mode (TLS + auth): host=%s port=%s user=%s",
                settings.mqtt_broker_host,
                settings.mqtt_broker_port,
                username,
            )
        else:
            logger.info(
                "MQTT local mode (no TLS, no auth): host=%s port=%s",
                settings.mqtt_broker_host,
                settings.mqtt_broker_port,
            )
        return client

    def _on_connect(self, client: mqtt.Client, userdata, flags, *args):
        # v1: (rc,)  |  v2: (reason_code, properties)
        rc = args[0] if args else 0
        if rc == 0:
            self.is_connected = True
            logger.info("MQTT client connected successfully")
            client.subscribe(settings.mqtt_topic_sensors)
            client.subscribe(settings.mqtt_topic_camera)
            client.subscribe(settings.mqtt_topic_arm)
            logger.info(
                "Subscribed to topics: %s, %s, %s",
                settings.mqtt_topic_sensors,
                settings.mqtt_topic_camera,
                settings.mqtt_topic_arm,
            )
        else:
            self.is_connected = False
            logger.error(
                "MQTT connect failed: %s (code %s). "
                "For HiveMQ: verify username/password in the console; if password contains # use quotes in .env.",
                _mqtt_rc_message(rc),
                rc,
            )

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            payload = msg.payload.decode()

        logger.debug("Received message on topic %s: %s", topic, payload)

        for topic_pattern, handler in self.message_handlers.items():
            if self._topic_matches(topic, topic_pattern):
                try:
                    handler(topic, payload)
                except Exception as e:
                    logger.error("Error in message handler for %s: %s", topic_pattern, e)

    def _on_disconnect(self, client, userdata, *args):
        # v1: (rc,)  |  v2: (disconnect_flags, reason_code, properties)
        rc = args[1] if len(args) >= 2 else (args[0] if args else -1)
        self.is_connected = False
        logger.warning("MQTT client disconnected, reason code %s", rc)

    def _topic_matches(self, topic: str, pattern: str) -> bool:
        if pattern == topic:
            return True
        if pattern.endswith("#"):
            prefix = pattern[:-1]
            return topic.startswith(prefix)
        return False

    def _teardown_client(self):
        if self.client is None:
            return
        try:
            if self._loop_running:
                self.client.loop_stop()
                self._loop_running = False
        except Exception as e:
            logger.debug("MQTT loop_stop: %s", e)
        try:
            self.client.disconnect()
        except Exception as e:
            logger.debug("MQTT disconnect: %s", e)
        self.client = None
        self.is_connected = False

    def _connect_once(self):
        if self.mqtt_connected():
            return
        with self._connect_lock:
            if self.mqtt_connected():
                return
            self._teardown_client()
            self.client = self._build_client()
            self.client.connect(
                settings.mqtt_broker_host,
                settings.mqtt_broker_port,
                keepalive=60,
            )
            self.client.loop_start()
            self._loop_running = True

    def _retry_loop(self):
        while not self._stop_event.is_set():
            if not self.mqtt_connected():
                try:
                    self._connect_once()
                except Exception as e:
                    logger.error(
                        "MQTT connection error (%s:%s): %s — retrying in %ss",
                        settings.mqtt_broker_host,
                        settings.mqtt_broker_port,
                        e,
                        MQTT_RECONNECT_INTERVAL_SEC,
                    )
            self._stop_event.wait(MQTT_RECONNECT_INTERVAL_SEC)

    def start(self):
        """Start background connect/retry loop; does not raise on failure."""
        if self._retry_thread is not None and self._retry_thread.is_alive():
            return
        self._stop_event.clear()
        self._retry_thread = threading.Thread(
            target=self._retry_loop,
            name="mqtt-reconnect",
            daemon=True,
        )
        self._retry_thread.start()
        logger.info("MQTT reconnect loop started (interval=%ss)", MQTT_RECONNECT_INTERVAL_SEC)

    def connect(self):
        """Single connect attempt (legacy). Prefer start() for resilient reconnect."""
        self._connect_once()

    def disconnect(self):
        """Stop retry loop and disconnect from broker."""
        self._stop_event.set()
        if self._retry_thread is not None:
            self._retry_thread.join(timeout=MQTT_RECONNECT_INTERVAL_SEC + 2)
            self._retry_thread = None
        self._teardown_client()
        logger.info("MQTT client stopped")

    def subscribe(self, topic: str, handler: Optional[Callable] = None):
        if self.client is not None:
            self.client.subscribe(topic)
        if handler:
            self.message_handlers[topic] = handler

    def publish(self, topic: str, payload: dict, qos: int = 0) -> bool:
        if not self.mqtt_connected() or self.client is None:
            logger.warning("MQTT client not connected, cannot publish to %s", topic)
            return False
        try:
            message = json.dumps(payload) if isinstance(payload, dict) else payload
            result = self.client.publish(topic, message, qos)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error("Error publishing to %s: %s", topic, e)
            return False

    def register_handler(self, topic_pattern: str, handler: Callable):
        self.message_handlers[topic_pattern] = handler


mqtt_client = MQTTClient()
