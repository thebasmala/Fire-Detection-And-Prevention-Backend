import logging
import serial
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)


class SerialClient:
    def __init__(self):
        self.serial_connection: Optional[serial.Serial] = None
        self.is_connected = False
    
    def connect(self) -> bool:
        """Connect to serial port"""
        try:
            self.serial_connection = serial.Serial(
                port=settings.serial_port,
                baudrate=settings.serial_baudrate,
                timeout=1
            )
            self.is_connected = True
            logger.info(f"Connected to serial port {settings.serial_port}")
            return True
        except serial.SerialException as e:
            logger.error(f"Error connecting to serial port: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """Disconnect from serial port"""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            self.is_connected = False
            logger.info("Disconnected from serial port")
    
    def send_command(self, command: str) -> bool:
        """Send a command to the arm via serial"""
        if not self.is_connected or not self.serial_connection:
            logger.warning("Serial connection not available")
            return False
        
        try:
            self.serial_connection.write(command.encode())
            logger.info(f"Sent command to arm: {command}")
            return True
        except Exception as e:
            logger.error(f"Error sending command to arm: {e}")
            return False
    
    def read_response(self) -> Optional[str]:
        """Read response from serial port"""
        if not self.is_connected or not self.serial_connection:
            return None
        
        try:
            if self.serial_connection.in_waiting > 0:
                response = self.serial_connection.readline().decode().strip()
                return response
        except Exception as e:
            logger.error(f"Error reading from serial port: {e}")
        return None
    
    def activate_arm(self) -> bool:
        """Activate the fire suppression arm"""
        return self.send_command("ACTIVATE")
    
    def deactivate_arm(self) -> bool:
        """Deactivate the fire suppression arm"""
        return self.send_command("DEACTIVATE")
    
    def move_arm(self, angle: float, x: float, y: float) -> bool:
        """Move arm to specific position"""
        command = f"MOVE {angle} {x} {y}"
        return self.send_command(command)


# Global serial client instance
serial_client = SerialClient()

