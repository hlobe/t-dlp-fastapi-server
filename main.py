from fastapi import FastAPI, Query, Header, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from subprocess import run, PIPE
from typing import Optional
from pathlib import Path
import os
import uuid
import json
import time
import hmac
import hashlib
import base64
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="yt-dlp FastAPI Server")

# 🔐 Безопасность
API_TOKEN      = os.getenv("API_TOKEN", "supersecrettoken123")
DOWNLOAD_DIR   = os.getenv("DOWNLOAD_DIR", "/tmp/videos")
COOKIES_PATH   = os.getenv("COOKIES_PATH", "/app/cookies.txt")
SECRET_KEY     = os.getenv("SIGN_SECRET", "supersecretkey").encode()
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

# 📦 Модель запроса
class DownloadRequest(BaseModel):
    url: str
    format: Optional[str]   = "best"
    filename: Optional[str] = None

class SignRequest(BaseModel):
    filename: str
    expires_in: int = 3600

def make_signed_url(filename: str, expires_in: int) -> str:
    exp = int(time.time()) + expires_in
    msg = f"{filename}:{exp}".encode()
    sig = base64.urlsafe_b64encode(hmac.new(SECRET_KEY, msg, hashlib.sha256).digest()).rstrip(b"=")
    return f"/download-file?filename={filename}&exp={exp}&sig={sig.decode()}"

# 🎬 Информация о видео
@app.get("/info")
def get_video_info(url: str, auth: None = Depends(verify_token)):
    cmd = ["yt-dlp", "--cookies", COOKIES_PATH, "-j", url]
    result = run(cmd, stdout=PIPE, stderr=PIPE, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip())
    return json.loads(result.stdout)

# 🔗 Прямая ссылка на поток
@app.get("/direct-url")
def get_direct_url(url: str, format: str = "best", auth: None = Depends(verify_token)):
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

# 📤 Обычная отдача скачанного файла (Bearer-защита)
@app.get("/download-file")
def serve_file(
    filename: str,
    auth: Optional[str] = Header(None),
    exp: Optional[int] = Query(None),
    sig: Optional[str] = Query(None),
):
    # Если передали exp+sig — проверяем подпись и срок жизни
    if exp is not None and sig is not None:
        msg = f"{filename}:{exp}".encode()
        good_sig = base64.urlsafe_b64encode(hmac.new(SECRET_KEY, msg, hashlib.sha256).digest()).rstrip(b"=").decode()
        if sig != good_sig or time.time() > exp:
            raise HTTPException(status_code=403, detail="Invalid or expired link")
    else:
        # Иначе — проверяем Bearer-токен
        verify_token(auth)

    filepath = Path(DOWNLOAD_DIR) / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    # Отдаём реально скачанный контейнер, media_type определяется автоматически
    return FileResponse(filepath, filename=filename)

# 🔏 Генерация «signed URL»
@app.post("/download-signed")
def download_signed(req: SignRequest, auth: None = Depends(verify_token)):
    path = Path(DOWNLOAD_DIR) / req.filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return {"url": make_signed_url(req.filename, req.expires_in)}

