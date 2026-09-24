import logging
import pathlib

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import APIError

from app.llm import run_turn
from app.schemas import ChatRequest, ChatResponse
from app.session import get_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

STATIC_DIR = pathlib.Path(__file__).parent / "static"

app = FastAPI(title="GuidePass Trip Agent")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session = get_session(req.session_id)
    try:
        reply, itinerary = run_turn(req.message, session)
    except APIError as e:
        return ChatResponse(reply=f"Lỗi kết nối LLM ({e.__class__.__name__}). Kiểm tra LLM_API_KEY trong .env.", itinerary=session.itinerary)
    return ChatResponse(reply=reply, itinerary=itinerary)
