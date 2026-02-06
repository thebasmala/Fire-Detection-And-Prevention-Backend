# Fire Detection and Prevention Backend

A FastAPI-based backend system for fire detection and prevention with MQTT integration, AI model support, real-time notifications, and live video streaming.

## Features

- Real-time fire detection and monitoring
- MQTT integration for hardware devices (sensors, camera, arm)
- AI model integration for risk detection and fire location
- Live video streaming support
- Real-time notifications
- JWT-based authentication
- RESTful API for management website
- PostgreSQL database with SQLModel ORM

## Hardware Components

- **Sensors**: Fire detection sensors connected via MQTT
- **Camera**: Integrated with Raspberry Pi, streams via MQTT
- **Arm**: Fire suppression arm controlled via serial connection
- **Raspberry Pi**: Main hardware controller

## AI Models

1. **High-Risk Device Detection**: Detects devices with high fire risk
2. **Fire Location Detection**: Locates fire angle and position

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   Create a `.env` file in the project root (see `guides/SETUP.md` for all available options)

3. **Set up PostgreSQL database**:
   ```bash
   createdb fire_detection_db
   ```

4. **Start the server**:
   ```bash
   uvicorn app.main:app --reload
   ```

## API Documentation

Once the server is running, access:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration settings
│   ├── database.py          # Database connection
│   ├── models/              # SQLModel models
│   ├── schemas/             # Pydantic schemas
│   ├── api/                 # API routers
│   ├── core/                # Core functionality
│   │   ├── security.py      # JWT authentication
│   │   ├── mqtt_client.py    # MQTT client
│   │   └── serial_client.py # Serial communication
│   └── services/            # Business logic
├── requirements.txt
├── .env (create this file - see guides/SETUP.md)
└── README.md
```

## Environment Variables

See `guides/SETUP.md` for all available configuration options and how to set up your `.env` file.

