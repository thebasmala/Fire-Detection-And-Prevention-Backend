# Fire Detection and Prevention Backend

FastAPI backend: MQTT ingest (Pi), PostgreSQL, WebSocket alerts, Cloudinary frames, email/SMS/FCM notifications.

## Quick start

```bash
pip install -r requirements.txt
# Copy .env — see guides/SETUP.md
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Docs: http://localhost:8000/docs  
- Health: http://localhost:8000/health  

## Documentation

| Guide | Audience |
|-------|----------|
| [guides/PROJECT_STATUS.md](guides/PROJECT_STATUS.md) | Status + Railway checklist |
| [guides/CLIENT_INTEGRATION.md](guides/CLIENT_INTEGRATION.md) | Flutter + web teams |
| [guides/DEPLOYMENT.md](guides/DEPLOYMENT.md) | Railway deploy |
| [guides/SETUP.md](guides/SETUP.md) | Environment variables |

## Clients (no manual tokens)

- **Login:** `POST /api/auth/login` → `access_token` + `session` (URLs, prefs, thresholds).
- **Web:** HttpOnly cookie — use `credentials: 'include'`.
- **Flutter:** JSON login; app sends `fcm_token` from Firebase in code (user never types it).
- **Updates:** `GET/PATCH /api/auth/session` only.

## Deploy

`Procfile` is configured for Railway. See [guides/DEPLOYMENT.md](guides/DEPLOYMENT.md).

## Pi

`pi content/integration/` — set `SMART_FIRE_BACKEND_URL` to your API URL (port 8000, not video stream).
