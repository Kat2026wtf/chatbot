import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from supabase import create_client

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

class ChatRequest(BaseModel):
    query: str
    is_admin: bool = False

@app.get("/")
def read_root():
    return {"message": "Chatbot Backend is live! Use /api/sync to sync files."}

def get_access_token():
    """Automatically fetches a fresh Microsoft Graph access token using the refresh token."""
    tenant_id = os.getenv("AZURE_TENANT_ID", "common")
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    payload = {
        "client_id": os.getenv("AZURE_CLIENT_ID"),
        "client_secret": os.getenv("AZURE_CLIENT_SECRET"),
        "refresh_token": os.getenv("ONEDRIVE_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
        "scope": "Files.ReadWrite.All offline_access"
    }
    
    response = requests.post(token_url, data=payload)
    if response.status_code != 200:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to refresh Microsoft token: {response.text}"
        )
    
    return response.json().get("access_token")

@app.get("/api/sync")
def sync_onedrive():
    """Reads her OneDrive folder and updates Supabase automatically via Microsoft Graph API"""
    try:
        # Automatically get a fresh token every time sync is called
        token = get_access_token()
        folder_name = os.getenv("CLIENT_FOLDER_PATH", "ClientChatbotData")

        headers = {"Authorization": f"Bearer {token}"}

        # Fetch items inside the main ClientChatbotData folder
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_name}:/children"
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"OneDrive API Error: {response.text}")

        data = response.json()
        items = data.get("value", [])

        for item in items:
            if "folder" in item:
                subfolder_name = item["name"].lower()
                sub_id = item["id"]

                sub_files_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{sub_id}/children"
                sub_res = requests.get(sub_files_url, headers=headers)

                if sub_res.status_code == 200:
                    sub_items = sub_res.json().get("value", [])
                    for sub_item in sub_items:
                        if "file" in sub_item:
                            file_name = sub_item["name"]
                            file_path = f"/{folder_name}/{item['name']}/{file_name}"
                            level = "public" if subfolder_name == "public" else "private"

                            supabase.table("chatbot_files").upsert({
                                "file_name": file_name,
                                "file_path": file_path,
                                "access_level": level
                            }, on_conflict="file_path").execute()

        return {"status": "Successfully synced her OneDrive folder with auto-refreshed token!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
def chat(req: ChatRequest):
    allowed_levels = ["public"]
    if req.is_admin:
        allowed_levels.append("private")

    files_res = supabase.table("chatbot_files").select("*").in_("access_level", allowed_levels).execute()
    file_list = [f["file_name"] for f in files_res.data]

    prompt = f"Using these available knowledge files {file_list}, answer this visitor query: {req.query}"
    response = gemini_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)

    return {"reply": response.text, "sources_used": file_list}
