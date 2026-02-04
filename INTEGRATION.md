# GitHub Service Integration Guide

**For Frontend Developer (Talento Vision)**

---

## 🚀 Service Overview

The GitHub Service extracts technical skills from user's:
1. **GitHub Repositories** (README.md files)
2. **Uploaded Resumes** (PDF files in Supabase Storage)

It uses **Groq AI** (Llama 3.3) for intelligent skill extraction.

---

## 📡 Base URL

```
https://12dbzw94lh.execute-api.us-east-1.amazonaws.com/Prod
```

---

## 🔗 API Endpoints

### 1. Connect GitHub (OAuth Flow)

**Start the OAuth flow to link user's GitHub account.**

| Property | Value |
|----------|-------|
| **Method** | `GET` |
| **URL** | `/api/github/connect?user_id={user_id}` |
| **Auth** | None (public) |

**Frontend Implementation:**

```javascript
// When user clicks "Connect GitHub" button
function connectGitHub(userId) {
  const baseUrl = "https://12dbzw94lh.execute-api.us-east-1.amazonaws.com/Prod";
  window.location.href = `${baseUrl}/api/github/connect?user_id=${userId}`;
}
```

**Flow:**
1. User clicks "Connect GitHub" → Redirects to GitHub OAuth
2. User authorizes the app
3. GitHub redirects back to our Lambda
4. Lambda stores the access token in `github_connections` table
5. Lambda redirects user to: `https://talento-vision.vercel.app/dashboard?feature=github_connected`

---

### 2. Trigger Repository Sync (Manual)

**Manually trigger a scan of user's repositories.**

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | `/api/github/sync/trigger/{user_id}` |
| **Auth** | `Authorization: Bearer {access_token}` (optional, for protected routes) |

**Request:**
```bash
POST https://12dbzw94lh.execute-api.us-east-1.amazonaws.com/Prod/api/github/sync/trigger/123e4567-e89b-12d3-a456-426614174000
```

**Response:**
```json
{
  "status": "completed",
  "github": {
    "repos_scanned": 15,
    "results": [
      {"repo": "my-project", "status": "processed", "skills_extracted": 5, "new_skills": 3},
      {"repo": "another-repo", "status": "unchanged"},
      {"repo": "old-repo", "status": "no_readme"}
    ]
  },
  "resume": {
    "success": true,
    "skills_extracted": 12,
    "new_skills_stored": 8,
    "skills": ["Python", "React", "AWS", "Docker", "PostgreSQL", ...]
  }
}
```

---

### 3. Sync Resume Only

**Extract skills from user's uploaded resume.**

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | `/api/github/sync/resume/{user_id}` |

**Response:**
```json
{
  "success": true,
  "skills_extracted": 12,
  "new_skills_stored": 8,
  "skills": ["Python", "React", "AWS", "Docker", "PostgreSQL", ...]
}
```

---

### 4. Weekly CRON Job (Backend Only)

**Processes ALL users with GitHub connected. Triggered by AWS EventBridge.**

| Property | Value |
|----------|-------|
| **Method** | `POST` |
| **URL** | `/api/github/sync/cron/run` |

> ⚠️ This endpoint should NOT be called from frontend. It's for scheduled jobs.

---

## 🗄️ Database Tables

### `user_skills` (Skills are stored here)

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | uuid | User's profile ID |
| `skill_name` | text | Skill name (e.g., "React") |
| `source` | enum | `github`, `resume`, or `manual` |
| `source_repo` | text | GitHub repo where skill was found |
| `confidence_score` | numeric | AI confidence (0.0-1.0) |
| `proficiency_level` | integer | Higher = found in multiple sources |

### `github_connections` (OAuth tokens)

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | uuid | User's profile ID |
| `github_username` | text | GitHub username |
| `access_token` | text | OAuth access token |
| `last_sync_at` | timestamp | Last time repos were scanned |

### `github_repos` (Processed repositories)

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | uuid | User's profile ID |
| `repo_full_name` | text | e.g., "username/repo-name" |
| `readme_content` | text | Stored README content |
| `readme_hash` | text | Hash to detect changes |

---

## 🎨 Frontend Integration Examples

### Check if GitHub is Connected

```javascript
// Query Supabase directly
const { data } = await supabase
  .from('github_connections')
  .select('github_username, last_sync_at')
  .eq('user_id', userId)
  .single();

if (data) {
  console.log(`Connected as: ${data.github_username}`);
} else {
  // Show "Connect GitHub" button
}
```

### Display User Skills

```javascript
// Fetch skills from Supabase
const { data: skills } = await supabase
  .from('user_skills')
  .select('skill_name, source, confidence_score, proficiency_level')
  .eq('user_id', userId)
  .order('proficiency_level', { ascending: false });

// skills = [
//   { skill_name: "Python", source: "github", confidence_score: 0.95, proficiency_level: 3 },
//   { skill_name: "React", source: "resume", confidence_score: 0.88, proficiency_level: 2 },
//   ...
// ]
```

### Trigger Sync After Resume Upload

```javascript
// After user uploads resume to Supabase Storage
async function onResumeUploaded(userId) {
  const response = await fetch(
    `https://12dbzw94lh.execute-api.us-east-1.amazonaws.com/Prod/api/github/sync/resume/${userId}`,
    { method: 'POST' }
  );
  const result = await response.json();
  console.log(`Extracted ${result.skills_extracted} skills from resume`);
}
```

---

## 🤖 AI Instructions for Frontend Developer's Assistant

> **For the AI assistant helping with frontend integration:**
>
> This backend service is deployed on AWS Lambda. When integrating:
>
> 1. **GitHub OAuth Flow**: The frontend should redirect users to `/api/github/connect?user_id=xxx`. After OAuth, users return to `/dashboard?feature=github_connected`.
>
> 2. **No CORS Issues**: The Lambda has CORS configured for `https://talento-vision.vercel.app`.
>
> 3. **Supabase Direct Access**: Frontend can directly query `user_skills` and `github_connections` tables using the Supabase JS client. The backend updates these tables.
>
> 4. **Skill Proficiency**: If `proficiency_level > 1`, the skill was found in multiple sources (both GitHub and Resume), indicating stronger proficiency.
>
> 5. **Callback Handling**: When user returns with `?feature=github_connected`, show a success toast and optionally trigger a sync.

---

## ⚠️ Important: Update GitHub OAuth App

**The backend owner must update the GitHub OAuth App callback URL to:**

```
https://12dbzw94lh.execute-api.us-east-1.amazonaws.com/Prod/api/github/auth/callback
```

Go to: GitHub → Settings → Developer settings → OAuth Apps → Talento Vision → Edit

---

## 📞 Contact

- **Backend Service**: GitHub Service (AWS Lambda)
- **API Gateway**: `https://12dbzw94lh.execute-api.us-east-1.amazonaws.com/Prod`
- **Region**: us-east-1
