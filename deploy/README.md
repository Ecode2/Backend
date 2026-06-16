# Bookverse deployment

Single ASGI process (Gunicorn + UvicornWorker) serves both the REST API and the
audio WebSocket. Object storage is **MinIO** (S3-compatible) on the same VPS.

## VPS (Debian 12)

```bash
sudo bash deploy/install.sh      # provisions everything (idempotent)
# edit /opt/bookverse/.env with real secrets, then:
sudo systemctl restart bookverse
sudo certbot --nginx -d bookverse.api.ecode2.com
sudo bash deploy/restart.sh      # health-checked restart + status table
```

`install.sh` installs Postgres, Redis, MinIO, Nginx, the venv, runs migrations +
collectstatic, and installs the systemd units and Nginx site. `restart.sh`
self-heals a missing Postgres, refuses to restart the app on a bad Nginx config,
and prints a per-service status table (non-zero exit if anything is down).

## Text-to-Speech credentials (non-GCP VPS)

This VPS is not on GCP, so there is no metadata-server service account. Choose:

- **Google** (`TTS_PROVIDER=google`): create a service account with the
  *Cloud Text-to-Speech API User* role, enable the API, download the JSON key to
  `/opt/bookverse/gcp-tts.json` (outside the repo) and set
  `GOOGLE_APPLICATION_CREDENTIALS` in `.env`.
- **Piper** (`TTS_PROVIDER=piper`): fully local, no billing. Install the `piper`
  binary + a voice model and set `PIPER_BINARY` / `PIPER_MODEL_PATH`.
- **Dummy** (`TTS_PROVIDER=dummy`): silent audio, for dev/testing offline.

Synthesized audio is content-addressed and cached in MinIO, so identical
passages/voices are never re-billed; speed changes use client `playbackRate`.

## Frontend (Vercel)

Set these environment variables in the Vercel project:

```
NEXT_PUBLIC_API_BASE=https://bookverse.api.ecode2.com
NEXT_PUBLIC_WS_BASE=wss://bookverse.api.ecode2.com
```

The frontend keeps the **access token in memory** and sends `credentials:
"include"` so the httpOnly **refresh cookie** (`Domain=.ecode2.com`,
`SameSite=Lax`) is shared between `bookverse.ecode2.com` and the API subdomain.
For this to work end-to-end:

- `COOKIE_DOMAIN=.ecode2.com` on the backend
- `CORS_ALLOWED_ORIGINS=https://bookverse.ecode2.com` and
  `CORS_ALLOW_CREDENTIALS=True` (set automatically)
- both apps served over HTTPS (`REFRESH_COOKIE_SECURE=true`)

## Audio cache eviction (cron)

```bash
/opt/bookverse/venv/bin/python manage.py evict_audio_cache --budget-bytes 2147483648
```
