import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from supabase import create_client

app = FastAPI()

# Allow cross-origin requests from your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

class ChatRequest(BaseModel):
    query: str
    is_admin: bool = False

@app.get("/")
def read_root():
    return {"message": "Chatbot Backend is live with Supabase Storage!"}

@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        allowed_levels = ["public"]
        if req.is_admin:
            allowed_levels.append("private")

        files_res = supabase.table("chatbot_files").select("*").in_("access_level", allowed_levels).execute()
        
        if not files_res.data:
            return {"reply": "No accessible knowledge files found for this query context.", "sources_used": []}

        file_list = [f["file_name"] for f in files_res.data]
        content_parts = []
        
        # Build file list description and collect public image URLs for Gemini Vision
        for file_name in file_list:
            try:
                # Get the public URL instead of raw bytes download
                public_url_res = supabase.storage.from_("chatbot_files").get_public_url(file_name)
                if public_url_res:
                    content_parts.append(f"Image File Name: {file_name}, Public URL: {public_url_res}")
            except Exception as url_err:
                print(f"Could not get URL for {file_name}: {url_err}")

        # Add the user's question and context
        prompt_text = f"Available files context: {file_list}. User Query: {req.query}"
        content_parts.append(prompt_text)

        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=content_parts
        )

        return {"reply": response.text, "sources_used": file_list}

    except Exception as e:
        print(f"CRITICAL CHAT ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
