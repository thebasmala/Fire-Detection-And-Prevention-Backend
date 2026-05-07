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
    fire_event_min_confidence: float = 0.6
    
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
    fire_frames_upload_dir: str = "./uploads/fire_frames"
    # If set, Pi can upload frames with header X-Fire-Frame-Key: <value> (no JWT).
    fire_frame_upload_api_key: Optional[str] = None
    # Full public base URL for links returned to Pi (e.g. http://192.168.100.4:8000). If unset, request URL is used.
    public_api_base_url: Optional[str] = None
    
    # Data retention
    sensor_data_retention_days: int = 30
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    # Comma-separated allowed browser origins for production CORS
    # Example: "https://app.example.com,https://admin.example.com"
    cors_origins: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

