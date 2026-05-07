# Pi Live Stream + AI Runtime Setup

This setup runs one process that owns the camera and does both:
- AI detection + MQTT/backend publishing
- MJPEG live stream on `/video_feed`

## 1) Run manually (single camera owner)

```bash
cd /home/pi/smart_fire_system/integration
python3 /home/pi/smart_fire_system/integration/smart_fire_main.py
```

Do not run `video_stream_server.py` at the same time.

## 2) Verify stream from laptop

- `http://raspberrypi.local:5000/health`
- `http://raspberrypi.local:5000/video_feed`

IP fallback:
- `http://<pi-ip>:5000/health`
- `http://<pi-ip>:5000/video_feed`

## 3) Backend stream row

Create or update backend stream URL to:

`http://raspberrypi.local:5000/video_feed`

Then use backend proxy:

`GET /api/video/streams/{stream_id}/live`

## 4) Enable auto-start service (recommended)

Copy to Pi:
- `pi content/raspberry_pi_examples/systemd/fire-smart-runtime.service`
- `pi content/raspberry_pi_examples/systemd/install_fire_runtime_service.sh`

On Pi:

```bash
chmod +x ~/raspberry_pi_examples/systemd/install_fire_runtime_service.sh
~/raspberry_pi_examples/systemd/install_fire_runtime_service.sh
```

This disables old `fire-video-stream.service` and enables `fire-smart-runtime.service`.

## 5) Optional stream-only mode

If you only want standalone stream testing (no AI runtime), run:

```bash
python3 ~/raspberry_pi_examples/video_stream_server.py
```

Stop/disable smart runtime first in this mode.
