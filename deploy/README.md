# Bookverse deployment

Single ASGI process (Gunicorn + UvicornWorker) serves both the REST API and the
audio WebSocket. Object storage is **Cloudflare R2** (S3-compatible, off-box).

## VPS (Ubuntu 24.04 / 26.04, Debian 12)

```bash
sudo bash deploy/install.sh      # first run seeds /opt/bookverse/.env and stops
# fill in /opt/bookverse/.env with real secrets, then:
sudo bash deploy/install.sh      # provisions everything (idempotent)
sudo certbot --nginx -d bookverse.api.ecode2.com
sudo bash deploy/restart.sh      # health-checked restart + status table
```

The first run deliberately exits after writing `.env` — provisioning Postgres
with the `.env.example` placeholders would leave their credentials
permanently out of sync with the real ones you fill in afterwards.

### Python version

Runs on the distro `python3`: 3.12 on Ubuntu 24.04, **3.14 on Ubuntu 26.04**.
Django is held at the **5.2 LTS** series, which supports 3.10–3.14 and is
security-supported until April 2028. Every dependency is pinned to a version
with prebuilt wheels for those interpreters — if `pip` starts compiling C or
Rust during install, a pin has drifted and should be bumped rather than
worked around by installing compilers.

`install.sh` installs Postgres, Redis (capped at 64 MB), Nginx, the venv, runs migrations +
collectstatic, and installs the systemd units and Nginx site. `restart.sh`
self-heals a missing Postgres, refuses to restart the app on a bad Nginx config,
and prints a per-service status table (non-zero exit if anything is down).

## Text-to-Speech credentials

The default provider is **NVIDIA**. Choose:

- **NVIDIA** (`TTS_PROVIDER=nvidia`, the default): get a free API key from
  [build.nvidia.com](https://build.nvidia.com) ("Get API Key" on any model
  page) and set `NVIDIA_API_KEY` in `.env`. NVIDIA's hosted TTS models are
  served over **gRPC**, not a REST/OpenAI-style API, and each model is picked
  by a **function-id** (a UUID on the model's page) rather than a model name —
  set `NVIDIA_TTS_FUNCTION_ID` plus a matching `TTS_DEFAULT_VOICE` to switch
  models. Defaults to Magpie-TTS Multilingual.
- **Google** (`TTS_PROVIDER=google`): this VPS is not on GCP, so there is no
  metadata-server service account. Create a service account with the
  *Cloud Text-to-Speech API User* role, enable the API, download the JSON key to
  `/opt/bookverse/gcp-tts.json` (outside the repo) and set
  `GOOGLE_APPLICATION_CREDENTIALS` in `.env`.
- **Piper** (`TTS_PROVIDER=piper`): fully local, no billing. Install the `piper`
  binary + a voice model and set `PIPER_BINARY` / `PIPER_MODEL_PATH`.
- **Dummy** (`TTS_PROVIDER=dummy`): silent audio, for dev/testing offline.

Synthesized audio is content-addressed and cached in R2, so identical
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
