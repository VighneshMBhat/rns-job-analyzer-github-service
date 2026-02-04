"""
Resume Service - Handles resume parsing and skill extraction.
"""
import requests
import io
from app.core.config import settings
from app.services.groq_service import extract_skills_from_resume
from supabase import create_client

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def extract_text_from_pdf(pdf_content: bytes) -> str:
    """
    Extract text from PDF content.
    Uses PyPDF2 for basic text extraction.
    """
    try:
        import PyPDF2
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"PDF extraction error: {e}")
        return ""


def download_resume(resume_url: str) -> bytes | None:
    """
    Download resume file from Supabase Storage URL.
    """
    try:
        response = requests.get(resume_url, timeout=30)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        print(f"Resume download error: {e}")
        return None


def process_user_resume(user_id: str) -> dict:
    """
    Process a user's resume:
    1. Get resume URL from profiles
    2. Download the resume
    3. Extract text
    4. Extract skills using Groq
    5. Store skills in user_skills table
    
    Returns a summary of extracted skills.
    """
    # 1. Get user's resume URL
    profile_res = supabase.table("profiles").select("resume_url, resume_uploaded_at").eq("id", user_id).single().execute()
    
    if not profile_res.data or not profile_res.data.get("resume_url"):
        return {"success": False, "error": "No resume found for user"}
    
    resume_url = profile_res.data["resume_url"]
    
    # 2. Download the resume
    pdf_content = download_resume(resume_url)
    if not pdf_content:
        return {"success": False, "error": "Failed to download resume"}
    
    # 3. Extract text from PDF
    resume_text = extract_text_from_pdf(pdf_content)
    if not resume_text or len(resume_text) < 50:
        return {"success": False, "error": "Could not extract text from resume"}
    
    # 4. Extract skills using Groq
    skills = extract_skills_from_resume(resume_text)
    if not skills:
        return {"success": False, "error": "No skills extracted from resume"}
    
    # 5. Store skills in database
    skills_stored = 0
    for skill_data in skills:
        skill_name = skill_data.get("skill", "").strip()
        confidence = skill_data.get("confidence", 0.5)
        
        if not skill_name:
            continue
        
        # Check if skill already exists for this user
        existing = supabase.table("user_skills").select("id, proficiency_level, source").eq("user_id", user_id).eq("skill_name_normalized", skill_name.lower()).execute()
        
        if existing.data:
            # Skill exists - update proficiency if from different source
            existing_skill = existing.data[0]
            if existing_skill["source"] != "resume":
                # Skill also found in resume - increase proficiency
                new_proficiency = (existing_skill.get("proficiency_level") or 1) + 1
                supabase.table("user_skills").update({
                    "proficiency_level": new_proficiency,
                    "updated_at": "now()"
                }).eq("id", existing_skill["id"]).execute()
        else:
            # New skill - insert
            supabase.table("user_skills").insert({
                "user_id": user_id,
                "skill_name": skill_name,
                "skill_name_normalized": skill_name.lower(),
                "source": "resume",
                "confidence_score": confidence,
                "proficiency_level": 1,
                "extracted_at": "now()"
            }).execute()
            skills_stored += 1
    
    return {
        "success": True,
        "skills_extracted": len(skills),
        "new_skills_stored": skills_stored,
        "skills": [s["skill"] for s in skills]
    }
