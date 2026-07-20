# Preview Deployment Runbook

This runbook deploys ACP Enterprise to `preview.allcountyhomeservices.com`. It is intentionally manual and conservative. Preview must use synthetic or sanitized data and must never connect to the production database.

## Architecture

```text
Browser
  → DigitalOcean firewall (80/443 only)
  → host Nginx with TLS
  → 127.0.0.1:8080
  → frontend Nginx container
      ├── static React application with SPA history fallback
      └── /api and /backend-health → FastAPI backend
          ├── private PostgreSQL container
          └── private Redis container
```

PostgreSQL, Redis, and FastAPI publish no host ports. Only frontend Nginx binds to the host loopback interface. The host reverse proxy is the only public application entry point.

## 1. DigitalOcean and DNS prerequisites

Create a dedicated Ubuntu LTS Droplet for preview. Do not reuse a production database server. Attach a DigitalOcean firewall allowing:

- TCP 22 from administrator IP addresses only.
- TCP 80 and 443 from the internet.
- No public PostgreSQL port 5432.
- No public Redis port 6379.

At the DNS provider, create an `A` record:

```text
Host: preview
Value: DROPLET_PUBLIC_IPV4_ADDRESS
TTL: 300
```

Wait for `dig +short preview.allcountyhomeservices.com` to return the Droplet address.

## 2. Initial server preparation

Connect using a non-root sudo user, update packages, and install Git, curl, Python 3, Nginx, Certbot, and the official Docker Engine with its Compose plugin. Follow DigitalOcean and Docker’s current Ubuntu installation instructions; do not use an unreviewed convenience script.

Verify tools:

```bash
git --version
docker --version
docker compose version
nginx -v
certbot --version
```

Allow the deployment user to run Docker, then sign out and back in:

```bash
sudo usermod -aG docker "$USER"
```

## 3. Repository checkout or update

Use a dedicated application directory:

```bash
sudo mkdir -p /opt/acp-enterprise
sudo chown "$USER":"$USER" /opt/acp-enterprise
git clone YOUR_APPROVED_REPOSITORY_URL /opt/acp-enterprise/app
cd /opt/acp-enterprise/app
git fetch --prune origin
git checkout YOUR_APPROVED_PREVIEW_BRANCH_OR_TAG
git pull --ff-only
```

Never deploy an unreviewed working tree. Confirm `git status --short` is empty and record `git rev-parse HEAD` in the deployment log.

## 4. Preview environment

Create the ignored runtime file:

```bash
cp .env.preview.example .env.preview
chmod 600 .env.preview
```

Generate three independent secrets. Do not paste the output into chat, tickets, or shell history:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
```

Edit the file locally on the server:

```bash
nano .env.preview
```

Replace every `REPLACE_...` placeholder. Use one value for `POSTGRES_PASSWORD`, its URL-encoded equivalent in `DATABASE_URL`, one signing key inside `ACCESS_TOKEN_KEYS`, and a different HMAC key. Keep CORS restricted to `https://preview.allcountyhomeservices.com`.

Validate Compose interpolation without printing resolved configuration into shared logs:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml config --quiet
```

## 5. Build and migrate

Build immutable application images:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml build --pull
```

Start the database and Redis first:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml up -d postgres redis
docker compose --env-file .env.preview -f docker-compose.preview.yml ps
```

Back up an existing preview database before every migration. For an initial empty database, run the forward migration service:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml run --rm migrate
```

Confirm the migration is at head:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml run --rm migrate alembic current
```

Then start the application. Compose also refuses to start the backend unless its migration dependency succeeds:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml up -d
docker compose --env-file .env.preview -f docker-compose.preview.yml ps
```

Do not use `docker compose down -v`; it deletes named database storage.

## 6. Host reverse proxy and TLS

Create `/etc/nginx/sites-available/acp-preview`:

```nginx
server {
    listen 80;
    server_name preview.allcountyhomeservices.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and validate it:

```bash
sudo ln -s /etc/nginx/sites-available/acp-preview /etc/nginx/sites-enabled/acp-preview
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d preview.allcountyhomeservices.com
sudo nginx -t
```

Confirm Certbot installed automatic certificate renewal:

```bash
sudo systemctl status certbot.timer
sudo certbot renew --dry-run
```

## 7. Health and application verification

Run the safe repository verification script:

```bash
PREVIEW_URL=https://preview.allcountyhomeservices.com \
  sh scripts/verify-preview.sh .env.preview
```

Manual checks:

```bash
curl --fail --silent --show-error https://preview.allcountyhomeservices.com/healthz
curl --fail --silent --show-error https://preview.allcountyhomeservices.com/backend-health
curl --head https://preview.allcountyhomeservices.com/mission-control
curl --head https://preview.allcountyhomeservices.com/customers
```

Open the site in a private browser window. Verify Mission Control, Customers, theme switching, direct route reloads, and the browser console. Authentication verification must use a dedicated preview account: log in, confirm `/api/v1/auth/session`, refresh once, log out, and confirm the revoked session cannot refresh. Never weaken authentication or expose development recovery tokens; `ENVIRONMENT=preview` prevents those tokens from being returned.

## 8. Logs and restart

Inspect logs without printing environment variables:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml logs --tail=200 backend frontend migrate
```

Restart application containers without touching data volumes:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml restart backend frontend
sh scripts/verify-preview.sh .env.preview
```

## 9. Backups

Before upgrades, create a restricted backup directory and dump PostgreSQL:

```bash
mkdir -p /opt/acp-enterprise/backups
chmod 700 /opt/acp-enterprise/backups
docker compose --env-file .env.preview -f docker-compose.preview.yml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  > "/opt/acp-enterprise/backups/preview-$(date +%Y%m%d-%H%M%S).dump"
chmod 600 /opt/acp-enterprise/backups/*.dump
```

Copy backups to encrypted storage outside the Droplet and periodically test restoration into a disposable database.

## 10. Rollback

Application rollback is image-and-code rollback, not a destructive database reset:

1. Record the current commit and take a database backup.
2. Check out the previously approved tag or commit.
3. Rebuild images.
4. Review whether the previous application is compatible with the current schema.
5. Start the previous application images and run verification.

```bash
git fetch --prune origin
git checkout PREVIOUS_APPROVED_TAG_OR_COMMIT
docker compose --env-file .env.preview -f docker-compose.preview.yml build
docker compose --env-file .env.preview -f docker-compose.preview.yml up -d --no-deps backend frontend
sh scripts/verify-preview.sh .env.preview
```

Alembic downgrade is not an automatic rollback mechanism. Only run a downgrade after database-owner review, a tested rollback plan, and a verified backup.

## 11. Troubleshooting

- **Compose reports a missing variable:** compare `.env.preview` with `.env.preview.example`; do not bypass required secrets.
- **Backend will not start:** inspect `migrate` and `backend` logs, then run `alembic current` in the backend container.
- **Health is degraded:** check PostgreSQL and Redis health before restarting the backend.
- **Direct links return 404:** confirm host Nginx proxies all paths and container Nginx uses `try_files ... /index.html`.
- **Forwarding headers are rejected:** confirm traffic reaches FastAPI through the fixed `172.30.0.0/24` preview network and do not broaden trusted CIDRs without review.
- **CORS failure:** confirm the browser origin exactly matches `CORS_ALLOWED_ORIGINS`; never use `*` with credentials.
- **TLS or HSTS issue:** validate the certificate and host proxy before exposing the domain.
- **Port 8080 is unavailable:** select another loopback port in `.env.preview` and update host Nginx accordingly.

Stopping containers without deleting data is safe:

```bash
docker compose --env-file .env.preview -f docker-compose.preview.yml stop
```

Never add `-v` to `down` or manually remove the PostgreSQL volume during routine troubleshooting.
