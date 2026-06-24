"""FastAPI application: REST endpoints + static web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent import agent
from app.chat import chat_manager
from app.config import settings
from app.llm import llm
from app.schemas import (
    AskRequest,
    AskResponse,
    ChatRequest,
    ChatResponse,
    CreateSessionResponse,
    IngestRequest,
    IngestResponse,
    MergeRequest,
    PersonEditRequest,
    Prediction,
    PredictRequest,
    SelfProfileView,
    SessionDetail,
    SessionSummary,
    VoiceConfirmRequest,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Human Memory Agent", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm": llm.health(), "memory": agent.store.stats()}


@app.get("/api/stats")
def stats() -> dict:
    return agent.store.stats()


@app.post("/api/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest) -> IngestResponse:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")
    return agent.ingest(req.text, source=req.source)


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is empty")
    return agent.ask(req.query)


@app.post("/api/predict", response_model=Prediction)
def predict(req: PredictRequest) -> Prediction:
    if not req.person.strip() or not req.situation.strip():
        raise HTTPException(status_code=400, detail="person and situation are required")
    return agent.predict(req.person, req.situation)


@app.get("/api/persons")
def persons() -> list[dict]:
    return [p.model_dump() for p in agent.store.persona.all()]


@app.get("/api/person/{name}")
def person(name: str) -> dict:
    persona = agent.store.persona.get(name)
    if not persona:
        raise HTTPException(status_code=404, detail="person not found")
    return {
        "persona": persona.model_dump(),
        "graph": agent.store.semantic.neighbors(persona.name),
    }


@app.post("/api/person/merge")
def person_merge(req: MergeRequest) -> dict:
    source = req.source.strip()
    target = req.target.strip()
    if not source or not target:
        raise HTTPException(status_code=400, detail="source and target are required")
    if source == target:
        raise HTTPException(status_code=400, detail="cannot merge a person into itself")
    if agent.store.persona.get_exact(source) is None:
        raise HTTPException(status_code=404, detail="source person not found")
    if agent.store.persona.get_exact(target) is None:
        raise HTTPException(status_code=404, detail="target person not found")
    agent.resolver.merge_person(source, target)
    merged = agent.store.persona.get(target)
    return {
        "status": "merged",
        "source": source,
        "target": target,
        "persona": merged.model_dump() if merged else None,
    }


@app.patch("/api/person/{name}")
def person_edit(name: str, req: PersonEditRequest) -> dict:
    if agent.store.persona.get_exact(name) is None:
        raise HTTPException(status_code=404, detail="person not found")
    for trait in req.remove_traits:
        agent.store.semantic.remove_trait(name, trait)
    for pref in req.remove_preferences:
        agent.store.semantic.remove_preference(name, pref)
    persona = agent.store.persona.update(
        name,
        summary=req.summary,
        remove_traits=req.remove_traits,
        remove_preferences=req.remove_preferences,
        remove_pattern_indices=req.remove_pattern_indices,
        add_aliases=req.add_aliases,
    )
    agent.store.commit()
    return {
        "status": "updated",
        "persona": persona.model_dump() if persona else None,
        "graph": agent.store.semantic.neighbors(name),
    }


@app.get("/api/graph")
def graph() -> dict:
    return agent.store.semantic.export()


@app.get("/api/self", response_model=SelfProfileView)
def self_profile() -> SelfProfileView:
    return chat_manager.self_memory.profile_view()


@app.get("/api/memories")
def memories(q: str | None = None, limit: int = 50) -> list[dict]:
    if q:
        return [
            {"episode": ep.model_dump(), "score": round(score, 4)}
            for ep, score in agent.store.episodic.search(q, top_k=limit)
        ]
    return [{"episode": ep.model_dump(), "score": None} for ep in agent.store.episodic.all()[:limit]]


@app.get("/api/skills")
def skills() -> list[dict]:
    return agent.store.skills.list()


@app.post("/api/decay")
def decay() -> dict:
    agent.evolver.decay()
    return {"status": "decayed", "memory": agent.store.stats()}


# --- chat (三叶虫) ------------------------------------------------------------
@app.post("/api/chat/session", response_model=CreateSessionResponse)
def chat_create_session() -> CreateSessionResponse:
    return chat_manager.create_session()


@app.get("/api/chat/sessions", response_model=list[SessionSummary])
def chat_sessions() -> list[SessionSummary]:
    return chat_manager.list_sessions()


@app.get("/api/chat/session/{session_id}", response_model=SessionDetail)
def chat_session(session_id: str) -> SessionDetail:
    detail = chat_manager.get_detail(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="session not found")
    return detail


@app.delete("/api/chat/session/{session_id}")
def chat_delete_session(session_id: str) -> dict:
    chat_manager.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@app.post("/api/chat/message", response_model=ChatResponse)
def chat_message(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message is empty")
    try:
        return chat_manager.handle_message(req.session_id, req.message)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")


@app.post("/api/chat/voice", response_model=ChatResponse)
async def chat_voice(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
) -> ChatResponse:
    from app.voice.engine import VoiceUnavailable

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="audio is empty")
    try:
        return chat_manager.handle_voice(session_id, audio_bytes)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")
    except VoiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/chat/voice/confirm", response_model=ChatResponse)
def chat_voice_confirm(req: VoiceConfirmRequest) -> ChatResponse:
    if not req.person.strip():
        raise HTTPException(status_code=400, detail="person is required")
    try:
        return chat_manager.confirm_voice(req.session_id, req.person)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")


# --- static web UI -----------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(WEB_DIR / "index.html"))


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
