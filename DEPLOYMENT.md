# Deployment Guide

This guide covers deploying the Fire Detection and Prevention Backend to various free hosting platforms.

## Prerequisites

1. **GitHub Account**: Push your code to GitHub
2. **Database**: Set up PostgreSQL (most platforms offer free PostgreSQL)
3. **Environment Variables**: Prepare all your `.env` variables

## Option 1: Render (Recommended - Easiest)

### Steps:

1. **Push code to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin <your-github-repo-url>
   git push -u origin main
   ```

2. **Create Render Account**
   - Go to https://render.com
   - Sign up with GitHub

3. **Create Web Service**
   - Click "New" → "Web Service"
   - Connect your GitHub repository
   - Select your repository

4. **Configure Settings**
   - **Name**: `fire-detection-backend` (or your choice)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free

5. **Add Environment Variables**
   Click "Advanced" → "Add Environment Variable" and add:
   ```
   DATABASE_URL=postgresql://user:password@host:5432/dbname
   SECRET_KEY=your-secret-key-here
   MQTT_BROKER_HOST=your-mqtt-host
   # ... add all other variables from .env
   ```

6. **Add PostgreSQL Database**
   - Click "New" → "PostgreSQL"
   - Name it (e.g., `fire-detection-db`)
   - Copy the "Internal Database URL"
   - Update `DATABASE_URL` in your Web Service environment variables

7. **Deploy**
   - Click "Create Web Service"
   - Wait for deployment (5-10 minutes)
   - Your API will be available at `https://your-app-name.onrender.com`

### Render Notes:
- Free tier: 750 hours/month
- Service sleeps after 15 minutes of inactivity (first request may be slow)
- Automatic HTTPS
- Can upgrade to always-on for $7/month

---

## Option 2: Railway

### Steps:

1. **Push code to GitHub** (same as Render)

2. **Create Railway Account**
   - Go to https://railway.app
   - Sign up with GitHub

3. **Create New Project**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository

4. **Add PostgreSQL**
   - Click "+ New" → "Database" → "Add PostgreSQL"
   - Railway automatically sets `DATABASE_URL` environment variable

5. **Configure Environment Variables**
   - Click on your service
   - Go to "Variables" tab
   - Add all variables from your `.env` file
   - `DATABASE_URL` is already set by Railway

6. **Set Start Command**
   - Go to "Settings" → "Deploy"
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

7. **Deploy**
   - Railway auto-deploys on git push
   - Your API will be at `https://your-app-name.up.railway.app`

### Railway Notes:
- Free tier: $5 credit/month
- No sleep (always on)
- Automatic HTTPS
- Easy database management

---

## Option 3: Fly.io

### Steps:

1. **Install Fly CLI**
   ```bash
   # Windows (PowerShell)
   iwr https://fly.io/install.ps1 -useb | iex
   
   # Or download from https://fly.io/docs/getting-started/installing-flyctl/
   ```

2. **Login**
   ```bash
   fly auth login
   ```

3. **Initialize Project**
   ```bash
   fly launch
   ```
   - Follow prompts
   - Select region
   - Don't deploy yet (say no)

4. **Create fly.toml** (if not auto-generated)
   ```toml
   app = "your-app-name"
   primary_region = "iad"
   
   [build]
   
   [http_service]
     internal_port = 8000
     force_https = true
     auto_stop_machines = true
     auto_start_machines = true
     min_machines_running = 0
     processes = ["app"]
   
   [[services]]
     http_checks = []
     internal_port = 8000
     processes = ["app"]
     protocol = "tcp"
     script_checks = []
   
     [services.concurrency]
       type = "connections"
       hard_limit = 25
       soft_limit = 20
   
     [[services.ports]]
       force_https = true
       handlers = ["http"]
       port = 80
   
     [[services.ports]]
       handlers = ["tls", "http"]
       port = 443
   
     [[services.tcp_checks]]
       grace_period = "1s"
       interval = "15s"
       restart_limit = 0
       timeout = "2s"
   ```

5. **Create Dockerfile** (in project root)
   ```dockerfile
   FROM python:3.11-slim
   
   WORKDIR /app
   
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   
   COPY . .
   
   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```

6. **Add PostgreSQL**
   ```bash
   fly postgres create --name fire-detection-db
   fly postgres attach fire-detection-db
   ```

7. **Set Secrets**
   ```bash
   fly secrets set SECRET_KEY=your-secret-key
   fly secrets set MQTT_BROKER_HOST=your-mqtt-host
   # ... add all other secrets
   ```

8. **Deploy**
   ```bash
   fly deploy
   ```

### Fly.io Notes:
- Free tier: 3 shared VMs
- Automatic HTTPS
- Global edge network

---

## Option 4: PythonAnywhere

### Steps:

1. **Sign Up**
   - Go to https://www.pythonanywhere.com
   - Create free account

2. **Upload Code**
   - Go to "Files" tab
   - Upload your project files
   - Or use Git: `git clone <your-repo-url>`

3. **Install Dependencies**
   - Go to "Consoles" → "Bash"
   ```bash
   cd /home/yourusername/your-project
   pip3.10 install --user -r requirements.txt
   ```

4. **Create Web App**
   - Go to "Web" tab
   - Click "Add a new web app"
   - Select "Manual configuration" → "Python 3.10"
   - Click "Next" → "Next"

5. **Configure WSGI File**
   - Edit the WSGI file:
   ```python
   import sys
   path = '/home/yourusername/your-project'
   if path not in sys.path:
       sys.path.append(path)
   
   from app.main import app
   application = app
   ```

6. **Set Environment Variables**
   - In WSGI file or use `.env` file
   - Add to WSGI file:
   ```python
   import os
   os.environ['DATABASE_URL'] = 'your-database-url'
   os.environ['SECRET_KEY'] = 'your-secret-key'
   # ... etc
   ```

7. **Reload Web App**
   - Click "Reload" button

### PythonAnywhere Notes:
- Free tier: Limited resources
- Must reload manually after code changes
- Good for testing

---

## Environment Variables Checklist

Make sure to set these in your hosting platform:

```env
# Database (usually auto-set by platform)
DATABASE_URL=postgresql://...

# JWT
SECRET_KEY=your-strong-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# MQTT (if using)
MQTT_BROKER_HOST=your-mqtt-broker
MQTT_BROKER_PORT=1883
MQTT_USERNAME=...
MQTT_PASSWORD=...

# Serial (usually not needed in cloud)
SERIAL_PORT=COM3
SERIAL_BAUDRATE=9600

# AI Models
AI_MODEL_RISK_DETECTION_URL=...
AI_MODEL_FIRE_LOCATION_URL=...
AI_MODEL_API_KEY=...

# Server
HOST=0.0.0.0
PORT=8000  # Usually set by platform as $PORT
DEBUG=False  # Set to False in production!
```

---

## Production Checklist

Before deploying:

- [ ] Set `DEBUG=False` in production
- [ ] Use strong `SECRET_KEY` (generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
- [ ] Update CORS origins to your frontend domain
- [ ] Set up PostgreSQL database
- [ ] Configure MQTT broker (if needed)
- [ ] Test all endpoints
- [ ] Set up monitoring/logging
- [ ] Configure backups for database

---

## Quick Comparison

| Platform | Free Tier | Always On | PostgreSQL | Ease of Use |
|----------|-----------|-----------|------------|-------------|
| **Render** | 750 hrs/mo | No (sleeps) | Yes | ⭐⭐⭐⭐⭐ |
| **Railway** | $5 credit | Yes | Yes | ⭐⭐⭐⭐⭐ |
| **Fly.io** | 3 VMs | Yes | Yes | ⭐⭐⭐ |
| **PythonAnywhere** | Limited | Yes | No | ⭐⭐⭐ |

**Recommendation**: Start with **Render** for easiest setup, or **Railway** if you need always-on service.

---

## Post-Deployment

After deployment:

1. **Test your API**
   ```bash
   curl https://your-app-url.com/health
   ```

2. **Update Frontend**
   - Change API URL to your deployed URL
   - Update CORS settings if needed

3. **Monitor**
   - Check logs regularly
   - Set up error tracking (e.g., Sentry)

4. **Backup Database**
   - Set up regular backups
   - Export data periodically

