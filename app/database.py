import logging

from sqlalchemy import inspect, text
from sqlmodel import SQLModel, Session, create_engine

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

_USER_NOTIFY_COLUMNS = (
    ("notify_email", "BOOLEAN DEFAULT TRUE"),
    ("notify_sms", "BOOLEAN DEFAULT FALSE"),
    ("notify_push", "BOOLEAN DEFAULT TRUE"),
    ("phone_number", "VARCHAR"),
    ("fcm_token", "VARCHAR"),
)

# Pi Arduino telemetry: device 1, sensors 1–4 temp (°C), 5–8 MQ2 (ppm)
PI_DEVICE_ID = 1
PI_SENSOR_SPECS: tuple[tuple[int, str, str, float, str], ...] = (
    (1, "Temperature Sensor 1", "temperature", 60.0, "C"),
    (2, "Temperature Sensor 2", "temperature", 60.0, "C"),
    (3, "Temperature Sensor 3", "temperature", 60.0, "C"),
    (4, "Temperature Sensor 4", "temperature", 60.0, "C"),
    (5, "MQ2 Sensor 1", "gas", 1000.0, "ppm"),
    (6, "MQ2 Sensor 2", "gas", 1000.0, "ppm"),
    (7, "MQ2 Sensor 3", "gas", 1000.0, "ppm"),
    (8, "MQ2 Sensor 4", "gas", 1000.0, "ppm"),
)


def _migrate_user_notification_columns() -> None:
    """Add notification preference columns if the user table predates them."""
    try:
        insp = inspect(engine)
        if "user" not in insp.get_table_names():
            return
        existing = {c["name"] for c in insp.get_columns("user")}
    except Exception as exc:
        logger.warning("Could not inspect user table for migrations: %s", exc)
        existing = set()

    for col_name, col_type in _USER_NOTIFY_COLUMNS:
        if col_name in existing:
            continue
        stmt = f'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS {col_name} {col_type}'
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
            logger.info('Added user column "%s"', col_name)
        except Exception as exc:
            logger.error('Failed to add user column "%s": %s', col_name, exc)


def _backfill_user_notification_defaults() -> None:
    """Ensure existing rows get push/email defaults after column migration."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    'UPDATE "user" SET notify_push = TRUE WHERE notify_push IS NULL'
                )
            )
            conn.execute(
                text(
                    'UPDATE "user" SET notify_email = TRUE WHERE notify_email IS NULL'
                )
            )
    except Exception as exc:
        logger.debug("User notification backfill skipped: %s", exc)


def seed_pi_sensors_and_device() -> None:
    """Ensure device 1 and sensors 1–8 exist for Pi MQTT (idempotent)."""
    from app.models.device import Device, DeviceType, DeviceStatus
    from app.models.sensor import Sensor, SensorType

    type_map = {t.value: t for t in SensorType}

    with Session(engine) as session:
        device = session.get(Device, PI_DEVICE_ID)
        if device is None:
            device = Device(
                id=PI_DEVICE_ID,
                name="Raspberry Pi 1",
                device_type=DeviceType.RASPBERRY_PI,
                status=DeviceStatus.OFFLINE,
                location="Main",
                mqtt_topic="sensors/#",
            )
            session.add(device)
            logger.info("Seeded device id=%s", PI_DEVICE_ID)
        else:
            device.name = device.name or "Raspberry Pi 1"
            device.device_type = DeviceType.RASPBERRY_PI
            session.add(device)

        for sensor_id, name, stype, threshold, unit in PI_SENSOR_SPECS:
            sensor = session.get(Sensor, sensor_id)
            if sensor is None:
                sensor = Sensor(
                    id=sensor_id,
                    name=name,
                    sensor_type=type_map[stype],
                    device_id=PI_DEVICE_ID,
                    threshold=threshold,
                    unit=unit,
                    is_active=True,
                )
                session.add(sensor)
                logger.info("Seeded sensor id=%s (%s)", sensor_id, name)
            else:
                sensor.name = name
                sensor.sensor_type = type_map[stype]
                sensor.device_id = PI_DEVICE_ID
                sensor.threshold = threshold
                sensor.unit = unit
                sensor.is_active = True
                session.add(sensor)

        session.commit()


def _migrate_sensor_live_columns() -> None:
    """Rename last_value/last_timestamp — PostgreSQL treats last_value as a window function."""
    try:
        insp = inspect(engine)
        if "sensor" not in insp.get_table_names():
            return
        existing = {c["name"] for c in insp.get_columns("sensor")}
    except Exception as exc:
        logger.warning("Could not inspect sensor table for migrations: %s", exc)
        return

    renames = (
        ("last_value", "current_value"),
        ("last_timestamp", "current_reading_at"),
    )
    for old_name, new_name in renames:
        if old_name in existing and new_name not in existing:
            stmt = f'ALTER TABLE sensor RENAME COLUMN "{old_name}" TO {new_name}'
            try:
                with engine.begin() as conn:
                    conn.execute(text(stmt))
                logger.info('Renamed sensor column "%s" → "%s"', old_name, new_name)
                existing.discard(old_name)
                existing.add(new_name)
            except Exception as exc:
                logger.error('Failed to rename sensor column "%s": %s', old_name, exc)

    for col_name, col_type in (
        ("current_value", "DOUBLE PRECISION"),
        ("current_reading_at", "TIMESTAMP"),
    ):
        if col_name not in existing:
            stmt = f"ALTER TABLE sensor ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
            try:
                with engine.begin() as conn:
                    conn.execute(text(stmt))
                logger.info('Added sensor column "%s"', col_name)
            except Exception as exc:
                logger.error('Failed to add sensor column "%s": %s', col_name, exc)


def init_db():
    """Initialize database tables"""
    SQLModel.metadata.create_all(engine)
    _migrate_user_notification_columns()
    _migrate_sensor_live_columns()
    _backfill_user_notification_defaults()
    try:
        seed_pi_sensors_and_device()
    except Exception as exc:
        logger.error("Pi sensor seed failed: %s", exc)


def get_session():
    """Dependency for getting database session"""
    with Session(engine) as session:
        yield session
