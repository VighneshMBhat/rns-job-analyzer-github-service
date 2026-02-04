# GitHub Service Setup Guide

## 1. Create GitHub OAuth App

1.  Go to **GitHub Settings** > **Developer settings** > **OAuth Apps**.
2.  Click **New OAuth App**.
3.  Fill form:
    *   **Application Name**: `RNS Job Analyzer`
    *   **Homepage URL**: `http://localhost:3000` (Your frontend)
    *   **Authorization callback URL**: `http://localhost:8001/api/github/auth/callback` 
        *   *(Note: When you deploy to Lambda, update this to the Lambda URL + `/api/github/auth/callback`)*
4.  Copy **Client ID** and **Client Secret**.

## 2. Configure Service

1.  Open `.env` in `github_service/`.
2.  Paste `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`.
3.  Add your `GROQ_API_KEY` (Get from [console.groq.com](https://console.groq.com/keys)).

## 3. Deployment

Since you want this on Lambda:
1.  Run `pip install -t package -r requirements.txt` (or use SAM).
2.  The `main.py` is configured with `Mangum` handler.
3.  Deploy using SAM (similar process to Auth Service).
4.  After deploy, update the **GitHub OAuth App** Callback URL to your new Lambda URL.
