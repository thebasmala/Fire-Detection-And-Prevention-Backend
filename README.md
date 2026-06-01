# Fire Detection and Prevention Backend

FastAPI backend for fire detection: MQTT ingest (Pi), PostgreSQL, real-time WebSocket alerts, Cloudinary frames, and automated notifications (email, SMS/MMS, FCM).

## Quick start

```bash
pip install -r requirements.txt
# Configure .env — see guides/SETUP.md
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **API docs:** `http://localhost:8000/docs`
- **Health:** `http://localhost:8000/health`
- **Client integration (Flutter + web):** [guides/CLIENT_INTEGRATION.md](guides/CLIENT_INTEGRATION.md)

## Automated client access (no manual tokens)

End users only **log in** (username + password). The server handles everything else:

| What | How |
|------|-----|
| **Web dashboard** | `POST /api/auth/login` → HttpOnly cookie → all REST + WebSocket with `credentials: 'include'` (no JWT copy/paste) |
| **Flutter** | `POST /api/auth/login/json` → store `access_token` + `session` object (URLs, thresholds, prefs) |
| **FCM push** | App passes `fcm_token` from Firebase SDK in login JSON (or `PUT /api/auth/me/fcm-token` on refresh) — users never type it |
| **Pi frames** | `SMART_FIRE_FRAME_KEY` in Pi env only (ops), not in the mobile app |

Login/register responses include a **`session`** bootstrap: user profile, notification prefs, realtime thresholds, and full endpoint URLs.

## Features

- MQTT: sensors, camera/fire events, arm
- Alerts → WebSocket (all clients) + optional email / SMS-MMS / FCM (high confidence)
- Cloudinary or local `/static` frame URLs
- JWT + cookie auth, role-ready user model
- Pi integration: `pi content/integration/`

## Project layout

```
app/
  api/          REST + WebSocket
  core/         auth, MQTT, storage
  services/     notifications, FCM, outbound email/SMS
  models/       SQLModel tables
guides/         SETUP.md, CLIENT_INTEGRATION.md, FCM_SETUP.md
pi content/     Raspberry Pi runtime + MQTT helpers
```

## Environment

See [guides/SETUP.md](guides/SETUP.md) for all variables.

## Hardware

- Sensors, camera, suppression arm via MQTT
- Raspberry Pi runs detection + uploads frames to this API

## Docs for client teams

- [guides/CLIENT_INTEGRATION.md](guides/CLIENT_INTEGRATION.md) — login, WebSocket, FCM, images, zone
- [guides/FCM_SETUP.md](guides/FCM_SETUP.md) — Firebase Admin on server + Flutter hooks
