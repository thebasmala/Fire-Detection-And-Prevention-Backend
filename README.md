# Smart Fire System — Backend API

FastAPI backend for a smart fire detection and prevention platform. It connects Raspberry Pi cameras and sensors (via MQTT), stores events in PostgreSQL, pushes real-time updates over WebSocket, and sends email, SMS, and push notifications when alerts exceed a confidence threshold.

**Production API:** [https://api.smartfiresystem.me](https://api.smartfiresystem.me)  
**Interactive docs:** [https://api.smartfiresystem.me/docs](https://api.smartfiresystem.me/docs)

---

## What it does

| Area | Description |
|------|-------------|
| **Fire & device detection** | Receives MQTT events from the Pi (camera + Hailo), saves fire events, uploads frames to Cloudinary |
| **Sensors** | 8 sensors (4× temperature, 4× MQ2 gas) on device 1 — MQTT `sensors/{id}` → DB → live API + WebSocket |
| **Alerts** | Creates alerts, resolves them via API, broadcasts `alert_created` / `alert_updated` |
| **Auth** | Register, login (form + JSON), JWT + HttpOnly cookie, session bootstrap for clients |
| **Notifications** | SendGrid email, Twilio SMS, Firebase FCM (configurable per user) |
| **Real-time** | WebSocket feed for dashboards and Flutter (`/api/realtime/ws`) |

Clients (web dashboard, Flutter) use **REST + WebSocket only** — they do not talk to MQTT directly.

---

## Architecture

```
Raspberry Pi (camera, Arduino sensors)
        │  MQTT (HiveMQ Cloud)
        │  HTTPS (frame uploads)
        ▼
   FastAPI Backend  ──►  PostgreSQL
        │
        ├── WebSocket  ──►  Web / Flutter apps
        ├── SendGrid / Twilio / FCM
        └── Cloudinary (frame images)
```

Pi integration code lives under `pi content/integration/`. The Pi publishes fire events and sensor readings to MQTT and uploads JPEG frames to this API.

---

## Tech stack

- **Python 3.12** (see `.python-version`)
- **FastAPI** + **Uvicorn**
- **SQLModel** / **PostgreSQL**
- **Paho MQTT** (subscriber)
- **JWT** auth (Bearer + cookie)
- **Cloudinary**, **SendGrid**, **Twilio**, **Firebase Admin** (optional)

---

## Project layout

```
app/
  main.py              # App entry, MQTT handlers, lifespan
  api/                 # REST routes (auth, alerts, sensors, …)
  core/                # MQTT client, WebSocket, security
  models/              # Database models
  services/            # Notifications, realtime dispatch, storage
pi content/
  integration/         # Raspberry Pi runtime (fire detection + sensors)
guides/
  client_integration_guide.md   # For web & Flutter teams
```

---

## Local development

### Prerequisites

- Python 3.12
- PostgreSQL
- MQTT broker (e.g. HiveMQ Cloud) for Pi-style testing

### Setup

```bash
git clone https://github.com/thebasmala/smart-fire-system-backend.git
cd smart-fire-system-backend

python -m venv env
# Windows: env\Scripts\activate
# Linux/macOS: source env/bin/activate

pip install -r requirements.txt
```

Create a `.env` file in the project root. Minimum variables:

```env
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/fire_detection_db
SECRET_KEY=change-me-to-a-long-random-string
DEBUG=true

# MQTT (match Pi / HiveMQ)
MQTT_BROKER_HOST=your-broker.hivemq.cloud
MQTT_BROKER_PORT=8883
MQTT_USERNAME=...
MQTT_PASSWORD=...

# Optional but recommended for full features
PUBLIC_API_BASE_URL=http://localhost:8000
FIRE_FRAME_UPLOAD_API_KEY=your-shared-upload-key
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

### Run

```bash
python run.py
# or
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

On startup the app creates tables, runs light migrations, and seeds **device 1** with **sensors 1–8** (temp threshold 60°C, MQ2 threshold 1000 ppm).

---

## Production (Railway)

Deploy from this repo. **Recommended:** use the included **`Dockerfile`** (Railway auto-detects it) — installs Python 3.12.8 from Docker Hub and avoids Railpack/mise downloading from GitHub (common `504 Gateway Timeout` failure).

If you use **Railpack** instead, Python is pinned to **3.12.8** via `.python-version`, `runtime.txt`, and `railpack.json`. Set `RAILPACK_PYTHON_VERSION=3.12.8` if the build still picks another version.

- **PostgreSQL** plugin linked → `DATABASE_URL`

Important environment variables:

```env
DEBUG=false
AUTH_COOKIE_SECURE=true
PUBLIC_API_BASE_URL=https://api.smartfiresystem.me
CORS_ORIGINS=https://api.smartfiresystem.me,https://smartfiresystem.me
SECRET_KEY=...
DATABASE_URL=...          # from Railway Postgres
FIRE_FRAME_UPLOAD_API_KEY=...   # same as Pi SMART_FIRE_FRAME_KEY
```

Pi `mqtt.env` should set:

```env
SMART_FIRE_BACKEND_URL=https://api.smartfiresystem.me
SMART_FIRE_FRAME_KEY=<same as FIRE_FRAME_UPLOAD_API_KEY>
```

---

## API overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Login (form — Swagger / web) |
| POST | `/api/auth/login/json` | Login (JSON — Flutter) |
| POST | `/api/auth/register` | Create account |
| GET | `/api/auth/session` | Session bootstrap (user, URLs, prefs) |
| GET | `/api/alerts` | List alerts |
| GET | `/api/sensors/live` | Live sensor values |
| GET | `/health` | Health check |
| WS | `/api/realtime/ws` | Real-time alerts + sensors |

Full request/response shapes and client examples are in the integration guide below.

### MQTT topics (Pi → backend)

| Topic | Payload |
|-------|---------|
| `camera/pi` | Fire / risky device detection JSON |
| `sensors/{id}` | `{"sensor_id":1,"device_id":1,"value":35.5,"unit":"C"}` |

Sensor updates are throttled to **once per minute per sensor**.

---

## Client apps (web & Flutter)

See **[guides/client_integration_guide.md](guides/client_integration_guide.md)** for:

- Login flows (form vs JSON)
- WebSocket messages (`alert_created`, `sensor_reading`)
- FCM token registration
- Sensor dashboard bootstrap (`GET /api/sensors/live`)
- Vite dev proxy setup (`api.smartfiresystem.me`, not the apex domain)

---

## Testing MQTT sensors manually

```bash
mosquitto_pub -h YOUR_BROKER -p 8883 --tls-use-os-certs \
  -u USER -P 'PASS' \
  -t "sensors/1" \
  -m '{"sensor_id":1,"device_id":1,"value":35.5,"unit":"C"}'
```

Use the **`value`** field (not `temperature` / `humidity`). Wait 60 seconds between publishes for the same sensor.

---

## License

Private / academic project — contact the repository owner for usage terms.
