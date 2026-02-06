import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from datetime import datetime

from app.config import settings
from app.database import init_db, get_session
from app.core.mqtt_client import mqtt_client
from app.core.serial_client import serial_client
from app.api import auth, devices, sensors, alerts, fire_events, video, ai
from app.models.device import Device, DeviceStatus
from app.models.sensor import Sensor, SensorReading
from app.models.fire_event import FireEvent, FireEventStatus
from app.models.alert import AlertType
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
    
    # Connect MQTT client
    try:
        mqtt_client.connect()
        logger.info("MQTT client connected")
    except Exception as e:
        logger.error(f"Failed to connect MQTT client: {e}")
    
    # Connect serial client (for arm control)
    try:
        serial_client.connect()
        logger.info("Serial client connected")
    except Exception as e:
        logger.warning(f"Failed to connect serial client (arm may not be available): {e}")
    
    # Register MQTT message handlers
    mqtt_client.register_handler("sensors/#", handle_sensor_message)
    mqtt_client.register_handler("camera/#", handle_camera_message)
    mqtt_client.register_handler("arm/#", handle_arm_message)
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    mqtt_client.disconnect()
    serial_client.disconnect()
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
                # Create sensor reading
                reading = SensorReading(
                    sensor_id=sensor_id,
                    value=value,
                    timestamp=datetime.utcnow()
                )
                session.add(reading)
                
                # Get sensor to check threshold
                from app.models.sensor import Sensor
                sensor = session.get(Sensor, sensor_id)
                if sensor and sensor.threshold and value >= sensor.threshold:
                    # Threshold exceeded, create alert synchronously
                    alert = Alert(
                        alert_type=AlertType.HIGH_TEMPERATURE if sensor.sensor_type == "temperature" else AlertType.SMOKE_DETECTED,
                        title=f"High {sensor.sensor_type} detected",
                        message=f"Sensor {sensor.name} reading {value} exceeds threshold {sensor.threshold}",
                        severity=3,
                        sensor_id=sensor_id,
                        device_id=device_id
                    )
                    session.add(alert)
                    # Send MQTT notification
                    notification = {
                        "alert_id": alert.id,
                        "type": alert.alert_type,
                        "title": alert.title,
                        "message": alert.message,
                        "severity": alert.severity,
                        "timestamp": alert.created_at.isoformat()
                    }
                    mqtt_client.publish("notifications/alerts", notification)
                
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
                        # Get pan/tilt from AI model (or fallback to x/y for backward compatibility)
                        pan = result.get("pan") or result.get("x")
                        tilt = result.get("tilt") or result.get("y")
                        
                        # Create fire event
                        # Note: x_coordinate stores pan, y_coordinate stores tilt
                        fire_event = FireEvent(
                            status=FireEventStatus.DETECTED,
                            device_id=device_id,
                            camera_id=device_id,
                            angle=result.get("angle") or pan,  # Use pan as angle if angle not provided
                            x_coordinate=pan,  # Pan angle
                            y_coordinate=tilt,  # Tilt angle
                            confidence=result.get("confidence"),
                            detected_at=datetime.utcnow()
                        )
                        session.add(fire_event)
                        session.commit()
                        session.refresh(fire_event)
                        
                        # Automatically move arm and activate if pan/tilt available
                        if pan is not None and tilt is not None:
                            from app.core.serial_client import serial_client
                            import time
                            serial_client.move_arm(pan=pan, tilt=tilt)
                            time.sleep(1)  # Wait for arm to move
                            serial_client.activate_arm()
                            fire_event.status = FireEventStatus.SUPPRESSING
                            fire_event.suppressed_at = datetime.utcnow()
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


# Create FastAPI application
app = FastAPI(
    title="Fire Detection and Prevention API",
    description="Backend API for fire detection and prevention system with MQTT integration",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
# In production, replace ["*"] with your frontend domain(s)
# Example: allow_origins=["https://your-frontend.com", "https://www.your-frontend.com"]
cors_origins = ["*"] if settings.debug else [
    "https://your-frontend-domain.com",  # Update with your frontend URL
    "http://localhost:3000",  # For local development
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        "mqtt_connected": mqtt_client.is_connected,
        "serial_connected": serial_client.is_connected
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )

