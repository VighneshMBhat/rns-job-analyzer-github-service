"""
Resume Service - Handles resume parsing and skill extraction.
Uses PyPDF2 as primary extractor, falls back to Tesseract OCR if needed.
"""
import requests
import io
import tempfile
import os
from app.core.config import settings
from app.services.groq_service import extract_skills_from_resume
from supabase import create_client

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def extract_text_with_pypdf2(pdf_content: bytes) -> str:
    """
    PRIMARY METHOD: Extract text using PyPDF2.
    Works for text-based PDFs (most modern resumes).
    """
    try:
        import PyPDF2
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        print(f"PyPDF2 extraction error: {e}")
        return ""


def extract_text_with_pdfplumber(pdf_content: bytes) -> str:
    """
    SECONDARY METHOD: Extract text using pdfplumber.
    Often better than PyPDF2 for complex layouts.
    """
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except Exception as e:
        print(f"pdfplumber extraction error: {e}")
        return ""


def extract_text_with_tesseract(pdf_content: bytes) -> str:
    """
    FALLBACK METHOD: Use Tesseract OCR for scanned/image PDFs.
    Converts PDF to images, then runs OCR on each page.
    """
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        
        # Convert PDF to images
        images = convert_from_bytes(pdf_content, dpi=200)
        
        text = ""
        for i, image in enumerate(images):
            # Run OCR on each page
            page_text = pytesseract.image_to_string(image)
            if page_text:
                text += f"\n--- Page {i+1} ---\n{page_text}"
        
        return text.strip()
    except Exception as e:
        print(f"Tesseract OCR error: {e}")
        return ""


def extract_text_from_pdf(pdf_content: bytes) -> str:
    """
    Smart PDF text extraction with fallback logic:
    
    1. Try PyPDF2 (fast, works for text-based PDFs)
    2. If text too short, try pdfplumber (better for complex layouts)
    3. If still no luck, try Tesseract OCR (for scanned PDFs)
    
    Returns extracted text.
    """
    MIN_TEXT_LENGTH = 100  # Minimum chars to consider extraction successful
    
    # Step 1: Try PyPDF2 (fastest)
    print("Attempting PyPDF2 extraction...")
    text = extract_text_with_pypdf2(pdf_content)
    
    if len(text) >= MIN_TEXT_LENGTH:
        print(f"PyPDF2 succeeded: {len(text)} chars extracted")
        return text
    
    # Step 2: Try pdfplumber (better for complex layouts)
    print("PyPDF2 insufficient, trying pdfplumber...")
    text = extract_text_with_pdfplumber(pdf_content)
    
    if len(text) >= MIN_TEXT_LENGTH:
        print(f"pdfplumber succeeded: {len(text)} chars extracted")
        return text
    
    # Step 3: Try Tesseract OCR (for scanned PDFs)
    print("pdfplumber insufficient, trying Tesseract OCR...")
    text = extract_text_with_tesseract(pdf_content)
    
    if len(text) >= MIN_TEXT_LENGTH:
        print(f"Tesseract OCR succeeded: {len(text)} chars extracted")
        return text
    
    # All methods failed
    print(f"All extraction methods failed. Best result: {len(text)} chars")
    return text  # Return whatever we got


def download_resume(resume_url: str) -> bytes | None:
    """
    Download resume file from Supabase Storage URL.
    """
    try:
        response = requests.get(resume_url, timeout=30)
        if response.status_code == 200:
            return response.content
        print(f"Resume download failed: HTTP {response.status_code}")
        return None
    except Exception as e:
        print(f"Resume download error: {e}")
        return None


def process_user_resume(user_id: str) -> dict:
    """
    Process a user's resume:
    1. Get resume URL from profiles
    2. Download the resume
    3. Extract text (PyPDF2 → pdfplumber → Tesseract OCR)
    4. Extract skills using Groq AI
    5. Store skills in user_skills table
    
    Returns a summary of extracted skills.
    """
    # 1. Get user's resume URL
    profile_res = supabase.table("profiles").select("resume_url, resume_uploaded_at").eq("id", user_id).single().execute()
    
    if not profile_res.data or not profile_res.data.get("resume_url"):
        return {"success": False, "error": "No resume found for user"}
    
    resume_url = profile_res.data["resume_url"]
    
    # Ensure we have a full URL (not just a path)
    if resume_url and not resume_url.startswith("http"):
        # Construct full Supabase Storage URL
        resume_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/resumes/{resume_url}"
        print(f"Constructed full resume URL: {resume_url}")
    
    # 2. Download the resume
    pdf_content = download_resume(resume_url)
    if not pdf_content:
        return {"success": False, "error": "Failed to download resume"}
    
    # 3. Extract text from PDF (with fallback logic)
    resume_text = extract_text_from_pdf(pdf_content)
    if not resume_text or len(resume_text) < 50:
        return {"success": False, "error": "Could not extract text from resume (may be image-based without OCR support)"}
    
    # 4. Extract skills using Groq AI
    skills = extract_skills_from_resume(resume_text)
    if not skills:
        return {"success": False, "error": "No skills extracted from resume"}
    
    # --- START: History & Cleanup ---
    # 5a. Archive existing resume skills
    current_resume_skills = supabase.table("user_skills").select("*").eq("user_id", user_id).eq("source", "resume").execute()
    
    if current_resume_skills.data:
        history_entries = []
        for s in current_resume_skills.data:
            history_entries.append({
                "user_id": user_id,
                "skill_name": s["skill_name"],
                "proficiency_level": s["proficiency_level"],
                "confidence_score": s["confidence_score"],
                "source_resume_url": resume_url,
                "meta_data": {"original_id": s["id"], "source_repo": s.get("source_repo")}
            })
        
        if history_entries:
            try:
                supabase.table("resume_skill_history").insert(history_entries).execute()
            except Exception as e:
                print(f"Failed to archive resume history: {e}")

        # 5b. Cleanup (Delete pure resume skills, Demote mixed skills)
        for s in current_resume_skills.data:
            if s.get("source_repo"):
                # Mixed source (Resume + GitHub) -> Convert to GitHub only
                # Decrement proficiency (remove resume contribution)
                new_prof = max(1, (s.get("proficiency_level") or 1) - 1)
                supabase.table("user_skills").update({
                    "source": "github",
                    "proficiency_level": new_prof,
                    "updated_at": "now()"
                }).eq("id", s["id"]).execute()
            else:
                # Pure resume skill -> Delete
                supabase.table("user_skills").delete().eq("id", s["id"]).execute()
    # --- END: History & Cleanup ---

    # 5. Store skills in database
    skills_stored = 0
    skills_updated = 0
    
    for skill_data in skills:
        skill_name = skill_data.get("skill", "").strip()
        confidence = skill_data.get("confidence", 0.5)
        
        if not skill_name:
            continue
        
        # Check if skill already exists for this user
        existing = supabase.table("user_skills").select("id, proficiency_level, source").eq("user_id", user_id).eq("skill_name_normalized", skill_name.lower()).execute()
        
        if existing.data:
            # Skill exists
            existing_skill = existing.data[0]
            
            # If it's "github" source (since we cleared "resume" ones), we merge it
            if existing_skill["source"] == "github":
                # Convert to "resume" source (OR keep github? Code logic prefer merging into one)
                # The prompt implies we should track "from this resume".
                # But our unique constraint checks (user, name, source).
                # If we want to allow "GitHub" row and "Resume" row to exist separately, 
                # we should NOT query by name only.
                # BUT user explicitly said "should not be repetitive". So merging is correct.
                # We'll allow "resume" to take precedence as source for mixed? 
                # Or keep "github" and just increment?
                # Previous logic was: if resume, update. If github, update.
                
                # Let's sticking to: "If found in resume, ensuring it reflects that."
                # We will Set source='resume' (marking it as also in resume) and increment.
                # NOTE: This effectively makes it "mixed" again.
                
                new_proficiency = (existing_skill.get("proficiency_level") or 1) + 1
                supabase.table("user_skills").update({
                    "source": "resume", # Mark as resume source (so next time we know to clean it)
                    "proficiency_level": new_proficiency,
                    "updated_at": "now()"
                }).eq("id", existing_skill["id"]).execute()
                skills_updated += 1
            elif existing_skill["source"] == "resume": 
                # Already exists? (Shouldn't happen unless duplicate in same resume text or we just inserted it)
                pass 
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
        "extraction_method": "PyPDF2/pdfplumber/Tesseract (auto)",
        "text_length": len(resume_text),
        "skills_extracted": len(skills),
        "new_skills_stored": skills_stored,
        "existing_skills_updated": skills_updated,
        "skills": [s["skill"] for s in skills]
    }
