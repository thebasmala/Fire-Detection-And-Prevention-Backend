import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from datetime import timezone

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select, delete

from app.config import settings
from app.database import init_db, get_session
from app.core.mqtt_client import mqtt_client
from app.api import auth, devices, sensors, alerts, fire_events, video, ai
from app.models.device import Device, DeviceStatus
from app.models.sensor import Sensor, SensorReading, SensorStatus
from app.models.fire_event import FireEvent
from app.models.risky_device import RiskyDevice
from app.models.alert import Alert, AlertType
from app.services.notification_service import notification_service
from app.services.ai_service import ai_service

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    # Startup
    logger.info("Starting Fire Detection and Prevention Backend...")
    
    # Initialize database
    init_db()
    logger.info("Database initialized")
    os.makedirs(settings.fire_frames_upload_dir, exist_ok=True)
    
    # Connect MQTT client
    try:
        mqtt_client.connect()
        logger.info("MQTT client connected")
    except Exception as e:
        logger.error(f"Failed to connect MQTT client: {e}")
    
    # Register MQTT message handlers
    mqtt_client.register_handler("sensors/#", handle_sensor_message)
    mqtt_client.register_handler("camera/#", handle_camera_message)
    mqtt_client.register_handler("arm/#", handle_arm_message)

    # Start background task for sensor data retention
    retention_task = asyncio.create_task(cleanup_old_sensor_readings_task())
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    retention_task.cancel()
    mqtt_client.disconnect()
    logger.info("Shutdown complete")


def handle_sensor_message(topic: str, payload: dict):
    """Handle incoming sensor messages from MQTT"""
    try:
        from app.database import engine
        with Session(engine) as session:
            # Parse sensor data from MQTT payload
            # Expected format: {"sensor_id": int, "value": float, "device_id": int}
            sensor_id = payload.get("sensor_id")
            value = payload.get("value")
            device_id = payload.get("device_id")
            
            if sensor_id and value is not None:
                # Create sensor reading (for history/audit)
                reading = SensorReading(
                    sensor_id=sensor_id,
                    value=value,
                    timestamp=datetime.utcnow()
                )
                session.add(reading)
                session.commit()
                session.refresh(reading)
                
                # Get sensor to update live status and check threshold
                sensor = session.get(Sensor, sensor_id)
                if sensor:
                    sensor.last_value = value
                    sensor.last_timestamp = datetime.utcnow()
                    
                    # Derive sensor status based on threshold if available
                    if sensor.threshold is not None:
                        if value >= sensor.threshold:
                            sensor.status = SensorStatus.CRITICAL
                        elif value >= 0.8 * sensor.threshold:
                            sensor.status = SensorStatus.WARNING
                        else:
                            sensor.status = SensorStatus.NORMAL
                    else:
                        sensor.status = SensorStatus.NORMAL
                    
                    # Threshold exceeded, create alert synchronously
                    if sensor.threshold is not None and value >= sensor.threshold:
                        alert = Alert(
                            alert_type=AlertType.HIGH_TEMP if sensor.sensor_type == "temperature" else AlertType.GAS_DETECTED,
                            sensor_reading_id=reading.id,
                        )
                        session.add(alert)
                        # Send MQTT notification
                        notification = {
                            "alert_id": alert.id,
                            "type": alert.alert_type,
                            "sensor_reading_id": reading.id,
                            "timestamp": alert.created_at.isoformat()
                        }
                        mqtt_client.publish("notifications/alerts", notification)
                    
                    session.add(sensor)
                
                # Update device last_seen
                if device_id:
                    device = session.get(Device, device_id)
                    if device:
                        device.status = DeviceStatus.ONLINE
                        device.last_seen = datetime.utcnow()
                        session.add(device)
                
                session.commit()
                logger.debug(f"Processed sensor reading: sensor_id={sensor_id}, value={value}")
    except Exception as e:
        logger.error(f"Error handling sensor message: {e}")


def handle_camera_message(topic: str, payload: dict):
    """Handle incoming camera messages from MQTT"""
    try:
        from app.database import engine
        import base64
        import asyncio
        
        # Production Pi integration payload (JSONL event forwarded through MQTT)
        # Example:
        # {
        #   "alert_status": "FIRE_DETECTED",
        #   "detection_type": "FIRE",
        #   "confidence": 0.61,
        #   "timestamp": 1775754185.28,
        #   "pan": 0.24,
        #   "tilt": -0.47,
        #   "frame_path": ".../frame_857.jpg"
        # }
        alert_status = str(payload.get("alert_status", "")).strip().upper()
        detection_type = str(payload.get("detection_type", "")).strip().upper()
        confidence_raw = payload.get("confidence")
        try:
            confidence = float(confidence_raw) if confidence_raw is not None else None
        except (TypeError, ValueError):
            confidence = None
        logger.info(
            "Camera MQTT message received: topic=%s alert_status=%s detection_type=%s confidence=%s",
            topic,
            alert_status,
            detection_type,
            confidence,
        )
        
        if (
            alert_status == "FIRE_DETECTED"
            and detection_type == "FIRE"
            and confidence is not None
            and confidence >= settings.fire_event_min_confidence
        ):
            device_id = payload.get("device_id")
            camera_id = payload.get("camera_id") or device_id

            frame_reference = (
                payload.get("frame_url")
                or payload.get("frame_path")
                or payload.get("fire_frame_path")
                or payload.get("fire_frame")
                or payload.get("image_path")
            )

            zone_raw = payload.get("zone")
            try:
                zone = int(zone_raw) if zone_raw is not None else None
            except (TypeError, ValueError):
                zone = None

            # Expected from Pi payload: `dateandtime` (string ISO or unix seconds).
            detected_at = datetime.utcnow()
            dt_val = payload.get("dateandtime") or payload.get("datetime") or payload.get("detected_at") or payload.get("timestamp")
            if isinstance(dt_val, (int, float)):
                try:
                    detected_at = datetime.utcfromtimestamp(float(dt_val))
                except (TypeError, ValueError, OSError):
                    detected_at = datetime.utcnow()
            elif isinstance(dt_val, str) and dt_val.strip():
                try:
                    detected_at = datetime.fromisoformat(dt_val.strip())
                except ValueError:
                    detected_at = datetime.utcnow()
            
            with Session(engine) as session:
                fire_event = FireEvent(
                    zone=zone,
                    confidence=round(confidence if confidence is not None else 0.0, 2),
                    frame=frame_reference,
                    detected_at=detected_at,
                )
                session.add(fire_event)
                session.commit()
                session.refresh(fire_event)
                fire_alert = Alert(
                    alert_type=AlertType.FIRE_DETECTED,
                    fire_event_id=fire_event.id,
                )
                session.add(fire_alert)
                session.commit()
                logger.info(
                    "Fire event created from integration payload: id=%s confidence=%.3f frame=%s",
                    fire_event.id,
                    fire_event.confidence,
                    frame_reference,
                )
            return
        
        if (
            alert_status == "DEVICE_DETECTED"
            and confidence is not None
            and confidence >= settings.device_event_min_confidence
        ):
            received_at = datetime.utcnow()
            device_name = str(payload.get("detection_type", "unknown")).strip()
            frame_id = payload.get("frame")
            frame_reference = (
                payload.get("frame_url")
                or payload.get("frame_path")
                or payload.get("image_path")
            )
            device_id = payload.get("device_id")
            zone_raw = payload.get("zone")
            try:
                zone = int(zone_raw) if zone_raw is not None else None
            except (TypeError, ValueError):
                zone = None
            detected_at = datetime.utcnow()
            dt_val = payload.get("dateandtime") or payload.get("datetime") or payload.get("detected_at") or payload.get("timestamp")
            if isinstance(dt_val, (int, float)):
                try:
                    detected_at = datetime.utcfromtimestamp(float(dt_val))
                except (TypeError, ValueError, OSError):
                    detected_at = datetime.utcnow()
            elif isinstance(dt_val, str) and dt_val.strip():
                try:
                    detected_at = datetime.fromisoformat(dt_val.strip())
                except ValueError:
                    detected_at = received_at
            # Normalize to UTC-naive for safe comparison/storage with TIMESTAMP WITHOUT TIME ZONE
            if isinstance(detected_at, datetime) and detected_at.tzinfo is not None:
                detected_at = detected_at.astimezone(timezone.utc).replace(tzinfo=None)
            with Session(engine) as session:
                last_statement = (
                    select(RiskyDevice)
                    .where(RiskyDevice.device_type == device_name)
                    .where(RiskyDevice.zone == zone)
                    .order_by(RiskyDevice.detected_at.desc())
                )
                last_risky = session.exec(last_statement).first()
                if (
                    last_risky is not None
                ):
                    delta_sec = (received_at - last_risky.detected_at).total_seconds()
                    if 0 <= delta_sec < settings.risky_device_cooldown_seconds:
                        logger.info(
                            "Risky device cooldown active: type=%s zone=%s last=%s now=%s cooldown=%ss",
                            device_name,
                            zone,
                            last_risky.detected_at.isoformat(),
                            received_at.isoformat(),
                            settings.risky_device_cooldown_seconds,
                        )
                        return
                risky = RiskyDevice(
                    device_type=device_name,
                    confidence=round(float(confidence), 2),
                    zone=zone,
                    frame=str(frame_reference) if frame_reference is not None else None,
                    detected_at=detected_at,
                )
                session.add(risky)
                session.commit()
                session.refresh(risky)
                device_alert = Alert(
                    alert_type=AlertType.RISKY_DEVICE_DETECTED,
                    risky_device_id=risky.id,
                )
                session.add(device_alert)
                session.commit()
                session.refresh(device_alert)
                logger.info(
                    "Risky device persisted: risky_id=%s alert_id=%s type=%s zone=%s",
                    risky.id,
                    device_alert.id,
                    risky.device_type,
                    risky.zone,
                )
            mqtt_client.publish(
                "notifications/alerts",
                {
                    "type": "device_detected",
                    "title": "Device Detected",
                    "message": f"{device_name} detected",
                    "severity": 2,
                    "timestamp": detected_at.isoformat(),
                    "confidence": confidence,
                    "zone": zone,
                    "frame": frame_id,
                    "detection_type": device_name,
                    "device_id": device_id,
                },
            )
            logger.info(
                "Device event accepted from integration payload: type=%s confidence=%.3f zone=%s frame=%s",
                device_name,
                confidence,
                zone,
                frame_id,
            )
            return
        
        if alert_status in {"FIRE_DETECTED", "DEVICE_DETECTED"}:
            logger.info(
                "Camera MQTT message ignored by filters: alert_status=%s detection_type=%s confidence=%s threshold=%s",
                alert_status,
                detection_type,
                confidence,
                settings.fire_event_min_confidence,
            )
        
        # Parse camera data from MQTT payload
        # Expected format: {"device_id": int, "image_data": str (base64), "metadata": dict}
        device_id = payload.get("device_id")
        image_data = payload.get("image_data")
        metadata = payload.get("metadata", {})
        
        if device_id and image_data:
            # Decode image
            try:
                image_bytes = base64.b64decode(image_data)
            except Exception as decode_error:
                logger.error(f"Error decoding image data: {decode_error}")
                return
            
            # Call AI service asynchronously
            async def process_fire_detection():
                result = await ai_service.locate_fire(image_bytes, metadata)
                
                if result and result.get("confidence", 0) > 0.7:  # Fire detected with high confidence
                    with Session(engine) as session:
                        # Create fire event (spatial columns removed from FireEvent schema)
                        fire_event = FireEvent(
                            confidence=round(float(result.get("confidence", 0.0)), 2),
                            detected_at=datetime.utcnow()
                        )
                        session.add(fire_event)
                        session.commit()
                        session.refresh(fire_event)
                        
                        # Automatically move arm and activate if pan/tilt available in AI result
                        pan = result.get("pan") or result.get("x")
                        tilt = result.get("tilt") or result.get("y")
                        if pan is not None and tilt is not None:
                            from app.core.serial_client import serial_client
                            import time
                            serial_client.move_arm(pan=pan, tilt=tilt)
                            time.sleep(1)  # Wait for arm to move
                            serial_client.activate_arm()
                            fire_event.resolved_at = datetime.utcnow()
                            session.add(fire_event)
                            session.commit()
                            logger.info(f"Arm activated automatically for fire event {fire_event.id}")
                        
                        # Send notification via MQTT
                        notification = {
                            "alert_id": None,
                            "type": "fire_detected",
                            "title": "Fire Detected!",
                            "message": f"Fire detected at {metadata.get('location', 'unknown location')}",
                            "severity": 5,
                            "fire_event_id": fire_event.id,
                            "timestamp": fire_event.detected_at.isoformat()
                        }
                        mqtt_client.publish("notifications/alerts", notification)
                        
                        logger.info(f"Fire detected! Event ID: {fire_event.id}, Pan: {pan}, Tilt: {tilt}")
            
            # Schedule async task
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(process_fire_detection())
                else:
                    loop.run_until_complete(process_fire_detection())
            except RuntimeError:
                # No event loop, create new one
                asyncio.run(process_fire_detection())
    except Exception as e:
        logger.error(f"Error handling camera message: {e}")


def handle_arm_message(topic: str, payload: dict):
    """Handle incoming arm status messages from MQTT"""
    try:
        from app.database import engine
        with Session(engine) as session:
            # Parse arm status from MQTT payload
            # Expected format: {"device_id": int, "status": str, "position": dict}
            device_id = payload.get("device_id")
            status = payload.get("status")
            
            if device_id:
                device = session.get(Device, device_id)
                if device:
                    device.last_seen = datetime.utcnow()
                    device.status = DeviceStatus.ONLINE if status == "active" else DeviceStatus.OFFLINE
                    session.add(device)
                    session.commit()
                    logger.debug(f"Updated arm device status: device_id={device_id}, status={status}")
    except Exception as e:
        logger.error(f"Error handling arm message: {e}")


async def cleanup_old_sensor_readings_task():
    """Periodically delete old sensor readings based on retention setting."""
    from app.database import engine
    try:
        while True:
            try:
                with Session(engine) as session:
                    cutoff = datetime.utcnow() - timedelta(days=settings.sensor_data_retention_days)
                    session.exec(
                        delete(SensorReading).where(SensorReading.timestamp < cutoff)
                    )
                    session.commit()
                    logger.info("Old sensor readings cleanup completed")
            except Exception as cleanup_error:
                logger.error(f"Error during sensor readings cleanup: {cleanup_error}")
            # Run once per day
            await asyncio.sleep(24 * 60 * 60)
    except asyncio.CancelledError:
        logger.info("Sensor readings cleanup task cancelled")


# Create FastAPI application
app = FastAPI(
    title="Fire Detection and Prevention API",
    description="Backend API for fire detection and prevention system with MQTT integration",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
if settings.debug:
    cors_origins = ["*"]
else:
    cors_origins = [
        origin.strip()
        for origin in (settings.cors_origins or "").split(",")
        if origin.strip()
    ]
    if not cors_origins:
        logger.warning(
            "Production mode with empty CORS_ORIGINS: browser clients may be blocked by CORS."
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.fire_frames_upload_dir, exist_ok=True)
app.mount(
    "/static/fire_frames",
    StaticFiles(directory=settings.fire_frames_upload_dir),
    name="fire_frames_static",
)
os.makedirs(settings.frames_upload_dir, exist_ok=True)
app.mount(
    "/static/frames",
    StaticFiles(directory=settings.frames_upload_dir),
    name="frames_static",
)

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(devices.router, prefix="/api")
app.include_router(sensors.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(fire_events.router, prefix="/api")
app.include_router(video.router, prefix="/api")
app.include_router(ai.router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Fire Detection and Prevention API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "mqtt_connected": mqtt_client.is_connected
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )

