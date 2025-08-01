from fastapi import FastAPI, Query, Header, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from subprocess import run, PIPE
from typing import Optional
import os
import uuid
import json
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="yt-dlp FastAPI Server")

# 🔐 Безопасность
API_TOKEN = os.getenv("API_TOKEN", "supersecrettoken123")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/videos")
COOKIES_PATH = os.getenv("COOKIES_PATH", "/app/cookies.txt")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ✅ Проверка токена
def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ")[1]
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

# 📦 Модель запроса
class DownloadRequest(BaseModel):
    url: str
    format: Optional[str] = "best"
    filename: Optional[str] = None

# 🎬 Получить инфо о видео
@app.get("/info")
def get_video_info(url: str, auth: None = Depends(verify_token)):
    cmd = ["yt-dlp", "--cookies", COOKIES_PATH, "-j", url]
    result = run(cmd, stdout=PIPE, stderr=PIPE, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip())
    try:
        return json.loads(result.stdout)
    except:
        return {"raw": result.stdout.strip()}

# 🔗 Получить прямую ссылку
@app.get("/direct-url")
def get_direct_url(url: str, format: Optional[str] = "best", auth: None = Depends(verify_token)):
    cmd = ["yt-dlp", "--cookies", COOKIES_PATH, "-f", format, "-g", url]
    result = run(cmd, stdout=PIPE, stderr=PIPE, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip())
    return {"direct_url": result.stdout.strip()}

# 📥 Скачать видео на сервер
@app.post("/download")
def download_video(req: DownloadRequest, auth: None = Depends(verify_token)):
    filename = req.filename or f"video_{uuid.uuid4().hex}.mp4"
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    cmd = ["yt-dlp", "--cookies", COOKIES_PATH, "-f", req.format, "-o", filepath, req.url]
    result = run(cmd, stdout=PIPE, stderr=PIPE, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip())
    if not os.path.exists(filepath):
        raise HTTPException(status_code=500, detail="File not found after download")
    return {"status": "success", "filename": filename, "path": filepath}

# 📤 Отдать скачанный файл
@app.get("/download-file")
def serve_file(filename: str, auth: None = Depends(verify_token)):
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, media_type="video/mp4", filename=filename)

