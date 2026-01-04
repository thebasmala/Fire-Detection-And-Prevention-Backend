from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.database import get_session
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.sensor import Sensor, SensorReading
from app.schemas.sensor import SensorCreate, SensorRead, SensorUpdate, SensorReadingCreate, SensorReadingRead

router = APIRouter(prefix="/sensors", tags=["Sensors"])


@router.post("", response_model=SensorRead, status_code=status.HTTP_201_CREATED)
async def create_sensor(
    sensor_data: SensorCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new sensor"""
    sensor = Sensor(**sensor_data.model_dump())
    session.add(sensor)
    session.commit()
    session.refresh(sensor)
    return sensor


@router.get("", response_model=List[SensorRead])
async def get_sensors(
    device_id: int = None,
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get all sensors, optionally filtered by device"""
    if device_id:
        statement = select(Sensor).where(Sensor.device_id == device_id).offset(skip).limit(limit)
    else:
        statement = select(Sensor).offset(skip).limit(limit)
    sensors = session.exec(statement).all()
    return sensors


@router.get("/{sensor_id}", response_model=SensorRead)
async def get_sensor(
    sensor_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific sensor"""
    sensor = session.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor


@router.patch("/{sensor_id}", response_model=SensorRead)
async def update_sensor(
    sensor_id: int,
    sensor_data: SensorUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Update a sensor"""
    sensor = session.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    
    update_data = sensor_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(sensor, field, value)
    
    from datetime import datetime
    sensor.updated_at = datetime.utcnow()
    session.add(sensor)
    session.commit()
    session.refresh(sensor)
    return sensor


@router.delete("/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sensor(
    sensor_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a sensor"""
    sensor = session.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    
    session.delete(sensor)
    session.commit()
    return None


@router.post("/readings", response_model=SensorReadingRead, status_code=status.HTTP_201_CREATED)
async def create_sensor_reading(
    reading_data: SensorReadingCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a sensor reading (typically called by MQTT handler)"""
    reading = SensorReading(**reading_data.model_dump())
    session.add(reading)
    session.commit()
    session.refresh(reading)
    return reading


@router.get("/{sensor_id}/readings", response_model=List[SensorReadingRead])
async def get_sensor_readings(
    sensor_id: int,
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get readings for a specific sensor"""
    statement = (
        select(SensorReading)
        .where(SensorReading.sensor_id == sensor_id)
        .offset(skip)
        .limit(limit)
        .order_by(SensorReading.timestamp.desc())
    )
    readings = session.exec(statement).all()
    return readings

