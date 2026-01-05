# Entity Relationship Diagram (ERD)

## Fire Detection System Database Schema

```mermaid
erDiagram
    User ||--o{ Alert : "has"
    Device ||--o{ Sensor : "contains"
    Device ||--o{ VideoStream : "has"
    Sensor ||--o{ SensorReading : "generates"
    Alert }o--|| User : "belongs to"
    Alert }o--o| Sensor : "references"
    Alert }o--o| Device : "references"
    Alert }o--o| FireEvent : "references"
    VideoStream }o--|| Device : "belongs to"
    Sensor }o--|| Device : "belongs to"
    SensorReading }o--|| Sensor : "belongs to"

    User {
        int id PK
        string email UK
        string username UK
        string hashed_password
        string full_name
        bool is_active
        bool is_superuser
        datetime created_at
        datetime updated_at
    }

    Device {
        int id PK
        string name
        string device_type
        string status
        string location
        string mqtt_topic
        string serial_port
        string ip_address
        datetime last_seen
        datetime created_at
        datetime updated_at
    }

    Sensor {
        int id PK
        string name
        string sensor_type
        int device_id FK
        float threshold
        string unit
        bool is_active
        datetime created_at
        datetime updated_at
    }

    SensorReading {
        int id PK
        int sensor_id FK
        float value
        datetime timestamp
    }

    Alert {
        int id PK
        string alert_type
        string status
        string title
        string message
        int severity
        int user_id FK
        int sensor_id
        int device_id
        int fire_event_id
        datetime created_at
        datetime acknowledged_at
        datetime resolved_at
    }

    FireEvent {
        int id PK
        string status
        string location
        float angle
        float x_coordinate
        float y_coordinate
        float confidence
        float temperature
        int device_id
        int camera_id
        string video_url
        datetime detected_at
        datetime confirmed_at
        datetime suppressed_at
        datetime created_at
        datetime updated_at
    }

    VideoStream {
        int id PK
        int device_id FK
        string stream_url
        bool is_active
        string resolution
        int fps
        datetime created_at
        datetime updated_at
    }
```

## Entity Descriptions

### User
Stores user account information including authentication credentials and profile data. Users can receive alerts.

### Device
Represents physical devices in the system (sensors, cameras, robotic arms, Raspberry Pi units). Tracks device status, location, and connectivity information.

### Sensor
Individual sensors attached to devices. Each sensor has a specific type (temperature, smoke, flame, gas, humidity) and can have threshold values for triggering alerts.

### SensorReading
Time-series data from sensors. Stores individual readings with timestamps for historical analysis.

### Alert
System alerts and notifications. Can be triggered by sensors, devices, or fire events. Alerts can be assigned to users and tracked through their lifecycle (pending → acknowledged → resolved).

### FireEvent
Records fire detection events with location coordinates, confidence scores, and status tracking through the fire suppression process.

### VideoStream
Video stream configurations for camera devices. Stores stream URLs and technical parameters like resolution and FPS.

## Enum Values Reference

### Device.device_type
- `sensor`
- `camera`
- `arm`
- `raspberry_pi`

### Device.status
- `online`
- `offline`
- `error`
- `maintenance`

### Sensor.sensor_type
- `temperature`
- `smoke`
- `flame`
- `gas`
- `humidity`

### Alert.alert_type
- `fire_detected`
- `high_temperature`
- `smoke_detected`
- `device_offline`
- `system_error`

### Alert.status
- `pending`
- `acknowledged`
- `resolved`
- `false_alarm`

### FireEvent.status
- `detected`
- `confirmed`
- `suppressing`
- `suppressed`
- `false_alarm`

## Relationships

- **User ↔ Alert**: One-to-Many (a user can have multiple alerts)
- **Device ↔ Sensor**: One-to-Many (a device can have multiple sensors)
- **Device ↔ VideoStream**: One-to-Many (a device can have multiple video streams)
- **Sensor ↔ SensorReading**: One-to-Many (a sensor generates multiple readings over time)
- **Alert ↔ User**: Many-to-One (alerts can optionally belong to a user)
- **Alert ↔ Sensor/Device/FireEvent**: Many-to-One (alerts can reference sensors, devices, or fire events)

