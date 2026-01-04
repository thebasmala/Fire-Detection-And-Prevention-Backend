# API Endpoints Reference

## Authentication (`/api/auth`)

### Register User
- **POST** `/api/auth/register`
- **Body**: `UserCreate` (email, username, password, full_name)
- **Response**: `UserRead`

### Login
- **POST** `/api/auth/login`
- **Body**: Form data (username, password)
- **Response**: `Token` (access_token, token_type)

### Get Current User
- **GET** `/api/auth/me`
- **Headers**: `Authorization: Bearer <token>`
- **Response**: `UserRead`

## Devices (`/api/devices`)

### Create Device
- **POST** `/api/devices`
- **Body**: `DeviceCreate`
- **Response**: `DeviceRead`

### Get All Devices
- **GET** `/api/devices?skip=0&limit=100`
- **Response**: `List[DeviceRead]`

### Get Device
- **GET** `/api/devices/{device_id}`
- **Response**: `DeviceRead`

### Update Device
- **PATCH** `/api/devices/{device_id}`
- **Body**: `DeviceUpdate`
- **Response**: `DeviceRead`

### Delete Device
- **DELETE** `/api/devices/{device_id}`
- **Response**: 204 No Content

### Update Device Status
- **POST** `/api/devices/{device_id}/update-status`
- **Body**: `DeviceStatus` enum
- **Response**: `DeviceRead`

## Sensors (`/api/sensors`)

### Create Sensor
- **POST** `/api/sensors`
- **Body**: `SensorCreate`
- **Response**: `SensorRead`

### Get All Sensors
- **GET** `/api/sensors?device_id=1&skip=0&limit=100`
- **Response**: `List[SensorRead]`

### Get Sensor
- **GET** `/api/sensors/{sensor_id}`
- **Response**: `SensorRead`

### Update Sensor
- **PATCH** `/api/sensors/{sensor_id}`
- **Body**: `SensorUpdate`
- **Response**: `SensorRead`

### Delete Sensor
- **DELETE** `/api/sensors/{sensor_id}`
- **Response**: 204 No Content

### Create Sensor Reading
- **POST** `/api/sensors/readings`
- **Body**: `SensorReadingCreate`
- **Response**: `SensorReadingRead`

### Get Sensor Readings
- **GET** `/api/sensors/{sensor_id}/readings?skip=0&limit=100`
- **Response**: `List[SensorReadingRead]`

## Alerts (`/api/alerts`)

### Get All Alerts
- **GET** `/api/alerts?status_filter=pending&skip=0&limit=100`
- **Response**: `List[AlertRead]`

### Get Alert
- **GET** `/api/alerts/{alert_id}`
- **Response**: `AlertRead`

### Create Alert
- **POST** `/api/alerts`
- **Body**: `AlertCreate`
- **Response**: `AlertRead`

### Update Alert
- **PATCH** `/api/alerts/{alert_id}`
- **Body**: `AlertUpdate`
- **Response**: `AlertRead`

### Acknowledge Alert
- **POST** `/api/alerts/{alert_id}/acknowledge`
- **Response**: `AlertRead`

### Resolve Alert
- **POST** `/api/alerts/{alert_id}/resolve`
- **Response**: `AlertRead`

## Fire Events (`/api/fire-events`)

### Get All Fire Events
- **GET** `/api/fire-events?status_filter=detected&skip=0&limit=100`
- **Response**: `List[FireEventRead]`

### Get Fire Event
- **GET** `/api/fire-events/{event_id}`
- **Response**: `FireEventRead`

### Create Fire Event
- **POST** `/api/fire-events`
- **Body**: `FireEventCreate`
- **Response**: `FireEventRead`

### Update Fire Event
- **PATCH** `/api/fire-events/{event_id}`
- **Body**: `FireEventUpdate`
- **Response**: `FireEventRead`

### Locate Fire (AI)
- **POST** `/api/fire-events/{event_id}/locate-fire`
- **Body**: Image file (multipart/form-data)
- **Response**: `FireEventRead`

### Suppress Fire
- **POST** `/api/fire-events/{event_id}/suppress`
- **Response**: `FireEventRead`
- **Note**: Activates fire suppression arm

## Video Streaming (`/api/video`)

### Create Video Stream
- **POST** `/api/video/streams`
- **Body**: `VideoStreamCreate`
- **Response**: `VideoStreamRead`

### Get All Video Streams
- **GET** `/api/video/streams?device_id=1`
- **Response**: `List[VideoStreamRead]`

### Get Video Stream
- **GET** `/api/video/streams/{stream_id}`
- **Response**: `VideoStreamRead`

### Stream Live Video
- **GET** `/api/video/streams/{stream_id}/live`
- **Response**: Video stream (video/mp4)

### Delete Video Stream
- **DELETE** `/api/video/streams/{stream_id}`
- **Response**: 204 No Content

## AI Models (`/api/ai`)

### Detect High-Risk Devices
- **POST** `/api/ai/detect-risk`
- **Body**: JSON object with device data
- **Response**: AI model response

### Locate Fire
- **POST** `/api/ai/locate-fire`
- **Body**: Image file (multipart/form-data)
- **Response**: `{"angle": float, "x": float, "y": float, "confidence": float}`

## System

### Root
- **GET** `/`
- **Response**: API information

### Health Check
- **GET** `/health`
- **Response**: System health status

