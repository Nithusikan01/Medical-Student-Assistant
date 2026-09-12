# AWS Deployment Plan

Moves this app off its current hosting (Koyeb for the backend, Supabase for Postgres, Vercel for
the frontend) onto AWS: ECS Fargate + RDS + S3/CloudFront, deployed via GitHub Actions. Written as
a runbook — follow top to bottom, high level first, each section drilling into the commands and
config needed to actually do it.

**Do not skip section 0.** Every later step assumes these decisions; they exist because a naive
"frontend on CloudFront, backend on an ALB, called cross-origin" design breaks this app's auth
specifically (see 0.1).

---

## 0. Architecture decisions

These are the load-bearing decisions for the whole plan. Each one exists because of something
concrete in this codebase — not a generic AWS best-practice checklist.

### 0.1 CloudFront fronts both the static site and the API — this is not optional

The refresh-token cookie is set `samesite="lax"` (`backend/src/backend/routers/auth.py:55`), and
`cookie_secure` is off by default (`COOKIE_SECURE` env var — must be `true` in prod). A
`SameSite=Lax` cookie is **not sent on cross-site `fetch`/XHR**, only on top-level navigations. If
the frontend (on a CloudFront/S3 domain) calls the backend (on a separate ALB domain) directly,
`POST /api/auth/refresh` never receives the cookie — login works, but the silent refresh-on-mount
and every subsequent rotation silently fails. Sessions won't survive a page reload.

The current Vercel deployment avoids this exact problem via `frontend/vercel.json`, which rewrites
`/api/*` and `/health/*` to the Koyeb backend so the browser only ever sees one origin. The AWS
setup must do the same job: **CloudFront gets a second cache behavior that routes `/api/*` and
`/health*` to the ALB as a second origin.** No frontend or backend code changes — this is pure
infrastructure, and it's why the ALB exists at all in this design (see 5, cost notes).

Do not attempt to fix this by setting `samesite="none"` in code instead — that's a real
alternative in general, but it's a code change to a security-sensitive auth path, it needs
`Secure` to be reliably true everywhere including local dev fallbacks, and it doesn't remove the
need for a stable single frontend origin anyway (CORS + `allow_credentials=True` still needs an
exact origin match). The CloudFront-behavior route is strictly simpler and changes zero backend
code.

### 0.2 Postgres via RDS, replacing Supabase

Single `db.t4g.micro` instance, not Aurora — this is a class-project scale workload and Aurora's
minimum cost isn't justified. RDS *replaces* Supabase; it does not run alongside it. See section 2
for the cutover sequence — data needs to move, not just the connection string.

### 0.3 Networking: public Fargate task, private RDS, no NAT Gateway

- The **Fargate task** sits in a **public** subnet with a public IP, so it can reach Pinecone and
  Gemini directly over the internet gateway (IGW) without a NAT Gateway. A NAT Gateway costs
  ~$32-35/month fixed plus data processing — not justified for one low-traffic task.
- **RDS** sits in **private/isolated subnets with no route to an IGW at all.** This costs nothing
  extra — RDS never initiates outbound internet traffic regardless of subnet type — and it's the
  correct default. "Public subnet + `publicly_accessible=false`" is a weaker version of the same
  goal: the DB still lives in an internet-routable subnet, which most security scanners (and
  reviewers) will flag. Isolated subnets with no IGW route close that off structurally.
- This means the VPC needs **4 subnets across 2 AZs**: 2 public (ALB + Fargate task), 2 private
  (RDS's subnet group — RDS requires ≥2 AZs for its subnet group even for a single-AZ instance).

### 0.4 Image build context is the repo root

There is one `Dockerfile`, at the repo root, not `backend/Dockerfile`. Its build context must
include both `rag/` and `backend/` (the backend imports the engine package), which is exactly what
the existing Dockerfile's own header comment says. Any `docker build` or GitHub Actions build step
must use `.` as context with `-f Dockerfile` from the repo root — not `backend/`.

The image deliberately ships without PyTorch/sentence-transformers (hosted inference is the
default embedding/reranking path), which is also why the Fargate task can be sized small (see
1.7) — there's no local model weights to load into memory.

### 0.5 Secrets live in Secrets Manager, never in the task definition or the workflow YAML

Required secrets, per CLAUDE.md: `PINECONE_API_KEY`, `PINECONE_INDEX_NAME` (not sensitive but
fine to keep alongside), `GEMINI_API_KEY`, `DATABASE_URL`, `SECRET_KEY` (≥32 chars, JWT signing),
`ADMIN_EMAIL`/`ADMIN_PASSWORD` (idempotent seed — an existing password is never overwritten). All
of these go into AWS Secrets Manager and are referenced by ARN in the task definition's `secrets`
block (not `environment`), so they never appear in plaintext in the task definition JSON, in
CloudWatch Logs, or in the GitHub Actions workflow.

Non-secret config (`CORS_ORIGINS`, `COOKIE_SECURE=true`, `ALLOW_OPEN_REGISTRATION`, chunking/
retrieval tuning vars) goes in the task definition's plain `environment` block.

### 0.6 Two IAM principals, not one

- **The GitHub Actions CI user** (or OIDC role — see 1.5) needs push/deploy permissions: ECR push,
  register task definitions, update the ECS service, sync S3, invalidate CloudFront.
- **The ECS task execution role** is a different, narrower principal: pull the image from ECR,
  read the specific secrets from Secrets Manager, write logs to CloudWatch. It has no GitHub
  Actions-side permissions at all.

Conflating these (giving the CI user the task's runtime permissions, or vice versa) is the kind of
mistake that's invisible until an audit or an incident.

---

## 1. One-time manual AWS setup

Everything here is done once, by hand (Console or CLI) — none of it belongs in the GitHub Actions
workflow. Order matters: networking → data layer → registry/IAM → compute → CDN.

### 1.1 VPC and subnets

- Create a VPC (e.g. `10.0.0.0/16`).
- 2 **public** subnets in different AZs (e.g. `10.0.0.0/24`, `10.0.1.0/24`), route table with a
  route to an Internet Gateway. These host the ALB and the Fargate task (task gets
  `assignPublicIp: ENABLED`).
- 2 **private/isolated** subnets in different AZs (e.g. `10.0.10.0/24`, `10.0.11.0/24`), route
  table with **no** IGW route (no NAT route either — fully isolated, per 0.3). These host RDS via
  an RDS subnet group.

### 1.2 Security groups

| SG | Inbound | From |
|---|---|---|
| `alb-sg` | 443 (and 80→redirect) | **CloudFront managed prefix list** `com.amazonaws.global.cloudfront.origin-facing` — *not* `0.0.0.0/0`. Direct internet access to the ALB bypasses CloudFront and defeats 0.1's same-origin fix. |
| `task-sg` | 8000 | `alb-sg` only |
| `rds-sg` | 5432 | `task-sg` only |

Getting the ALB SG source wrong (`0.0.0.0/0`) is the most common way this design quietly stops
doing what it's for — double-check it after creation, not just at creation time.

### 1.3 RDS (Postgres)

- Engine: PostgreSQL (match the version Supabase currently runs, or newer — Alembic migrations
  are engine-version-agnostic here).
- Instance class: `db.t4g.micro` to start.
- Subnet group: the 2 private subnets from 1.1.
- Security group: `rds-sg`.
- `publicly_accessible = false` (defense in depth on top of "no IGW route," not a substitute for
  it).
- Credentials: generate, store immediately in Secrets Manager as the `DATABASE_URL` secret in
  full connection-string form (`postgresql://user:pass@host:5432/dbname`) — this is the exact
  string the task definition will reference and the exact format `db/session.py` expects.

### 1.4 ECR repository

```
aws ecr create-repository --repository-name rag-backend --image-scanning-configuration scanOnPush=true
```

Note the repository URI for the task definition and workflow.

### 1.5 IAM

**CI user/role** (GitHub Actions) — policy scoped to exactly:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRPush",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECSDeploy",
      "Effect": "Allow",
      "Action": [
        "ecs:RegisterTaskDefinition",
        "ecs:DescribeTaskDefinition",
        "ecs:UpdateService",
        "ecs:DescribeServices",
        "ecs:RunTask"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PassRolesToECS",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::<ACCOUNT_ID>:role/rag-task-execution-role",
        "arn:aws:iam::<ACCOUNT_ID>:role/rag-task-role"
      ]
    },
    {
      "Sid": "FrontendSync",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::<FRONTEND_BUCKET>", "arn:aws:s3:::<FRONTEND_BUCKET>/*"]
    },
    {
      "Sid": "CacheInvalidate",
      "Effect": "Allow",
      "Action": "cloudfront:CreateInvalidation",
      "Resource": "arn:aws:cloudfront::<ACCOUNT_ID>:distribution/<DISTRIBUTION_ID>"
    }
  ]
}
```

`ecs:RegisterTaskDefinition` and `iam:PassRole` are easy to miss — without them, registering a new
task definition revision from the workflow fails.

Prefer an OIDC IAM role (GitHub's `configure-aws-credentials` action with `role-to-assume`) over a
long-lived access key pair if you want to avoid storing static credentials as repo secrets at all;
either works, OIDC is just the better long-term default.

**ECS task execution role** (`rag-task-execution-role`) — separate principal, trust policy for
`ecs-tasks.amazonaws.com`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:<REGION>:<ACCOUNT_ID>:secret:rag/*"
    }
  ]
}
```

**ECS task role** (`rag-task-role`) — what the running container itself can call. This app makes
no AWS SDK calls from inside the request path (Pinecone/Gemini are external HTTPS APIs, not AWS
services), so this role can start empty/minimal and only grow if that changes.

### 1.6 ECS cluster

```
aws ecs create-cluster --cluster-name rag-cluster
```

Fargate — no EC2 capacity to manage.

### 1.7 Task definition

Key fields:

- `family`: `rag-backend`
- `networkMode`: `awsvpc`
- `requiresCompatibilities`: `["FARGATE"]`
- `cpu`: `512` (0.5 vCPU), `memory`: `1024` (1GB) — justified by 0.4: no ML model weights loaded
  in-process, so this is headroom for FastAPI + the hybrid retrieval/rerank calls, not for a
  local embedding model. Revisit only if `USE_HOSTED_INFERENCE` is ever turned off.
- `executionRoleArn`: `rag-task-execution-role`
- `taskRoleArn`: `rag-task-role`
- One container definition:
  - `image`: `<ECR_URI>:<TAG>` (tag = commit SHA, set per-deploy — see 3.2)
  - `portMappings`: containerPort `8000`
  - `environment`: `CORS_ORIGINS` (the CloudFront domain from 1.10), `COOKIE_SECURE=true`,
    `ALLOW_OPEN_REGISTRATION` (per your policy), any `CHUNK_SIZE`/`CANDIDATE_K`/retrieval tuning
    vars you're overriding from defaults
  - `secrets`: `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `GEMINI_API_KEY`, `DATABASE_URL`,
    `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` — each a `{name, valueFrom: <secret ARN>}` pair
  - `healthCheck`: `CMD-SHELL, curl -f http://localhost:8000/health/health || exit 1`, matching
    the app's actual health endpoint (`GET /health/health` — the router is mounted under `/health`
    and declares `/health` itself, so the full path really is `/health/health`)
  - `logConfiguration`: `awslogs` driver → a CloudWatch log group (e.g. `/ecs/rag-backend`,
    create it first or let the execution role's `logs:CreateLogStream` handle it if the group
    already exists)

### 1.8 ALB, target group, ECS service

- ALB in the 2 public subnets, SG = `alb-sg`.
- Target group: type `ip` (required for `awsvpc` networking mode), health check path
  `/health/health`, port 8000.
- Listener: 443 (ACM cert if using a custom domain — see 1.11 — or just serve over CloudFront's
  HTTPS and keep the ALB listener on plain HTTP 80, since CloudFront-to-origin can be HTTP if the
  origin isn't publicly browsed directly; simplest for v1 is HTTP 80 listener, HTTPS everywhere
  else via CloudFront).
- ECS service: launch type Fargate, subnets = the 2 public subnets, SG = `task-sg`,
  `assignPublicIp: ENABLED`, desired count 1, attached to the target group above.

### 1.9 S3 bucket for the frontend

- Private bucket, block all public access.
- CloudFront reaches it via **Origin Access Control (OAC)**, not a public bucket policy or legacy
  OAI.

### 1.10 CloudFront distribution

- **Default behavior**: origin = the S3 bucket (1.9) via OAC, viewer protocol policy "redirect to
  HTTPS", default root object `index.html`. Add a custom error response mapping 403/404 →
  `/index.html` with 200 status, since this is an SPA with client-side routing
  (`react-router-dom`).
- **Second behavior**, path pattern `/api/*`: origin = the ALB's DNS name (custom origin, HTTP
  port 80 or HTTPS 443 matching 1.8's listener). Forward all headers/cookies/query strings for
  this behavior — caching must be disabled (use the AWS-managed `CachingDisabled` policy) since
  these are API calls, not static assets.
- **Third behavior**, path pattern `/health*`: same ALB origin, same no-cache policy — this is
  what makes `/health/health` reachable through the CloudFront domain for the verification
  checklist in section 4.
- Note the distribution ID and domain name — needed for the workflow (invalidation) and for
  `CORS_ORIGINS` (1.7) and the ALB SG source (1.2, already set to the managed prefix list rather
  than this specific distribution, which is the simpler and still-correct option).

### 1.11 Custom domain — explicitly deferred

Not required to start; CloudFront's own `*.cloudfront.net` domain is a valid HTTPS origin for the
frontend and, via 0.1's behavior routing, for the API too. Add a Route 53 hosted zone + ACM cert
+ CloudFront alternate domain name later if a real domain is wanted (tracked in section 6).

---

## 2. Database cutover: Supabase → RDS

This is a real data migration, not a config change — RDS is *replacing* Supabase, per the
confirmed decision in the Context. Do not skip 2.1.

### 2.1 Dump the current Supabase database

```
pg_dump "$SUPABASE_DATABASE_URL" --format=custom --file=supabase_backup.dump
```

Do this even if you believe there's no data worth keeping yet — it's one command, it's the
rollback path if RDS setup goes wrong mid-cutover, and skipping it is the kind of shortcut that's
only ever regretted after the fact.

### 2.2 Create the schema in RDS

Run `alembic upgrade head` against the **new, empty** RDS instance, from something that can reach
the `rds-sg`-protected private subnet. Two options:

- **One-off ECS task** (recommended): `aws ecs run-task` using the exact backend image, overriding
  the container command to `alembic upgrade head` instead of the uvicorn entrypoint, in the same
  VPC/subnets/SG as the real service (needs a route to RDS, so run it in a subnet that has
  `rds-sg` access — the public subnets with `task-sg` already satisfy this since `rds-sg` allows
  `task-sg`). This exercises the exact image and dependency versions that will run in production,
  and needs no throwaway EC2 instance or bastion host.
- **Local tunnel**: temporary bastion or SSH tunnel + local `alembic upgrade head` with
  `DATABASE_URL` pointed at RDS through the tunnel. More manual, only worth it if the one-off task
  approach is inconvenient.

Verify: `alembic current` should show the head revision (`0003_documents`).

### 2.3 Restore data

```
pg_restore --dbname="$RDS_DATABASE_URL" --no-owner --no-privileges supabase_backup.dump
```

Or, if there's no real user data yet worth carrying over (reasonable for a class project still in
development), skip this step and start RDS empty — **this is a call to make at execution time**,
not one to bake into the plan.

### 2.4 Verify admin seeding

Boot the backend once against RDS and confirm `ADMIN_EMAIL`/`ADMIN_PASSWORD` seeding behaves
correctly — idempotent, so it should no-op if 2.3 already restored an admin row, or create one
fresh if RDS started empty.

### 2.5 Sweep every `DATABASE_URL` reference

- The `DATABASE_URL` **GitHub Actions secret** — currently consumed by
  `.github/workflows/backend-deploy.yml:47` for the pre-deploy migration step. Update its value to
  the RDS connection string as part of cutover, not after.
- **Do not touch** local `backend/.env` files — those are per-developer and unaffected by this
  production migration.
- `README.md:167,590,608` documents Supabase as the recommended Postgres host — update these once
  cutover is verified working (section 4), so the README reflects the new deployment story.
- No code changes needed: `backend/src/backend/db/session.py` and `backend/alembic.ini` both read
  `DATABASE_URL` generically — they don't know or care that it used to point at Supabase.

### 2.6 Decommission Supabase — after verification, not before

Keep the Supabase project around (paused, if the plan supports pausing rather than deleting) for a
few days after section 4's checklist passes, as a rollback net. Delete only once confident.

---

## 3. GitHub Actions CI/CD

### 3.1 Repo secrets/variables

Add: `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or configure an OIDC role and use
`role-to-assume` instead — see 1.5), `ECR_REPOSITORY` (or hardcode in the workflow),
`ECS_CLUSTER`, `ECS_SERVICE`, `CLOUDFRONT_DISTRIBUTION_ID`, `FRONTEND_BUCKET`.

Remove once cutover is confirmed: `KOYEB_API_TOKEN` secret, `KOYEB_SERVICE` repository variable.

### 3.2 Rewrite `.github/workflows/backend-deploy.yml` — don't add a parallel file

The existing workflow already gets the important sequencing right: install → run
`rag/tests/unit` and `backend/tests/{unit,api}` → **apply migrations before deploying** (schema
must never lag behind code that expects it) → deploy, with a `concurrency: group: deploy-backend`
guard so two deploys can't race a migration against a rollback. Keep all of that. Replace only the
deploy tail:

```yaml
      # ... existing checkout / install / test / migrate steps, DATABASE_URL now = RDS ...

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}   # or access-key-id/secret-access-key
          aws-region: <REGION>

      - uses: aws-actions/amazon-ecr-login@v2
        id: ecr-login

      - name: Build and push image
        env:
          ECR_REGISTRY: ${{ steps.ecr-login.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t "$ECR_REGISTRY/rag-backend:$IMAGE_TAG" -f Dockerfile .
          docker push "$ECR_REGISTRY/rag-backend:$IMAGE_TAG"

      - name: Render new task definition
        id: render
        uses: aws-actions/amazon-ecs-render-task-definition@v1
        with:
          task-definition: task-definition.json   # current live definition, kept in the repo
          container-name: rag-backend
          image: ${{ steps.ecr-login.outputs.registry }}/rag-backend:${{ github.sha }}

      - name: Deploy to ECS
        uses: aws-actions/amazon-ecs-deploy-task-definition@v2
        with:
          task-definition: ${{ steps.render.outputs.task-definition }}
          cluster: ${{ secrets.ECS_CLUSTER }}
          service: ${{ secrets.ECS_SERVICE }}
          force-new-deployment: true
```

Remove the `koyeb-community/koyeb-actions` install step and the `koyeb service redeploy` step
entirely — they're replaced by the block above.

Keep `task-definition.json` (a checked-in baseline matching 1.7, image field overwritten per-run
by the render step above) in the repo — e.g. `backend/deploy/task-definition.json` — rather than
constructing the whole JSON inline in the workflow.

### 3.3 New `.github/workflows/frontend-deploy.yml`

The frontend currently deploys via **Vercel's own GitHub integration** — there's no existing
Actions workflow for it (`vercel.json` exists, but nothing under `.github/workflows/` references
Vercel). This is a genuinely new file, not a rewrite:

```yaml
name: Deploy frontend

on:
  push:
    branches: [main]
    paths:
      - "frontend/**"
      - ".github/workflows/frontend-deploy.yml"
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run build   # runs tsc -b first, so this also type-checks

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: <REGION>

      - name: Sync to S3
        run: aws s3 sync dist/ s3://${{ secrets.FRONTEND_BUCKET }} --delete

      - name: Invalidate CloudFront cache
        run: aws cloudfront create-invalidation --distribution-id ${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }} --paths "/*"
```

No `VITE_API_URL` build-time variable needed — per 0.1, the frontend and API share the same
CloudFront origin, so the existing relative `/api/...` URLs in `src/api/client.ts` work unchanged.

Once this is verified end-to-end (section 4), `frontend/vercel.json` and the Vercel project become
unused. Note their removal as a follow-up cleanup — not blocking for this migration.

### 3.4 IAM policy for the CI principal

Covered fully in 1.5 — the corrected version includes `ecs:RegisterTaskDefinition` and
`iam:PassRole`, both missing from earlier drafts of this plan and both required for
`amazon-ecs-deploy-task-definition` to succeed.

---

## 4. Cutover and verification checklist

Run through this in order; don't decommission anything (2.6, 3.3's Vercel note) until it's fully
green:

1. ECS service shows the task as `RUNNING` and target group health check as `healthy`.
2. `https://<cloudfront-domain>/health/health` returns `200` — confirms the CloudFront → ALB
   routing from 1.10 works.
3. Register a new user through the CloudFront URL, log out, close the tab, reopen — silent refresh
   on mount should restore the session. **This specifically validates the 0.1 cookie fix**; if
   sessions don't persist across a reload, the CloudFront `/api/*` behavior or the ALB SG is
   misconfigured.
4. Log in as admin, upload a PDF via the document management panel.
5. Ask a question referencing that PDF in the chat UI; confirm an answer comes back with
   structured sources.
6. If Supabase data was restored (2.3), confirm previously existing conversations/documents are
   visible and usable.
7. Only after 1-6 pass: proceed to Supabase decommission (2.6) and Vercel project removal (3.3).

---

## 5. Cost notes

| Item | Approx. cost | Notes |
|---|---|---|
| Fargate (0.5 vCPU / 1GB, always-on) | Low, usage-based | No ML weights loaded, per 0.4 |
| RDS `db.t4g.micro` | ~$12-15/mo (or free-tier eligible for 12mo) | Replaces Supabase's free tier — factor this in against Supabase's cost, if any |
| ALB | ~$16-20/mo, fixed | **Not optional here** — see below |
| NAT Gateway | $0 — avoided | Per 0.3: public Fargate subnet + isolated RDS subnet means neither needs one |
| ECR | Free ≤500MB for 12mo, then $0.10/GB-mo | |
| S3 + CloudFront | Low, usage-based | Typically <$1-2/mo at low traffic |

**Why the ALB isn't optional:** it's doing double duty — load balancer *and* the stable origin
that CloudFront's `/api/*` behavior (1.10) points at. A bare Fargate task with just a public IP
would be cheaper, but that IP changes on every redeploy, which would silently break the CloudFront
origin configuration on every single deploy. The ALB's stable DNS name is what makes the 0.1
same-origin fix durable across deploys, not just a one-time setup trick — its fixed cost is the
price of that stability.

With a $200 credit, this setup has comfortable runway for months. The ALB is the line item worth
watching if stretching the credit further matters — e.g., scaling the ECS service to 0 desired
tasks (and accepting the ALB still bills) during long idle stretches, or tearing down and
recreating the whole stack between active development periods.

---

## 6. Known future improvements (explicitly out of scope for v1)

- Move the Fargate task to a private subnet + NAT Gateway once real traffic or a security review
  justifies the added ~$32-35/mo.
- Custom domain + ACM certificate (Route 53 hosted zone, CloudFront alternate domain name) instead
  of the default `*.cloudfront.net` domain.
- Multi-AZ RDS and/or ECS service autoscaling, once uptime/traffic requirements exist.
- Remove `frontend/vercel.json` and the Vercel project entirely once confidence in the AWS path is
  established.
