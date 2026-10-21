from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from supabase import create_client
import os

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

# Serve your frontend HTML right at the root URL
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "Backend is running, but index.html was not found in the root directory."

class ChatRequest(BaseModel):
    query: str
    is_admin: bool = False

@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        if req.is_admin:
            files_res = (
                supabase.table("chatbot_files")
                .select("*")
                .or_("access_level.eq.public,access_level.eq.private")
                .execute()
            )
        else:
            files_res = (
                supabase.table("chatbot_files")
                .select("*")
                .eq("access_level", "public")
                .execute()
            )
        
        if not files_res.data:
            return {"reply": "No accessible knowledge files found for this query context.", "sources_used": []}

        file_list = [f["file_name"] for f in files_res.data]
        content_parts = []
        
        for file_name in file_list:
            try:
                public_url_res = supabase.storage.from_("chatbot_files").get_public_url(file_name)
                if public_url_res:
                    content_parts.append(f"Image File Name: {file_name}, Public URL: {public_url_res}")
            except Exception as url_err:
                print(f"Could not get URL for {file_name}: {url_err}")

        prompt_text = f"Available files context: {file_list}. User Query: {req.query}"
        content_parts.append(prompt_text)

        response = gemini_client.models.generate_content(
            model='gemini-3.8-flash', 
            contents=content_parts
        )

        return {"reply": response.text, "sources_used": file_list}

    except Exception as e:
        print(f"CRITICAL CHAT ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
