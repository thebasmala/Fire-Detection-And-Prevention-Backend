from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://user:password@localhost:5432/fire_detection_db"
    
    # JWT
    secret_key: str = "your-secret-key-here-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # Set true in production (HTTPS) so login cookie is Secure
    auth_cookie_secure: bool = False
    
    # MQTT
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_topic_sensors: str = "sensors/#"
    mqtt_topic_camera: str = "camera/#"
    mqtt_topic_arm: str = "arm/#"
    # WebSocket popup + email/SMS when linked confidence exceeds this (default 80%)
    high_confidence_threshold: float = 0.8
    high_confidence_notify_cooldown_seconds: int = 15
    # SendGrid / Twilio — missing credentials skip silently; recipients from User prefs
    sendgrid_api_key: Optional[str] = None
    sendgrid_from_email: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_from_number: Optional[str] = None
    # Firebase Admin SDK service account JSON path (FCM push)
    firebase_credentials_path: Optional[str] = None
    fire_event_min_confidence: float = 0.6
    device_event_min_confidence: float = 0.6
    risky_device_cooldown_seconds: int = 120
    
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
    frames_upload_dir: str = "./uploads/frames"
    # If set, Pi can upload frames with header X-Fire-Frame-Key: <value> (no JWT).
    fire_frame_upload_api_key: Optional[str] = None
    # FastAPI public URL for local /static frame links when Cloudinary is off (NOT the MJPEG stream URL).
    # Example: http://192.168.100.4:8000 — Pi upload uses request URL if unset.
    public_api_base_url: Optional[str] = None

    # Cloudinary (optional — if all three are set, frame uploads use Cloudinary)
    cloudinary_cloud_name: Optional[str] = None
    cloudinary_api_key: Optional[str] = None
    cloudinary_api_secret: Optional[str] = None
    
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

