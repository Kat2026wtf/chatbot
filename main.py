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
        # Determine allowed access levels based on admin status
        allowed_levels = ["public"]
        if req.is_admin:
            allowed_levels.append("private")

        # Query Supabase DB table for allowed files
        files_res = supabase.table("chatbot_files").select("*").in_("access_level", allowed_levels).execute()
        
    
      # Fallback if no specific DB metadata exists: list storage directly
        if not files_res.data:
            storage_files = supabase.storage.from_("chatbot_files").list("")
            file_list = [f["name"] for f in storage_files]
        else:
            file_list = [f["file_name"] for f in files_res.data]

        if not file_list:
            return {"reply": "No accessible knowledge files found for this query context.", "sources_used": []}

        prompt = f"Using these available knowledge files {file_list}, answer this visitor query: {req.query}"
        response = gemini_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)

        return {"reply": response.text, "sources_used": file_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
