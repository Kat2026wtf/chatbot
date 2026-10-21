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
        # 1. Determine allowed access levels based on admin status
        allowed_levels = ["public"]
        if req.is_admin:
            allowed_levels.append("private")

        # 2. Query Supabase DB table for allowed files
        files_res = supabase.table("chatbot_files").select("*").in_("access_level", allowed_levels).execute()
        
        if not files_res.data:
            return {"reply": "No accessible knowledge files found for this query context.", "sources_used": []}

        file_list = [f["file_name"] for f in files_res.data]

        # 3. Gather text prompt and download image bytes from Supabase Storage
        content_parts = []
        
        for file_name in file_list:
            try:
                # Download file bytes from Supabase Storage bucket
                file_bytes = supabase.storage.from_("chatbot_files").download(file_name)
                if file_bytes:
                    content_parts.append({
                        "mime_type": "image/jpeg",
                        "data": file_bytes
                    })
            except Exception as storage_err:
                print(f"Could not download {file_name}: {storage_err}")

        # Add the user's text question to the payload
        content_parts.append(req.query)

        # 4. Send multimodal payload (Images + Text) to Gemini 2.5 Flash
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=content_parts
        )

        return {"reply": response.text, "sources_used": file_list}

    except Exception as e:
        print(f"Backend Chat Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
