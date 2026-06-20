import os
import json
import shutil
import asyncio
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import urllib.request
import urllib.error
import contextlib
import time
import traceback
from collections import deque
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

DATA_DIR = os.path.abspath(os.path.join(os.getcwd(), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
RUNTIME_DIR = os.path.join(DATA_DIR, "Runtime")
HLS_DIR = os.path.join(RUNTIME_DIR, "hls")
SOURCES_FILE = os.path.join(DATA_DIR, "sources.json")

def get_ffmpeg_path():
    local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg.exe")
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
    return "ffmpeg"

logs_queue = deque(maxlen=600)

def should_suppress_log(line: str, name: str) -> bool:
    suppressed = [
        "Skipping invalid undecodable NALU",
        "non-existing PPS",
        "no frame!",
        "Last message repeated",
        "Stream HEVC is not hvc1",
        "mime type is not rfc8216 compliant",
        "Invalid data found when processing input",
        "Error number -10053 occurred",
        "keepalive request failed",
        "Packet corrupt",
        "corrupt input packet",
        "Found duplicated MOOV Atom. Skipped it"
    ]
    for p in suppressed:
        if p in line:
            return True
    return False

def log_msg(msg: str, name: str = "系统"):
    if not msg: return
    if name != "系统" and should_suppress_log(msg, name):
        return
    formatted = f"[{name}] {msg}"
    print(formatted)
    logs_queue.append(formatted)

class AppState:
    def __init__(self):
        self.is_running = False
        self.video_url = ""
        self.audio_url = ""
        self.delay_seconds = 0.0
        self.processes = {}

state = AppState()

async def read_stream(stream, name):
    try:
        while True:
            line = await stream.readline()
            if not line:
                break
            msg = line.decode('utf-8', errors='replace').strip()
            log_msg(msg, name)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        pass

async def stop_process(name):
    p = state.processes.get(name)
    if p:
        try:
            p.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(p.wait(), timeout=3.0)
            if p.returncode is None:
                p.kill()
                await p.wait()
        except Exception:
            pass
        finally:
            state.processes.pop(name, None)

def prepare_directories():
    if os.path.exists(RUNTIME_DIR):
        try:
            shutil.rmtree(RUNTIME_DIR)
        except:
            pass
    os.makedirs(HLS_DIR, exist_ok=True)

def calibration_merge_arguments(video_url: str, audio_url: str, delay_seconds: float):
    args = [
        get_ffmpeg_path(),
        "-nostdin",
        "-hide_banner",
        "-loglevel", "warning",
        "-nostats",
        "-fflags", "+genpts"
    ]
    
    if delay_seconds > 0:
        args.extend(["-itsoffset", f"{delay_seconds:.3f}"])
        
    args.extend([
        "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
        "-thread_queue_size", "4096",
        "-i", video_url,
        "-fflags", "+genpts"
    ])
    
    if delay_seconds < 0:
        args.extend(["-itsoffset", f"{-delay_seconds:.3f}"])
        
    args.extend([
        "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
        "-thread_queue_size", "4096",
        "-i", audio_url,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-filter:a", "aresample=async=1:first_pts=0",
        "-c:a", "aac",
        "-b:a", "128k",
        "-f", "hls", "-hls_time", "4", "-hls_list_size", "30",
        "-hls_delete_threshold", "30",
        "-hls_flags", "delete_segments",
        "-hls_allow_cache", "0",
        "-hls_segment_filename", os.path.join(HLS_DIR, "seg_%05d.ts"),
        os.path.join(HLS_DIR, "index.m3u8")
    ])
    return args

async def start_calibration_merge(video_url, audio_url, delay_seconds):
    args = calibration_merge_arguments(video_url, audio_url, delay_seconds)
    log_msg(f"启动进程 merge", "系统")
    p = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    state.processes["merge"] = p
    asyncio.create_task(read_stream(p.stdout, "merge"))
    asyncio.create_task(read_stream(p.stderr, "merge"))

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await stop_all_processes()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/hls/{file_path:path}")
async def hls_files(file_path: str):
    full_path = os.path.join(HLS_DIR, file_path)
    if os.path.exists(full_path):
        return FileResponse(full_path)
    return JSONResponse(status_code=404, content={"message": "File not found"})

@app.get("/api/sources")
async def get_sources():
    if os.path.exists(SOURCES_FILE):
        try:
            with open(SOURCES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"video_sources": [], "audio_sources": []}

@app.post("/api/sources")
async def save_sources(request: Request):
    data = await request.json()
    with open(SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"success": True}

class ParseM3uReq(BaseModel):
    url: str

@app.post("/api/parse_m3u")
async def parse_m3u(req: ParseM3uReq):
    try:
        req_obj = urllib.request.Request(req.url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        with urllib.request.urlopen(req_obj, timeout=10) as response:
            content = response.read().decode('utf-8', errors='ignore')
        
        channels = []
        lines = content.splitlines()
        for i in range(len(lines)):
            if lines[i].startswith("#EXTINF:"):
                info = lines[i]
                name = info.split(",")[-1].strip()
                for j in range(i+1, min(i+5, len(lines))):
                    if lines[j].strip() and not lines[j].startswith("#"):
                        channels.append({"name": name, "url": lines[j].strip()})
                        break
        return {"success": True, "channels": channels}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/status")
async def get_status():
    return {
        "is_running": state.is_running,
        "video_url": state.video_url,
        "audio_url": state.audio_url,
        "delay_seconds": state.delay_seconds
    }

@app.get("/api/logs")
async def get_logs():
    return {"logs": list(logs_queue)}

@app.post("/api/clear_logs")
async def clear_logs():
    logs_queue.clear()
    return {"success": True}

class StartReq(BaseModel):
    video_url: str
    audio_url: str
    delay_seconds: float

async def stop_all_processes():
    for name in list(state.processes.keys()):
        await stop_process(name)
    state.is_running = False
    log_msg("已停止所有进程")

@app.post("/api/stop")
async def api_stop():
    await stop_all_processes()
    return {"success": True}

async def start_stream(req: StartReq):
    await stop_all_processes()
    state.video_url = req.video_url
    state.audio_url = req.audio_url
    state.delay_seconds = req.delay_seconds
    state.is_running = True

    prepare_directories()
    log_msg("--- 开始合并流 ---")
    log_msg(f"视频: {req.video_url}")
    log_msg(f"音频: {req.audio_url}")
    log_msg(f"时差: {req.delay_seconds} 秒")

    await start_calibration_merge(req.video_url, req.audio_url, req.delay_seconds)

@app.post("/api/start")
async def api_start(req: StartReq):
    try:
        await start_stream(req)
        return {"success": True}
    except Exception as e:
        log_msg(f"启动失败: {e}", "Error")
        return {"success": False, "error": str(e)}

@app.post("/api/apply_delay")
async def api_apply_delay(req: StartReq):
    if state.is_running and state.video_url == req.video_url and state.audio_url == req.audio_url:
        if state.delay_seconds != req.delay_seconds:
            state.delay_seconds = req.delay_seconds
            log_msg(f"时差变更为: {state.delay_seconds} 秒")
            await stop_process("merge")
            prepare_directories()
            await start_calibration_merge(state.video_url, state.audio_url, state.delay_seconds)
    else:
        await start_stream(req)
    return {"success": True}

@app.post("/api/shutdown")
async def shutdown_server():
    os._exit(0)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=38080)
