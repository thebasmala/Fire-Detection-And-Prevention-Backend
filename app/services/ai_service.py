import httpx
import logging
from typing import Optional, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self):
        self.risk_detection_url = settings.ai_model_risk_detection_url
        self.fire_location_url = settings.ai_model_fire_location_url
        self.api_key = settings.ai_model_api_key
    
    async def detect_high_risk_devices(self, device_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call AI model to detect high-risk devices"""
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.risk_detection_url,
                    json=device_data,
                    headers=headers
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Error calling risk detection AI model: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in risk detection: {e}")
            return None
    
    async def locate_fire(self, image_data: bytes, metadata: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Call AI model to locate fire angle and position"""
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            files = {"image": image_data}
            data = metadata or {}
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.fire_location_url,
                    files=files,
                    data=data,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                
                # Expected response format: {"pan": float, "tilt": float, "confidence": float}
                # Or backward compatible: {"angle": float, "x": float, "y": float, "confidence": float}
                return result
        except httpx.HTTPError as e:
            logger.error(f"Error calling fire location AI model: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in fire location: {e}")
            return None


ai_service = AIService()

