"""
Sync Router - Handles GitHub repository syncing and skill extraction.
Includes CRON job logic for weekly processing.
"""
from fastapi import APIRouter, HTTPException
from supabase import create_client
from app.core.config import settings
from app.services.groq_service import extract_skills_from_readme
from app.services.resume_service import process_user_resume
import requests
import base64
import hashlib

router = APIRouter()
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def compute_hash(content: str) -> str:
    """Compute MD5 hash of content to detect changes."""
    return hashlib.md5(content.encode()).hexdigest()


def process_repo(user_id: str, repo: dict, token: str) -> dict:
    """
    Process a single repository:
    1. Check if already processed (by github_repo_id)
    2. Fetch README.md
    3. Check if content changed (using hash)
    4. Extract skills if new/changed
    5. Store results
    
    Returns processing result.
    """
    repo_id = repo["id"]
    repo_name = repo["name"]
    repo_full_name = repo["full_name"]
    repo_url = repo["html_url"]
    
    # Check if repo already processed
    existing = supabase.table("github_repos").select("id, readme_hash").eq("user_id", user_id).eq("github_repo_id", repo_id).execute()
    
    # Fetch README
    readme_url = f"https://api.github.com/repos/{repo_full_name}/readme"
    readme_resp = requests.get(readme_url, headers={"Authorization": f"Bearer {token}"})
    
    if readme_resp.status_code != 200:
        return {"repo": repo_name, "status": "no_readme"}
    
    content_encoded = readme_resp.json().get("content", "")
    readme_content = base64.b64decode(content_encoded).decode("utf-8")
    content_hash = compute_hash(readme_content)
    
    # Check if content changed
    if existing.data:
        existing_hash = existing.data[0].get("readme_hash")
        if existing_hash == content_hash:
            return {"repo": repo_name, "status": "unchanged"}
        
        # Content changed - update repo record
        supabase.table("github_repos").update({
            "readme_content": readme_content,
            "readme_hash": content_hash,
            "last_processed_at": "now()",
            "updated_at": "now()"
        }).eq("id", existing.data[0]["id"]).execute()
    else:
        # New repo - insert
        supabase.table("github_repos").insert({
            "user_id": user_id,
            "github_repo_id": repo_id,
            "repo_name": repo_name,
            "repo_full_name": repo_full_name,
            "repo_url": repo_url,
            "readme_content": readme_content,
            "readme_hash": content_hash
        }).execute()
    
    # Extract skills from README
    skills = extract_skills_from_readme(readme_content)
    skills_stored = 0
    
    for skill_data in skills:
        skill_name = skill_data.get("skill", "").strip()
        confidence = skill_data.get("confidence", 0.5)
        
        if not skill_name:
            continue
        
        # Check if skill already exists for this user
        skill_exists = supabase.table("user_skills").select("id, proficiency_level, source").eq("user_id", user_id).eq("skill_name_normalized", skill_name.lower()).execute()
        
        if skill_exists.data:
            existing_skill = skill_exists.data[0]
            # If skill exists from resume, increase proficiency
            if existing_skill["source"] == "resume":
                new_proficiency = (existing_skill.get("proficiency_level") or 1) + 1
                supabase.table("user_skills").update({
                    "proficiency_level": new_proficiency,
                    "source_repo": repo_full_name,  # Also found in this repo
                    "updated_at": "now()"
                }).eq("id", existing_skill["id"]).execute()
            # If same skill from different repo, just update confidence if higher
            elif existing_skill["source"] == "github":
                if confidence > (existing_skill.get("confidence_score") or 0):
                    supabase.table("user_skills").update({
                        "confidence_score": confidence,
                        "source_repo": repo_full_name,
                        "updated_at": "now()"
                    }).eq("id", existing_skill["id"]).execute()
        else:
            # New skill - insert
            supabase.table("user_skills").insert({
                "user_id": user_id,
                "skill_name": skill_name,
                "skill_name_normalized": skill_name.lower(),
                "source": "github",
                "source_repo": repo_full_name,
                "confidence_score": confidence,
                "proficiency_level": 1,
                "extracted_at": "now()"
            }).execute()
            skills_stored += 1
    
    return {
        "repo": repo_name,
        "status": "processed",
        "skills_extracted": len(skills),
        "new_skills": skills_stored
    }


@router.post("/trigger/{user_id}")
def trigger_sync(user_id: str):
    """
    Manually triggers a scan of the user's GitHub repositories.
    Also processes the user's resume if available.
    """
    # 1. Get Access Token
    conn_resp = supabase.table("github_connections").select("access_token").eq("user_id", user_id).single().execute()
    
    github_results = []
    if conn_resp.data:
        token = conn_resp.data["access_token"]
        
        # 2. Fetch all repos (up to 100)
        repos_resp = requests.get(
            "https://api.github.com/user/repos?sort=updated&per_page=30",
            headers={"Authorization": f"Bearer {token}"}
        )
        repos = repos_resp.json()
        
        # 3. Process each repo
        for repo in repos:
            result = process_repo(user_id, repo, token)
            github_results.append(result)
        
        # 4. Update last_sync_at
        supabase.table("github_connections").update({
            "last_sync_at": "now()",
            "repos_analyzed": len(repos)
        }).eq("user_id", user_id).execute()
    
    # 5. Also process resume
    resume_result = process_user_resume(user_id)
    
    return {
        "status": "completed",
        "github": {
            "repos_scanned": len(github_results),
            "results": github_results
        },
        "resume": resume_result
    }


@router.post("/cron/run")
def run_cron_job():
    """
    Weekly CRON endpoint - processes ALL users with GitHub connected.
    This should be triggered by AWS EventBridge or similar scheduler.
    """
    # Get all users with GitHub connected
    connections = supabase.table("github_connections").select("user_id").execute()
    
    if not connections.data:
        return {"status": "no_users", "processed": 0}
    
    results = []
    for conn in connections.data:
        user_id = conn["user_id"]
        try:
            result = trigger_sync(user_id)
            results.append({"user_id": user_id, "status": "success", "data": result})
        except Exception as e:
            results.append({"user_id": user_id, "status": "error", "error": str(e)})
    
    return {
        "status": "completed",
        "users_processed": len(results),
        "results": results
    }


@router.post("/resume/{user_id}")
def sync_resume_only(user_id: str):
    """
    Manually trigger resume skill extraction for a specific user.
    """
    result = process_user_resume(user_id)
    return result
