# Network Profiles (Pi + Backend)

Use these profiles when you move the Pi between:
- same LAN as backend laptop
- different network (friend lab / remote)

## Files

- `pi_local_lan_config_snippet.py`
- `pi_remote_friend_config_snippet.py`
- `backend_local_lan_env_snippet.env`
- `backend_remote_friend_env_snippet.env`

## How to apply

### Pi
1. Open Pi file: `/home/pi/smart_fire_system/integration/smart_fire_system/config.py`
2. Replace the matching section with one of the `pi_*` snippets.
3. Restart runtime:
   - `sudo systemctl restart fire-smart-runtime.service`

### Backend laptop
1. Open backend file: `.env`
2. Copy values from one of the `backend_*` snippets.
3. Restart backend (`uvicorn`).

## Notes

- `.local` hostnames work only on same LAN with mDNS.
- Cross-network requires public/tunneled URLs (ngrok/cloudflared/etc).
- Replace placeholders before use.
