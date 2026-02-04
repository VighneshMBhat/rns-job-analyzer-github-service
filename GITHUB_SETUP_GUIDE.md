# GitHub Service Setup Guide

## Overview

This service:
1.  Allows users to **Connect GitHub** via OAuth.
2.  Runs as a **weekly CRON job** to fetch new repositories.
3.  Reads `README.md` from each repo.
4.  Uses **Groq AI** (`llama-3.3-70b-versatile`) to extract technical skills.
5.  Stores skills in `user_skills` table with `source = 'github'`.
6.  **Avoids duplicates**: Only processes NEW repos (tracked in `github_repos` table).
7.  **Resume Skills**: Also extracts skills from user's uploaded resume (`profiles.resume_url`) and stores with `source = 'resume'`.

---

## Step 1: Create GitHub OAuth App

### Navigate to GitHub

1.  Login to **GitHub**.
2.  Click **Profile Picture** → **Settings**.
3.  Scroll down → **Developer settings** (left sidebar).
4.  Click **OAuth Apps** → **New OAuth App**.

### Fill the Form

| Field | Value |
|-------|-------|
| **Application name** | `Talento Vision` |
| **Homepage URL** | `https://talento-vision.vercel.app` |
| **Application description** | `Skill Gap Analyzer - Scans GitHub repos for skills` |
| **Authorization callback URL** | `http://localhost:8001/api/github/auth/callback` |

> ⚠️ **Important**: After deploying to AWS Lambda, update the callback URL to:
> `https://YOUR_LAMBDA_URL/api/github/auth/callback`

5.  Click **Register application**.

### Get Credentials

1.  **Client ID**: Copy the value shown (e.g., `Ov23liXXX...`).
2.  **Client Secret**: Click **Generate a new client secret**.
    *   ⚠️ Copy it immediately! You won't see it again.

---

## Step 2: Update Environment Variables

Open: `d:\rns-job-analyzer\github_service\.env`

Update these lines:

```env
GITHUB_CLIENT_ID=paste_your_client_id_here
GITHUB_CLIENT_SECRET=paste_your_client_secret_here
```

### Full `.env` Reference

| Variable | Description | Where to Get |
|----------|-------------|--------------|
| `HOST_URL` | This service's base URL | `http://localhost:8001` (local) or Lambda URL |
| `FRONTEND_URL` | Frontend URL | `https://talento-vision.vercel.app` |
| `SUPABASE_URL` | Supabase API URL | Already set |
| `SUPABASE_KEY` | Supabase Anon Key | Already set |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Service Key | Already set |
| `GITHUB_CLIENT_ID` | **YOU SET THIS** | From GitHub OAuth App |
| `GITHUB_CLIENT_SECRET` | **YOU SET THIS** | From GitHub OAuth App |
| `GITHUB_REDIRECT_URI` | Callback URL | Match the one in GitHub App |
| `GROQ_API_KEY` | Groq Cloud API Key | Already set |
| `GROQ_MODEL` | AI Model | `llama-3.3-70b-versatile` |

---

## Database Schema

### Table: `github_connections`
Stores the OAuth connection for each user.

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | uuid | FK to profiles |
| `access_token` | text | GitHub OAuth token |
| `github_username` | text | GitHub username |
| `last_sync_at` | timestamp | Last cron run time |

### Table: `github_repos` *(NEW)*
Tracks which repos have been processed.

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | uuid | FK to profiles |
| `github_repo_id` | bigint | GitHub's numeric repo ID |
| `repo_full_name` | text | e.g., "user/project" |
| `readme_content` | text | README.md content |
| `readme_hash` | text | Hash to detect changes |
| `last_processed_at` | timestamp | Last scan time |

### Table: `user_skills`
Stores extracted skills.

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | uuid | FK to profiles |
| `skill_name` | text | e.g., "React" |
| `source` | enum | `github`, `resume`, `manual` |
| `source_repo` | text | Repo where skill was found |
| `confidence_score` | numeric | AI confidence (0.0-1.0) |
| `proficiency_level` | integer | Higher = more mentions |

### Table: `profiles`
User profile (includes resume).

| Column | Description |
|--------|-------------|
| `resume_url` | URL to uploaded resume (Supabase Storage) |
| `resume_uploaded_at` | When resume was uploaded |

---

## Service Logic (Weekly CRON)

```
1. For each user with GitHub connected:
   a. Fetch all repos using access_token
   b. For each repo:
      - Check if repo_id exists in github_repos
      - If NEW → Fetch README.md → Extract skills → Save
      - If EXISTS → Check readme_hash for changes
        - If changed → Re-extract skills
        - If same → Skip

2. For each user with resume uploaded:
   a. Download resume from resume_url
   b. Extract text (PDF parsing)
   c. Send to Groq → Extract skills
   d. Save with source='resume'

3. Skill Deduplication:
   - If same skill found in GitHub AND Resume → Increase proficiency_level
   - Track both sources but don't create duplicate entries
```

---

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/github/connect` | GET | Start OAuth flow (pass `user_id` in query) |
| `/api/github/auth/callback` | GET | OAuth callback from GitHub |
| `/api/github/sync/trigger/{user_id}` | POST | Manually trigger sync for a user |
| `/api/github/cron/run` | POST | Trigger weekly cron for all users |

---

## Next Steps

1.  ✅ Create GitHub OAuth App.
2.  ✅ Update `.env` with Client ID & Secret.
3.  ⏳ I will update the service code to handle:
    *   Repo tracking (avoid duplicates)
    *   Resume skill extraction
    *   Proficiency calculation
4.  ⏳ Deploy to AWS Lambda.
5.  ⏳ Set up AWS EventBridge for weekly CRON trigger.
