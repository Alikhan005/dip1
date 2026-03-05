# Render Deployment (Free)

## 1. Prerequisites

1. Project is pushed to GitHub.
2. You have a Render account linked with GitHub.

## 2. Deploy from `render.yaml`

1. Open `https://dashboard.render.com/blueprints`.
2. Click `New Blueprint Instance`.
3. Select your GitHub repo `Alikhan005/syllabus`.
4. Render will detect `render.yaml`.
5. Click `Apply`.

Render creates:
1. Web service `almau-syllabus` (free)
2. PostgreSQL `almau-syllabus-db` (free)

## 3. Important free-tier notes

1. Free web service sleeps on inactivity.
2. Free Render Postgres has storage/time limits (check current Render pricing).
3. Worker is launched inside the same web service process via `deploy/render-start.sh`.

## 4. First check

After deploy is finished:

1. Open your Render app URL.
2. Check health endpoint: `/healthz/`
3. Login and run one AI check to verify worker processing.

## 5. If deploy fails

1. Open service `Logs`.
2. Verify DB migration errors and environment variables.
3. Re-deploy from latest commit.
