# Deploying on the AWS free tier

Run the whole app on **one EC2 t3.micro** (1 GB RAM) next to your RDS database. OpenAI is the only
paid part. This is the setup in `docker-compose.free.yml`. Why it looks the way it does is in
[decision 0032](decisions/0032-free-tier-deployment.md).

```
Your laptop ──SSH tunnel (or HTTPS)──► EC2 t3.micro
                                        ├─ frontend (nginx)   127.0.0.1:8080
                                        ├─ backend  (API)     127.0.0.1:8000
                                        ├─ worker
                                        ├─ redis
                                        └─ volume "media"     photos, audio, uploads
                                              │
                                              ▼
                                       RDS PostgreSQL  ──►  OpenAI API
```

Compared with the standard setup:

| | Standard (`docker-compose.yml`) | Free tier (+ `docker-compose.free.yml`) |
|---|---|---|
| Sentiment model | included (about 1 GB of RAM per container) | **left out**: the image is built with `WITH_SENTIMENT=false` |
| Media files | DynamoDB (on-demand, not free) | **the server's disk**, in a Docker volume |
| Image size | about 2.5 GB | about 500 MB |
| After a crash or reboot | stays down | **restarts by itself** |

**What you lose:** the mood charts and the sentiment on evidence cards. Everything else works.

---

## Before you start

You need:

- An AWS account. Check **Billing → Free tier** to see what yours includes. Accounts with the
  classic free tier get 750 hours a month of t3.micro, 30 GB of EBS disk and RDS for 12 months.
  Newer accounts get credits instead.
- The RDS database from the main [README](../README.md#cloud-setup-openai--aws), in the same region
  you'll use for EC2.
- An OpenAI API key.
- `backend/.env` filled in and working locally.

---

## 1. Launch the server

In the EC2 console, choose **Launch instance**:

| Setting | Value |
|---|---|
| Region | the same as your RDS database |
| AMI | **Ubuntu Server 24.04 LTS** |
| Instance type | **t3.micro** |
| Key pair | create one (for example `memory`) and download the `.pem` file |
| Network | the **same VPC** as the RDS database (the default VPC, if you didn't create one) |
| Security group | allow **SSH (22) from My IP only**. Nothing else for now |
| Storage | **20–30 GB** gp3 (the free tier covers up to 30 GB). Docker images and your media live here |

Keep the `.pem` file out of the project folder, for example in `~/.ssh/memory.pem`. It's git-ignored
(`*.pem`), but it's safer not to keep keys inside a repository at all.

On macOS and Linux, protect the key or SSH will refuse it:

```bash
chmod 400 ~/.ssh/memory.pem
```

On Windows, OpenSSH uses the file as it is, as long as only your user can read it (right-click →
Properties → Security).

## 2. Let the server reach the database

In the RDS console, open your database → **Connectivity & security** → its security group →
**Edit inbound rules**, and add:

| Type | Port | Source |
|---|---|---|
| PostgreSQL | 5432 | the **EC2 instance's security group** (start typing `sg-`) |

Pointing the rule at the security group rather than an IP means it keeps working if the server's IP
changes. Once the server is the only thing that needs the database, you can remove the rule for your
laptop's IP and set **Public access: No**.

## 3. Prepare the server

Connect:

```bash
ssh -i ~/.ssh/memory.pem ubuntu@<server-public-ip>
```

**Add 2 GB of swap.** 1 GB of RAM isn't enough to *build* the images (the frontend build alone can
use more), and without swap the build gets killed. Running the app fits in 1 GB, and the swap is a
safety margin.

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
```

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**Install Docker, Compose and git:**

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
```

```bash
sudo usermod -aG docker ubuntu
```

Then log out (`exit`) and SSH in again, so the `docker` group applies.

```bash
docker compose version
```

## 4. Get the code and the settings

**The code**, from GitHub:

```bash
git clone https://github.com/Kavyaaves/MemoryEngine.git && cd MemoryEngine
```

If the repository is private, GitHub asks for a username and a **personal access token** (not your
password). Create one under GitHub → Settings → Developer settings → Fine-grained tokens, with
read-only access to this repository.

**The settings.** `backend/.env` is git-ignored, so copy it from your laptop. Run this **on your
laptop**, from the project folder:

```bash
scp -i ~/.ssh/memory.pem backend/.env ubuntu@<server-public-ip>:~/MemoryEngine/backend/.env
```

Then check these values in it, on the server (`nano backend/.env`):

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `SECRET_KEY` | a long random value. The app **refuses to start** in production with the default. Make one with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DATABASE_URL` | your RDS URL |
| `OPENAI_API_KEY` | your key |

You don't need to change `REDIS_URL`, `STORAGE_BACKEND` or `SENTIMENT_ENABLED`: the free-tier
Compose file sets them, and Compose's `environment` values override `.env`. The `AWS_*` keys aren't
used, because nothing talks to DynamoDB.

## 5. Build and start

```bash
docker compose -f docker-compose.yml -f docker-compose.free.yml up -d --build
```

The first build takes a while on a t3.micro. Later builds reuse cached layers and are much faster
([0031](decisions/0031-backend-docker-image.md)). The API runs the database migrations each time it starts.

Check that everything is up:

```bash
docker compose -f docker-compose.yml -f docker-compose.free.yml ps
```

```bash
curl -s http://127.0.0.1:8000/api/health
```

You should see `{"status":"ok","db":true,"redis":true}`. If `db` is `false`, see
[Troubleshooting](#troubleshooting).

Tip: to avoid typing both `-f` flags every time, put this line in `~/.bashrc` on the server:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.free.yml
```

After that, plain `docker compose up -d --build`, `docker compose ps` and `docker compose logs` use
both files. The commands below assume you've done this.

## 6. Open the app

Compose only listens on `127.0.0.1`: the app isn't reachable from the internet, on purpose. Choose
how you reach it.

### Option A: an SSH tunnel (recommended for personal use)

Nothing is exposed publicly. Only someone with your key can reach the app. On your laptop:

```bash
ssh -i ~/.ssh/memory.pem -N -L 8080:127.0.0.1:8080 ubuntu@<server-public-ip>
```

Leave it running, then open <http://localhost:8080> and register your account. Traffic is encrypted
by SSH, and the security group stays at port 22 from your IP only.

### Option B: your own domain with HTTPS

Use this if you want to open the app from any device without a tunnel.

> **Read this first.** Registration is **open**: anyone who can reach the site can create an account
> and use your OpenAI budget. Every account shares the token budget
> ([0016](decisions/0016-quota-guard-and-token-budget.md)), so spending is capped, but strangers
> could still use it all up. Register your own account first, and treat a public deployment as
> something to lock down before you share the address.

1. Point a DNS **A record** (for example `memories.example.com`) at the server's public IP. To keep
   the IP from changing, allocate an **Elastic IP** and attach it to the instance.
2. In the security group, allow **HTTP (80)** and **HTTPS (443)** from anywhere.
3. Install Caddy, a web server that gets and renews HTTPS certificates by itself:

   ```bash
   sudo apt-get install -y caddy
   ```

4. Replace `/etc/caddy/Caddyfile` with this (use your domain):

   ```
   memories.example.com {
       reverse_proxy 127.0.0.1:8080
   }
   ```

5. Reload it:

   ```bash
   sudo systemctl reload caddy
   ```

Open `https://memories.example.com`. Caddy passes streamed answers (Server-Sent Events) through
immediately, so Ask streams as it does locally.

Don't open port 8080 to the internet directly. That would send your password and login token
unencrypted.

---

## Updating

On the server:

```bash
cd ~/MemoryEngine && git pull && docker compose up -d --build
```

The API applies new migrations when it starts. Old image layers build up over time, so free the
disk now and then:

```bash
docker image prune -f
```

If you changed `backend/.env` on your laptop, copy it again with `scp` (step 4), then run
`docker compose up -d` so the containers pick it up.

## Backups

Two things hold your data. Back up both.

**The database:** in RDS, turn on **automated backups** (Modify → Backup retention period, for
example 7 days). RDS includes backup storage up to the size of your database at no extra cost.

**The media volume:** photos, audio and uploaded files are only on this server's disk. Compose names
the volume after the project folder, so check the name first:

```bash
docker volume ls
```

With the folder `MemoryEngine`, it's `memoryengine_media`. Archive it:

```bash
docker run --rm -v memoryengine_media:/data -v "$PWD":/backup alpine tar czf /backup/media-$(date +%F).tgz -C /data .
```

Then copy the archive off the server, **on your laptop**:

```bash
scp -i ~/.ssh/memory.pem "ubuntu@<server-public-ip>:~/MemoryEngine/media-*.tgz" .
```

A snapshot of the EC2 disk (EC2 → Volumes → Create snapshot) also works, and captures everything at once.

## Day-to-day commands

| To… | Run |
|---|---|
| see what's running | `docker compose ps` |
| follow the API's logs | `docker compose logs -f backend` |
| follow imports | `docker compose logs -f worker` |
| restart everything | `docker compose restart` |
| stop everything | `docker compose down` (the volumes and data stay) |
| check memory use | `free -h` and `docker stats --no-stream` |
| place old memories in the Memory Universe | `docker compose exec backend python -m app.universe` |
| embed anything missed | `docker compose exec backend python -m app.ai.embeddings` |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The build stops with `Killed` or exit code `137` | Out of memory. Add swap (step 3), then build again |
| `backend` keeps restarting with `SECRET_KEY must be set in production` | Set `SECRET_KEY` in `backend/.env`, then `docker compose up -d` |
| `/api/health` shows `"db": false`, or the logs say the database is unavailable | The RDS security group doesn't allow the server (step 2), `DATABASE_URL` is wrong, or a password symbol isn't URL-encoded (`@` → `%40`) |
| Answers are marked **degraded** | OpenAI isn't reachable: check `OPENAI_API_KEY`, your OpenAI billing, and the token budget in the AI Lab |
| An upload fails as too large | The app's limit is `MAX_UPLOAD_MB` (default 50). Split the export or raise it in `.env` |
| The mood charts are empty | Expected: sentiment is off in this setup |
| Photos are gone after re-creating the server | Media lives in the volume on that disk. Restore it from your backup |
| The SSH tunnel says `address already in use` | Something on your laptop already uses port 8080. Use `-L 8081:127.0.0.1:8080` and open `localhost:8081` |
| The disk is full | `docker image prune -f`, then check `df -h`. Grow the EBS volume if your media needs it |

## Costs to keep an eye on

- **OpenAI:** billed per token. The caps in `.env` (`MAX_TOKENS_PER_WINDOW`, `MAX_DAILY_REQUESTS`)
  limit it, and the AI Lab shows usage.
- **Public IPv4:** AWS charges for public IPv4 addresses. Free-tier accounts include 750 hours a
  month for the first year, enough for one server running all month. An Elastic IP that isn't
  attached to a running instance is charged.
- **After 12 months** (classic free tier), the t3.micro and RDS are billed normally. Set an
  **AWS Budget** (Billing → Budgets) with an email alert so nothing surprises you.
