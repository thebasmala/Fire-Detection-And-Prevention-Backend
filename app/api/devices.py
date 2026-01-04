from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.database import get_session
from app.core.security import get_current_active_user
from app.models.user import User
from app.models.device import Device, DeviceStatus
from app.schemas.device import DeviceCreate, DeviceRead, DeviceUpdate
from datetime import datetime

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.post("", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
async def create_device(
    device_data: DeviceCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new device"""
    device = Device(**device_data.model_dump())
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


@router.get("", response_model=List[DeviceRead])
async def get_devices(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get all devices"""
    statement = select(Device).offset(skip).limit(limit)
    devices = session.exec(statement).all()
    return devices


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(
    device_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific device"""
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.patch("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: int,
    device_data: DeviceUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Update a device"""
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    update_data = device_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(device, field, value)
    
    device.updated_at = datetime.utcnow()
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a device"""
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    session.delete(device)
    session.commit()
    return None


@router.post("/{device_id}/update-status", response_model=DeviceRead)
async def update_device_status(
    device_id: int,
    status_update: DeviceStatus,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """Update device status"""
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    device.status = status_update
    device.last_seen = datetime.utcnow()
    device.updated_at = datetime.utcnow()
    session.add(device)
    session.commit()
    session.refresh(device)
    return device

