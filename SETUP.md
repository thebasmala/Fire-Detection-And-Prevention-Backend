# Setup Guide

## Prerequisites

1. **Python 3.9+** installed
2. **PostgreSQL** database server running
3. **MQTT Broker** (e.g., Mosquitto) running (optional for development)
4. **Serial port** available for arm control (optional)

## Installation Steps

### 1. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/fire_detection_db

# JWT
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# MQTT
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_TOPIC_SENSORS=sensors/#
MQTT_TOPIC_CAMERA=camera/#
MQTT_TOPIC_ARM=arm/#

# Serial (for arm control)
SERIAL_PORT=COM3
SERIAL_BAUDRATE=9600

# AI Models
AI_MODEL_RISK_DETECTION_URL=http://localhost:8001/api/detect-risk
AI_MODEL_FIRE_LOCATION_URL=http://localhost:8002/api/locate-fire
AI_MODEL_API_KEY=

# Video Streaming
VIDEO_STREAM_PORT=8080
VIDEO_UPLOAD_DIR=./uploads/videos

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=True
```

### 4. Create Database

```bash
# Using psql
createdb fire_detection_db

# Or using SQL
psql -U postgres
CREATE DATABASE fire_detection_db;
```

### 5. Initialize Database Tables

The database tables will be automatically created when you first run the application.

### 6. Run the Application

```bash
python run.py
```

Or using uvicorn directly:

```bash
uvicorn app.main:app --reload
```

## API Documentation

Once the server is running:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## Testing the API

### 1. Register a User

```bash
curl -X POST "http://localhost:8000/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "username": "admin",
    "password": "admin123",
    "full_name": "Admin User"
  }'
```

### 2. Login

```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

### 3. Use the Token

```bash
curl -X GET "http://localhost:8000/api/devices" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## MQTT Message Formats

### Sensor Messages

Topic: `sensors/#`

```json
{
  "sensor_id": 1,
  "value": 75.5,
  "device_id": 1
}
```

### Camera Messages

Topic: `camera/#`

```json
{
  "device_id": 1,
  "image_data": "base64_encoded_image_string",
  "metadata": {
    "location": "Building A, Floor 2",
    "timestamp": "2024-01-01T12:00:00Z"
  }
}
```

### Arm Messages

Topic: `arm/#`

```json
{
  "device_id": 1,
  "status": "active",
  "position": {
    "angle": 45.0,
    "x": 100,
    "y": 200
  }
}
```

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration settings
│   ├── database.py          # Database connection
│   ├── models/              # SQLModel models
│   │   ├── user.py
│   │   ├── device.py
│   │   ├── sensor.py
│   │   ├── alert.py
│   │   ├── fire_event.py
│   │   └── video_stream.py
│   ├── schemas/             # Pydantic schemas
│   │   ├── user.py
│   │   ├── device.py
│   │   ├── sensor.py
│   │   ├── alert.py
│   │   ├── fire_event.py
│   │   └── video_stream.py
│   ├── api/                 # API routers
│   │   ├── auth.py
│   │   ├── devices.py
│   │   ├── sensors.py
│   │   ├── alerts.py
│   │   ├── fire_events.py
│   │   ├── video.py
│   │   └── ai.py
│   ├── core/                # Core functionality
│   │   ├── security.py      # JWT authentication
│   │   ├── mqtt_client.py   # MQTT client
│   │   └── serial_client.py # Serial communication
│   └── services/            # Business logic
│       ├── ai_service.py
│       └── notification_service.py
├── requirements.txt
├── run.py
├── .gitignore
└── README.md
```

## Troubleshooting

### Database Connection Issues

- Verify PostgreSQL is running: `pg_isready`
- Check database credentials in `.env`
- Ensure database exists

### MQTT Connection Issues

- Verify MQTT broker is running
- Check broker host and port in `.env`
- Test connection: `mosquitto_pub -h localhost -t test -m "hello"`

### Serial Port Issues

- Check if serial port exists: `python -m serial.tools.list_ports`
- Verify port name in `.env` (COM3 on Windows, /dev/ttyUSB0 on Linux)
- Ensure correct baudrate

### AI Model Integration

- Ensure AI model services are running
- Verify URLs in `.env` are correct
- Check API keys if required

