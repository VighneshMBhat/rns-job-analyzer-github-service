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
    5. Diff skills (New vs Old) to update user_skills weights
    6. Store results with extracted_skills
    """
    repo_id = repo["id"]
    repo_name = repo["name"]
    repo_full_name = repo["full_name"]
    repo_url = repo["html_url"]
    
    # Check if repo already processed
    existing = supabase.table("github_repos").select("id, readme_hash, extracted_skills").eq("user_id", user_id).eq("github_repo_id", repo_id).execute()
    
    # Fetch README
    readme_url = f"https://api.github.com/repos/{repo_full_name}/readme"
    readme_resp = requests.get(readme_url, headers={"Authorization": f"Bearer {token}"})
    
    if readme_resp.status_code != 200:
        return {"repo": repo_name, "status": "no_readme"}
    
    content_encoded = readme_resp.json().get("content", "")
    readme_content = base64.b64decode(content_encoded).decode("utf-8")
    content_hash = compute_hash(readme_content)
    
    # Check if content changed
    old_skills_list = []
    if existing.data:
        existing_record = existing.data[0]
        # If hash matches AND we have extracted_skills (migration check), skip
        if existing_record.get("readme_hash") == content_hash and existing_record.get("extracted_skills") is not None:
            return {"repo": repo_name, "status": "unchanged"}
        
        # If we are here, either content changed OR we need to backfill extracted_skills
        if existing_record.get("extracted_skills"):
            old_skills_list = existing_record["extracted_skills"]
    
    # Extract skills from README
    skills = extract_skills_from_readme(readme_content)
    
    # Helper to clean skill names
    def clean_skills(s_list):
        return {s.get("skill", "").strip().lower(): s for s in s_list if s.get("skill")}

    old_map = clean_skills(old_skills_list)
    new_map = clean_skills(skills)
    
    old_set = set(old_map.keys())
    new_set = set(new_map.keys())

    added_skills = new_set - old_set
    removed_skills = old_set - new_set

    skills_processed = 0

    # 1. Handle Added Skills (Increment)
    for skill_key in added_skills:
        skill_data = new_map[skill_key]
        skill_name = skill_data.get("skill")
        confidence = skill_data.get("confidence", 0.5)

        # Upsert logic
        existing_user_skill = supabase.table("user_skills").select("*").eq("user_id", user_id).eq("skill_name_normalized", skill_key).execute()
        
        if existing_user_skill.data:
             # Increment proficiency
             current_prof = existing_user_skill.data[0].get("proficiency_level", 1)
             supabase.table("user_skills").update({
                 "proficiency_level": current_prof + 1,
                 "updated_at": "now()"
             }).eq("id", existing_user_skill.data[0]["id"]).execute()
        else:
             # Insert new
             supabase.table("user_skills").insert({
                 "user_id": user_id,
                 "skill_name": skill_name,
                 "skill_name_normalized": skill_key,
                 "source": "github",
                 "source_repo": repo_full_name,
                 "confidence_score": confidence,
                 "proficiency_level": 1,
                 "extracted_at": "now()"
             }).execute()
        skills_processed += 1

    # 2. Handle Removed Skills (Decrement)
    for skill_key in removed_skills:
        existing_user_skill = supabase.table("user_skills").select("*").eq("user_id", user_id).eq("skill_name_normalized", skill_key).execute()
        if existing_user_skill.data:
             record = existing_user_skill.data[0]
             current_prof = record.get("proficiency_level", 1)
             
             if current_prof > 1:
                 # Decrement
                 supabase.table("user_skills").update({
                     "proficiency_level": current_prof - 1,
                     "updated_at": "now()"
                 }).eq("id", record["id"]).execute()
             elif record["source"] == "github":
                 # If prof is 1 and source is github, it's gone
                 supabase.table("user_skills").delete().eq("id", record["id"]).execute()
                 
    # 3. Update github_repos record
    if existing.data:
        supabase.table("github_repos").update({
            "readme_content": readme_content,
            "readme_hash": content_hash,
            "extracted_skills": skills,  # Store for next diff
            "last_processed_at": "now()",
            "updated_at": "now()"
        }).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase.table("github_repos").insert({
            "user_id": user_id,
            "github_repo_id": repo_id,
            "repo_name": repo_name,
            "repo_full_name": repo_full_name,
            "repo_url": repo_url,
            "readme_content": readme_content,
            "readme_hash": content_hash,
            "extracted_skills": skills
        }).execute()
    
    return {
        "repo": repo_name,
        "status": "processed",
        "skills_extracted": len(skills),
        "changes": {
            "added": len(added_skills),
            "removed": len(removed_skills)
        }
    }


@router.post("/trigger/{user_id}")
def trigger_sync(user_id: str):
    """
    Manually triggers a scan of the user's GitHub repositories.
    Also processes the user's resume if available.
    """
    try:
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
            
            if repos_resp.status_code == 200:
                repos = repos_resp.json()
                
                # 3. Process each repo
                for repo in repos:
                    try:
                        result = process_repo(user_id, repo, token)
                        github_results.append(result)
                    except Exception as repo_e:
                        print(f"Failed to process repo {repo.get('name')}: {repo_e}")
                        continue
                
                # 4. Update last_sync_at
                supabase.table("github_connections").update({
                    "last_sync_at": "now()",
                    "repos_analyzed": len(repos)
                }).eq("user_id", user_id).execute()
        
        # 5. Also process resume
        resume_result = {}
        try:
            resume_result = process_user_resume(user_id)
        except Exception as resume_e:
            print(f"Resume processing failed: {resume_e}")
            resume_result = {"success": False, "error": str(resume_e)}
        
        return {
            "status": "completed",
            "github": {
                "repos_scanned": len(github_results),
                "results": github_results
            },
            "resume": resume_result
        }
    except Exception as e:
        print(f"Trigger sync failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


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
