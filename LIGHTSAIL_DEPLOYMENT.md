# Lightsail Deployment Runbook

The current, low-cost deployment: the whole backend (API + PostgreSQL) on **one AWS Lightsail
instance**, behind the same S3 + CloudFront setup as before. It replaces the ECS Fargate + ALB
+ RDS stack described in `AWS_DEPLOYMENT_PLAN.md`, which cost ~$55–65/month whether anyone
used the app or not — far more than an MVP with a handful of users justifies. That document is
kept as the blueprint for when traffic does justify it.

**Target: ~$13–14/month, fixed.** Same public URL, same app code, same deploy-on-merge CI.

---

## Architecture

```
Browser ──HTTPS──> CloudFront  d1u7p8d1507l08.cloudfront.net   (TLS at the edge)
                     ├─ /* (Default)      -> S3 bucket (frontend build)
                     │                       + viewer-request function spa-index-rewrite
                     └─ /api/*, /health/* -> Lightsail instance, HTTP :80
                                             origin host <static-ip-dashed>.sslip.io
                                             + header X-Origin-Verify: <secret>

Lightsail instance (Ubuntu 24.04, 2 GB) — docker compose, /opt/msa
   caddy     :80   403 unless X-Origin-Verify matches, else proxy to backend:8000
   backend         ghcr.io/nithusikan01/medical-student-assistant-backend:<sha>
   postgres        postgres:18-alpine, named volume `pgdata`, no published port
```

Why it looks like this:

- **CloudFront stays.** It keeps the frontend and API on one origin, which the `SameSite=Lax`
  refresh cookie requires, and it provides HTTPS without a domain. Its always-free tier (1 TB,
  10M requests/month) covers this app's traffic.
- **`sslip.io` hostname.** A CloudFront origin must be a hostname, not an IP, and a Lightsail
  static IP has no DNS name. `13-234-1-2.sslip.io` resolves to `13.234.1.2` with no setup. This
  is a stopgap until there's a real domain (see the domain section near the end).
- **Secret origin header instead of a firewall allowlist.** The old ALB only accepted traffic
  from CloudFront's prefix list. Lightsail's firewall can't express that, so CloudFront adds
  `X-Origin-Verify` to every origin request and Caddy refuses anything without it. Hitting
  the static IP directly gets a 403.
- **Postgres in a container on the same box.** RDS was ~$15/month alone. Backups are
  Lightsail's automatic daily snapshots.
- **Images on GHCR, not ECR.** GitHub Actions pushes and the server pulls with the workflow's own
  short-lived `GITHUB_TOKEN`, so the server holds **no AWS credentials at all**.
- **One uvicorn worker.** The response cache and BM25 index are per-process (see CLAUDE.md);
  a second worker would keep a second copy that diverges.

## Cost

| Item | Monthly |
|---|---|
| Lightsail 2 GB plan (static IP, 60 GB SSD and transfer included) | $12 — confirm the `ap-south-1` price in the console |
| Lightsail automatic snapshots | ~$1–2 |
| S3 (frontend build) | ~$0.05 |
| CloudFront | $0 (always-free tier) |
| GHCR | $0 |
| **Total** | **≈ $13–14** |

The 1 GB plan ($7) also works thanks to the swap file `bootstrap.sh` creates, bringing the
total to ~$8–10 — but the in-memory BM25 index grows with every book ingested, so 2 GB is the
recommended size. Lightsail can move to a larger plan later via a snapshot.

Not counted: Pinecone, Gemini and Groq. Those are billed by their providers, not AWS, and are
unchanged by this move.

---

## Step 0 — Stop using the root user

Do this first, so every later step runs as an IAM user. AWS resources belong to the *account*,
not to whoever created them — nothing moves; this only changes who signs in from now on.

A plain IAM user rather than IAM Identity Center: Identity Center needs AWS Organizations,
which accounts on the credit-based free plan can't use.

1. **Lock down root** (signed in as root):
   - **Security credentials** → assign an **MFA device**.
   - **Security credentials** → **Access keys**: delete any that exist.
   - **Account** → **IAM user and role access to Billing information** → **Edit** → tick
     **Activate IAM Access**. Without this, IAM users cannot see bills, credits or Budgets even
     with `AdministratorAccess`.
2. **Create the admin user**: **IAM** → **User groups** → create `Admins` with the
   `AdministratorAccess` policy → **Users** → create e.g. `nithusikan-admin` in that group, with
   console access and a strong password. Sign in as it once and assign an MFA device.
   - No access key unless you need the AWS CLI. If you do, create it on this user, keep it only
     in `aws configure`, and rotate it every ~90 days.
3. **Switch**: sign out of root; sign in at
   `https://519035820911.signin.aws.amazon.com/console` as the new user. Use root only for
   the few tasks that require it (closing the account, changing the support plan).
4. **Automation already doesn't use root** and stays that way: GitHub Actions uses the OIDC
   role `medical-student-assistant-github-actions` (frontend only, after this move), and the
   Lightsail server needs no AWS credentials. The old `medical-student-assistant-cli` user is
   deleted in Step 7.
5. **Verify**: **IAM → Dashboard** shows no security recommendations outstanding, and the IAM
   user can open **Billing and Cost Management → Free Tier** and see the credit balance.

## Step 1 — Create the instance

Signed in as the IAM admin user, **Lightsail** console, region **Mumbai (ap-south-1)**:

1. **Create instance** → Linux/Unix → **OS only → Ubuntu 24.04 LTS** → the **$12 (2 GB)**
   plan (dual-stack, i.e. with a public IPv4). Name it `medical-student-assistant`.
2. **SSH key**: create a new key pair (or upload your own public key) and download the private
   key — you'll use it from your machine and from GitHub Actions.
3. Once running: **Networking** → **Attach static IP** (free while attached — a detached one is
   billed, so release it if you ever delete the instance).
4. **Networking → IPv4 firewall**: keep **SSH 22** but **restrict it to your IP**; keep
   **HTTP 80** open to all (the header check protects it). Add nothing else.
5. **Snapshots** → enable **Automatic snapshots** (daily, 7 retained).

## Step 2 — Prepare the server

From your machine (Git Bash/PowerShell with OpenSSH):

```bash
ssh -i <key>.pem ubuntu@<static-ip>

# on the server
curl -fsSL https://raw.githubusercontent.com/Nithusikan01/Medical-Student-Assistant/main/deploy/lightsail/bootstrap.sh | bash
exit   # log back in so the docker group applies
```

(Before this branch is merged, `scp` `deploy/lightsail/bootstrap.sh` over and `bash` it
instead.)

Copy the compose files over, then create the `.env`:

```bash
scp -i <key>.pem deploy/lightsail/docker-compose.yml deploy/lightsail/Caddyfile \
    deploy/lightsail/deploy.sh deploy/lightsail/.env.example ubuntu@<static-ip>:/opt/msa/

ssh -i <key>.pem ubuntu@<static-ip>
cd /opt/msa
cp .env.example .env && chmod 600 .env
openssl rand -hex 32    # run once for POSTGRES_PASSWORD, once for ORIGIN_SECRET
nano .env
```

Copy the API keys, `SECRET_KEY` and `ADMIN_*` values from the existing Secrets Manager secret
(`medical-student-assistant/backend` → **Retrieve secret value**) so existing sessions and the
admin account carry over. **Keep `SECRET_KEY` identical** — a new one would invalidate every
issued token. Keep `ORIGIN_SECRET` handy for Step 5.

## Step 3 — Copy the database from RDS

RDS sits in private subnets with no internet route, so the dump goes through a short-lived EC2
instance used purely as an SSH tunnel. Do this at a quiet time — anything written to the old
stack after the dump is not carried over.

1. **RDS** → the instance → **Actions → Take snapshot** (safety net). Note the **engine
   version** (18.3 at the time of this move): `postgres:18-alpine` in `docker-compose.yml` must
   be the same major version or newer — change the tag before going further if RDS is newer.
2. **EC2** → **Launch instance**: Amazon Linux 2023, `t3.micro`, a new key pair, subnet
   `subnet-0d7efb05e950dd1ea` (public), auto-assign public IP **on**. Security groups:
   `task-sg` (which `rds-sg` already trusts on 5432) **plus** a new temporary group allowing
   SSH 22 from **My IP**.
3. From your machine, open a tunnel and dump through it with Docker Desktop (no Postgres client
   to install anywhere):

   ```bash
   ssh -i <ec2-key>.pem -N -L 5433:medical-student-assistant-db.c3ugy24cq1u0.ap-south-1.rds.amazonaws.com:5432 ec2-user@<ec2-public-ip>

   # second terminal, from the repo root; prompts for the RDS master password
   docker run --rm -it -v "$PWD:/out" postgres:18-alpine \
     pg_dump -h host.docker.internal -p 5433 -U postgres -d medical_assistant \
     -Fc --no-owner --no-privileges -f /out/msa.dump
   ```

4. Copy it over and restore into a fresh, empty Postgres **before** the first app deploy:

   ```bash
   scp -i <key>.pem msa.dump ubuntu@<static-ip>:/opt/msa/

   ssh -i <key>.pem ubuntu@<static-ip>
   cd /opt/msa
   docker compose up -d postgres
   docker compose exec -T postgres pg_restore -U postgres -d medical_assistant --no-owner --no-privileges < msa.dump
   docker compose exec postgres psql -U postgres -d medical_assistant -c "select count(*) from users; select version_num from alembic_version;"
   rm msa.dump
   ```

5. **Terminate the EC2 instance**, delete the temporary security group, and delete `msa.dump`
   from your machine.

This carries users, conversations, documents, `document_chunks`, telemetry and model pricing.
`document_chunks` is both the BM25 source and the list of Pinecone vector ids, and Pinecone
itself is untouched — **no re-ingestion is needed**.

## Step 4 — First deploy from GitHub Actions

1. Get the server's host key, **on the server itself** so it can't be spoofed:
   `ssh-keyscan -t ed25519 localhost` → replace `localhost` at the start of the line with the
   static IP.
2. Repo → **Settings → Secrets and variables → Actions** → add:

   | Secret | Value |
   |---|---|
   | `LIGHTSAIL_HOST` | the static IP |
   | `LIGHTSAIL_USER` | `ubuntu` |
   | `LIGHTSAIL_SSH_KEY` | the full private key file contents |
   | `LIGHTSAIL_KNOWN_HOSTS` | the host-key line from step 1 |

3. **Lightsail firewall**: GitHub's runners don't have fixed IPs, so CI can't reach SSH while
   it's restricted to your IP. Either open 22 to all (key-only auth, password login is
   disabled on Lightsail images by default) or open it just before a deploy. Opening it is the
   practical choice; the private key is the real protection.
4. **Actions → Deploy backend → Run workflow**. It tests, pushes the image to GHCR, copies the
   compose files, and runs `deploy.sh`: pull → `alembic upgrade head` (a no-op if the restore
   was at head) → `up -d` → health poll. A failed migration or health check fails the job and
   leaves the previous containers running.

## Step 5 — Point CloudFront at Lightsail

**CloudFront** → distribution `E39FPVC302KYZF`:

1. **Origins → Create origin**:
   - **Origin domain**: the static IP with dashes + `.sslip.io`, e.g. `13-234-1-2.sslip.io`
   - **Protocol**: HTTP only, port 80
   - **Add custom header**: `X-Origin-Verify` = the `ORIGIN_SECRET` from `.env`
   - **Response timeout**: 60 seconds (a long generation or a book upload can exceed the
     default 30)
2. **Behaviors**: edit **only** `/api/*` and `/health/*` → change the origin to the new one.
   Keep **CachingDisabled** and **AllViewerExceptHostHeader** exactly as they are.
   **Do not touch `Default (*)`**, which must stay on the S3 origin, and change which origin a
   behavior uses on the **Behaviors** tab, never by editing an origin's domain on the
   **Origins** tab. Both mistakes happened during this move and took the site down; see
   Troubleshooting.
3. Wait for **Deploying → Enabled**, then compare against
   [CloudFront configuration](#cloudfront-configuration) below.

**Rollback** at any point before Step 7: switch the two behaviors back to the ALB origin.

## Step 6 — Verify

```bash
# on the server: services healthy, header check working
docker compose ps
curl -s -o /dev/null -w "%{http_code}\n" localhost/health/health      # 403
curl -s -H "X-Origin-Verify: <secret>" localhost/health/health        # {"status":"healthy"}
```

```powershell
# from your machine: direct access refused, CloudFront path works
curl.exe -s -o NUL -w "%{http_code}" http://<static-ip>/health/health  # 403
curl.exe https://d1u7p8d1507l08.cloudfront.net/health/health           # {"status":"healthy"}
```

In a browser at the CloudFront URL:

- Log in as an existing user, which proves the data moved. Reload and confirm you're still
  signed in, which proves the refresh cookie works through CloudFront.
- Open an old conversation: its messages and sources replay.
- Ask a question and get a grounded answer with sources (Pinecone + BM25 from the restored
  chunks + Gemini).
- As admin: upload a small PDF, ask about it, then delete it.
- The admin monitoring pages show new traces.

A day later on the server, `free -h` and `docker stats --no-stream` show the memory headroom.

## Step 7 — Tear down the old stack

After 1–2 days without problems, in this order:

1. **ECS**: set the service's desired count to 0 → delete the service → delete the cluster.
   Deregister old task definitions if you like (they're free).
2. **EC2 → Load Balancers**: delete `medical-student-assistant-alb`, then the target group
   `medical-student-assistant-tg`.
3. **CloudFront**: delete the now-unused ALB origin.
4. **RDS**: delete `medical-student-assistant-db` **with a final snapshot**. Once Lightsail's
   automatic snapshots have been running for a week, delete the RDS snapshots too (they're
   billed per GB).
5. **ECR**: delete the `medical-student-assistant-backend` repository.
6. **Secrets Manager**: schedule `medical-student-assistant/backend` for deletion (7 days).
7. **CloudWatch**: delete log group `/ecs/medical-student-assistant-backend`.
8. **IAM**:
   - Remove the `ECRAuth`, `ECRPush`, `ECSDeploy` and `PassRolesToECS` statements from
     `medical-student-assistant-github-actions` (keep `FrontendSync` and `CacheInvalidate`).
   - Delete the two ECS roles, `medical-student-assistant-task-execution-role` and
     `medical-student-assistant-task-role`.
   - Delete the `medical-student-assistant-cli` user and its access keys.
9. **VPC**: the VPC, subnets and security groups cost nothing and can stay. Check **EC2 →
   Elastic IPs** and **VPC → Public IPv4 addresses** for anything left allocated — idle public
   IPv4 is billed.
10. Next day: **Billing → Bills**, and confirm nothing but Lightsail, S3 and CloudFront is
    accruing.

## Step 8 — Budget alert

**Billing → Budgets → Create budget** → **Use a template → Monthly cost budget**, **$15**, your
email. The template alerts at 85% and 100% of actual spend and when the forecast passes 100%.

---

## Day-to-day operations

| Task | How |
|---|---|
| Deploy backend | Merge to `main` touching `backend/`, `rag/`, `Dockerfile` or `deploy/lightsail/` — or **Run workflow** manually |
| Deploy frontend | Merge touching `frontend/` — unchanged: build → S3 sync → CloudFront invalidation |
| Roll back backend | On the server: `cd /opt/msa && bash deploy.sh <older-commit-sha>`, after `docker login ghcr.io` with a PAT that has `read:packages`. Only if no newer migration ran — migrations aren't reversed |
| Logs | `docker compose logs -f backend` (rotated at 3 × 10 MB per service) |
| psql | `docker compose exec postgres psql -U postgres -d medical_assistant` |
| Change an env var | Edit `/opt/msa/.env`, then `docker compose up -d` (recreates what changed) |
| Restart | `docker compose restart backend` — also empties the per-process response cache |
| OS updates | Security updates install automatically; `sudo reboot` occasionally, and the containers come back by themselves (`restart: unless-stopped`) |
| Restore from backup | Lightsail → **Snapshots** → create a new instance from one, move the static IP to it |
| Off-box DB copy | `docker compose exec -T postgres pg_dump -U postgres -Fc medical_assistant > backup.dump`, then `scp` it off |

## CloudFront configuration

What distribution `E39FPVC302KYZF` must look like. Check against this after any edit in the
CloudFront console. Every row has been wrong at least once, and each one fails differently.

| Behavior | Origin | Cache policy | Origin request policy | Viewer request function |
|---|---|---|---|---|
| `/api/*` | `lightsail-backend` | CachingDisabled | AllViewerExceptHostHeader | none |
| `/health/*` | `lightsail-backend` | CachingDisabled | AllViewerExceptHostHeader | none |
| `Default (*)` | `medical-student-assistant-frontend-519035820911.s3.ap-south-1.amazonaws.com` | CachingOptimized | none | `spa-index-rewrite` |

- **Origins**: the S3 bucket (with an origin access control) and `lightsail-backend`
  (`<static-ip-dashed>.sslip.io`, HTTP only, port 80, header `X-Origin-Verify`, response
  timeout 60 s). Nothing else.
- **Error pages**: **empty**. Custom error responses apply to every behavior, so a
  `404 → /index.html, 200` rule also rewrites the API's real 404s into HTML, and the app
  shows `Unexpected token '<' ... is not valid JSON`. Client-side routes are handled by
  `spa-index-rewrite` instead (CloudFront Functions → published, `cloudfront-js-2.0`):

  ```js
  function handler(event) {
    var request = event.request;
    if (!request.uri.includes('.')) {
      request.uri = '/index.html';
    }
    return request;
  }
  ```

Quick check from any machine. Each line should print the status shown in its comment:

```bash
U=https://d1u7p8d1507l08.cloudfront.net
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" $U/                               # 200 text/html
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" $U/c/abc                          # 200 text/html
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" $U/health/health                  # 200 application/json
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" $U/api/this-route-does-not-exist  # 404 application/json
```

## Troubleshooting (things that happened during the move)

| Symptom | Cause | Fix |
|---|---|---|
| Homepage returns `404 {"detail":"Not Found"}` from `uvicorn` | `Default (*)` points at the backend (Lightsail or the old ALB) instead of S3 | Behaviors → `Default (*)` → origin = the S3 bucket |
| Every path, `/api/*` included, returns S3 `AccessDenied` XML | The `lightsail-backend` **origin** had its domain changed to the S3 bucket, so all behaviors using it hit S3 with no access control | Origins → `lightsail-backend` → domain back to `<ip>.sslip.io`, HTTP only, header restored |
| `/` returns 200 with `X-Cache: Error from cloudfront`; an unknown `/api/...` path returns `200 text/html` | Custom error responses are serving `index.html`, and `spa-index-rewrite` is not attached | Attach the function to `Default (*)` (viewer request), then delete every row on **Error pages** |
| `spa-index-rewrite` is missing from the function dropdown | The function is unpublished (or was never created in this account) | Functions → create it as above → **Publish** tab → Publish function |
| SSH to a temporary EC2 instance times out | The home connection's public IP changed, and the security group allows only the old one | Security group → SSH rule → Source **My IP** again |
| Postgres 18 container refuses to start with a volume at `/var/lib/postgresql/data` | The 18 image stores data in `/var/lib/postgresql/18/docker` | Mount the volume at `/var/lib/postgresql` (already done in `docker-compose.yml`) |

## Adding a domain later

Either:

- **Keep CloudFront (least change):** request a free ACM certificate in **us-east-1** for the
  domain, add it to the distribution as an alternate domain name, point a CNAME at the
  distribution, and add the new origin to `CORS_ORIGINS` in `.env`. The `sslip.io` origin can
  stay, or be replaced with an `api.` subdomain pointing at the static IP.
- **Drop CloudFront for the API:** point the domain at the static IP, replace `:80` in the
  Caddyfile with the domain (Caddy fetches a Let's Encrypt certificate itself), open 443 in the
  Lightsail firewall, serve the frontend from Caddy as well, and remove the header check.

## When to move back up

The ECS/ALB/RDS design in `AWS_DEPLOYMENT_PLAN.md` buys redundancy and managed backups. Revisit
it when one of these happens: real users depend on uptime (a single instance is a single point
of failure), sustained memory pressure on the largest sensible Lightsail plan, or a need for
more than one API worker (which first needs a shared response cache — see the README's next
improvements).
