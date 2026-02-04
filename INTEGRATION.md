# GitHub Service - Frontend Integration Guide

**Version**: 2.0  
**Last Updated**: 2026-02-05  
**For**: Talento Vision Frontend (Next.js on Vercel)

---

## 🤖 AI Assistant Instructions

> **This section is for the AI assistant helping with frontend integration.**
>
> The backend GitHub service has been deployed. The frontend needs specific corrections to properly integrate with it. **DO NOT disrupt existing features** - only make the targeted changes described below.
>
> **Key Points**:
> 1. The GitHub OAuth flow is handled entirely by the backend Lambda.
> 2. The frontend just needs to redirect users and read data from Supabase.
> 3. Check `github_connections` table for connection status, NOT a boolean field.
> 4. The `profiles` table now has `github_username` and `github_connected_at` fields.

---

## 📡 Backend API Details

| Property | Value |
|----------|-------|
| **Base URL** | `https://12dbzw94lh.execute-api.us-east-1.amazonaws.com/Prod` |
| **Region** | `us-east-1` |
| **Stack** | AWS Lambda (SAM) |

---

## 🔗 API Endpoints

### 1. Connect GitHub

| Property | Value |
|----------|-------|
| **URL** | `GET /api/github/connect?user_id={user_id}` |
| **Purpose** | Starts GitHub OAuth flow |
| **How It Works** | Redirects to GitHub → User authorizes → Callback stores token → Redirects to frontend |

### 2. Trigger Sync (Manual)

| Property | Value |
|----------|-------|
| **URL** | `POST /api/github/sync/trigger/{user_id}` |
| **Purpose** | Scans repos, extracts skills from READMEs, also processes resume |

### 3. Sync Resume Only

| Property | Value |
|----------|-------|
| **URL** | `POST /api/github/sync/resume/{user_id}` |
| **Purpose** | Extracts skills from user's uploaded resume |

---

## ✅ REQUIRED FRONTEND CHANGES

### Issue 1: "GitHub Not Connected" showing incorrectly

**Problem**: Settings page shows "GitHub Not Connected" even after successful OAuth.

**Root Cause**: Frontend is not querying `github_connections` table OR is checking a wrong field.

**Solution**: Query the `github_connections` table to check if connection exists.

```typescript
// ✅ CORRECT WAY to check if GitHub is connected
async function checkGitHubConnection(userId: string) {
  const { data, error } = await supabase
    .from('github_connections')
    .select('id, github_username, last_sync_at')
    .eq('user_id', userId)
    .single();
  
  if (data) {
    return {
      isConnected: true,
      username: data.github_username,
      lastSync: data.last_sync_at
    };
  }
  
  return { isConnected: false };
}
```

**Alternative**: Check `profiles.github_connected_at` field:

```typescript
// Also valid - check profiles table
const { data } = await supabase
  .from('profiles')
  .select('github_username, github_connected_at')
  .eq('id', userId)
  .single();

const isConnected = !!data?.github_connected_at;
```

---

### Issue 2: Connect to GitHub button implementation

**Current Button Location**: Settings page → GitHub Integration section

**Correct Implementation**:

```typescript
// When user clicks "Connect to GitHub" button
function handleConnectGitHub() {
  const userId = /* get current user's ID from auth context */;
  const backendUrl = "https://12dbzw94lh.execute-api.us-east-1.amazonaws.com/Prod";
  
  // Redirect to backend OAuth endpoint
  window.location.href = `${backendUrl}/api/github/connect?user_id=${userId}`;
}
```

---

### Issue 3: Handle OAuth callback redirect

**After successful GitHub OAuth**, user is redirected to:
```
https://talento-vision.vercel.app/dashboard?feature=github_connected
```

**Frontend should**:
1. Check for `?feature=github_connected` query param
2. Show a success toast/notification
3. Optionally trigger a sync

```typescript
// In dashboard page (useEffect or on mount)
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  
  if (params.get('feature') === 'github_connected') {
    // Show success message
    toast.success('GitHub connected successfully!');
    
    // Clean URL
    window.history.replaceState({}, '', '/dashboard');
    
    // Optionally trigger sync
    triggerGitHubSync(userId);
  }
  
  if (params.get('error') === 'github_connection_failed') {
    const detail = params.get('detail') || 'Unknown error';
    toast.error(`GitHub connection failed: ${detail}`);
    window.history.replaceState({}, '', '/dashboard');
  }
}, []);
```

---

### Issue 4: Trigger sync after connection

**After GitHub is connected**, trigger a sync to fetch repos and extract skills:

```typescript
async function triggerGitHubSync(userId: string) {
  const backendUrl = "https://12dbzw94lh.execute-api.us-east-1.amazonaws.com/Prod";
  
  try {
    const response = await fetch(
      `${backendUrl}/api/github/sync/trigger/${userId}`,
      { method: 'POST' }
    );
    
    if (response.ok) {
      const result = await response.json();
      console.log('Sync completed:', result);
      // Refresh skills display
    }
  } catch (error) {
    console.error('Sync failed:', error);
  }
}
```

---

### Issue 5: Display extracted skills

**Skills are stored in `user_skills` table**:

```typescript
// Fetch user's skills
async function fetchUserSkills(userId: string) {
  const { data, error } = await supabase
    .from('user_skills')
    .select('skill_name, source, confidence_score, proficiency_level, source_repo')
    .eq('user_id', userId)
    .order('proficiency_level', { ascending: false });
  
  return data;
}
```

**Display logic**:
- `source = 'github'` → Skill from repository
- `source = 'resume'` → Skill from resume
- `proficiency_level > 1` → Found in multiple sources (stronger skill)

---

## 🗄️ Database Tables Reference

### `github_connections`

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid | Primary key |
| `user_id` | uuid | FK to profiles |
| `github_username` | text | GitHub username |
| `github_avatar_url` | text | Avatar URL |
| `access_token` | text | OAuth token (encrypted) |
| `last_sync_at` | timestamp | Last repo scan time |
| `repos_analyzed` | integer | Count of repos scanned |

### `profiles` (Updated fields)

| Column | Type | Description |
|--------|------|-------------|
| `github_username` | text | GitHub username (set on connect) |
| `github_connected_at` | timestamp | When GitHub was connected |
| `resume_url` | text | URL to uploaded resume |

### `user_skills`

| Column | Type | Description |
|--------|------|-------------|
| `skill_name` | text | Skill name (e.g., "React") |
| `source` | enum | `github`, `resume`, `manual` |
| `source_repo` | text | Repo where skill was found |
| `confidence_score` | numeric | AI confidence (0.0-1.0) |
| `proficiency_level` | integer | Higher = stronger skill |

---

## 🔄 Complete Flow Diagram

```
User clicks "Connect to GitHub"
         │
         ▼
Frontend redirects to:
  /api/github/connect?user_id=xxx
         │
         ▼
Backend redirects to GitHub OAuth
         │
         ▼
User authorizes on GitHub
         │
         ▼
GitHub redirects to:
  /api/github/auth/callback?code=xxx&state=user_id
         │
         ▼
Backend:
  1. Exchanges code for access_token
  2. Gets GitHub user info
  3. Inserts into github_connections
  4. Updates profiles.github_connected_at
         │
         ▼
Backend redirects to:
  https://talento-vision.vercel.app/dashboard?feature=github_connected
         │
         ▼
Frontend:
  1. Detects ?feature=github_connected
  2. Shows success toast
  3. (Optional) Calls /sync/trigger/{user_id}
         │
         ▼
Sync Service:
  1. Fetches all repos from GitHub API
  2. Reads README.md from each repo
  3. Sends to Groq AI for skill extraction
  4. Stores skills in user_skills table
  5. Also processes resume if uploaded
```

---

## ⚠️ DO NOT CHANGE

The following should remain unchanged:
- Login/Signup flow
- Supabase authentication
- Resume upload functionality (Step 4)
- Dashboard layout
- Settings page layout (only update GitHub connection check logic)

---

## 📋 Checklist for Frontend Developer

- [ ] Update GitHub connection check to query `github_connections` table
- [ ] Ensure "Connect to GitHub" button redirects to backend URL with `user_id`
- [ ] Handle `?feature=github_connected` redirect on dashboard
- [ ] Handle `?error=github_connection_failed` redirect on dashboard
- [ ] Add function to trigger sync after connection
- [ ] Display skills from `user_skills` table

---

## 📞 Support

**Backend API URL**: `https://12dbzw94lh.execute-api.us-east-1.amazonaws.com/Prod`

**Test the connection endpoint**:
```
GET https://12dbzw94lh.execute-api.us-east-1.amazonaws.com/Prod/api/github/connect?user_id=test-user-id
```
(This should redirect to GitHub OAuth page)
