from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://user:password@localhost:5432/fire_detection_db"
    
    # JWT
    secret_key: str = "your-secret-key-here-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # MQTT
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_topic_sensors: str = "sensors/#"
    mqtt_topic_camera: str = "camera/#"
    mqtt_topic_arm: str = "arm/#"
    
    # Serial (for arm control)
    serial_port: str = "COM3"
    serial_baudrate: int = 9600
    
    # AI Models
    ai_model_risk_detection_url: str = "http://localhost:8001/api/detect-risk"
    ai_model_fire_location_url: str = "http://localhost:8002/api/locate-fire"
    ai_model_api_key: Optional[str] = None
    
    # Video Streaming
    video_stream_port: int = 8080
    video_upload_dir: str = "./uploads/videos"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

