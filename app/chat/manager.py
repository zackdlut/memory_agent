"""Chat orchestration for the assistant 三叶虫.

Flow:
  - create_session()  -> assistant greets and asks who the user is
  - handle_message()
      * awaiting_identity : extract the user's name, bind the session, greet by
                            name (recalling memory if we already know them)
      * active            : retrieve memory about the person, generate a
                            memory-aware reply, ingest the whole exchange, and
                            compute side-panel "understanding" + behavior
                            prediction
"""

from __future__ import annotations

from app.agent import MemoryAgent, agent
from app.chat.self_memory import SelfMemory
from app.chat.session_store import SessionStore
from app.config import settings
from app.llm import llm
from app.llm.prompts import (
    CHAT_REPLY_SYSTEM,
    CHAT_REPLY_TEMPLATE,
    IDENTITY_EXTRACT_SYSTEM,
    IDENTITY_EXTRACT_TEMPLATE,
)
from app.schemas import (
    ChatResponse,
    CreateSessionResponse,
    Prediction,
    SessionDetail,
    TraitWeight,
    Understanding,
    VoiceSuggestion,
)

HISTORY_TURNS = 6  # how many recent messages to feed back into the reply prompt


class ChatManager:
    def __init__(self, memory_agent: MemoryAgent | None = None) -> None:
        self.agent = memory_agent or agent
        self.sessions = SessionStore()
        self.assistant = settings.assistant_name
        self.self_memory = SelfMemory(self.agent.store)
        # voiceprints + per-session pending embedding awaiting identity confirm
        self._voiceprints = None  # lazily created VoiceprintStore
        self._pending_voiceprints: dict[str, "np.ndarray"] = {}
        # seed the assistant's self node + backfill acquaintances it already has
        known = [s.person for s in self.sessions.list() if s.person]
        try:
            self.self_memory.ensure(known)
        except Exception:
            pass

    # ---------------------------------------------------------------- create
    def create_session(self) -> CreateSessionResponse:
        session = self.sessions.create()
        greeting = f"你好，我是{self.assistant}，很高兴认识你！请问你是谁呀？"
        self.sessions.add_message(session.id, "assistant", greeting)
        return CreateSessionResponse(session_id=session.id, greeting=greeting)

    # ------------------------------------------------------------ voiceprints
    @property
    def voiceprints(self):
        """Lazily-created voiceprint store (only when voice is first used)."""
        if self._voiceprints is None:
            from app.voice.store import VoiceprintStore

            self._voiceprints = VoiceprintStore()
        return self._voiceprints

    # ----------------------------------------------------------------- read
    def list_sessions(self):
        return self.sessions.list()

    def get_detail(self, session_id: str) -> SessionDetail | None:
        session = self.sessions.get(session_id)
        if not session:
            return None
        return SessionDetail(session=session, messages=self.sessions.messages(session_id))

    def delete_session(self, session_id: str) -> None:
        self.sessions.delete(session_id)

    # --------------------------------------------------------------- message
    def handle_message(self, session_id: str, text: str) -> ChatResponse:
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError("session not found")

        self.sessions.add_message(session_id, "user", text)

        if session.state == "awaiting_identity":
            return self._handle_identity(session_id, text)
        return self._handle_active(session.person or "对方", session_id, text)

    # ------------------------------------------------------------- identity
    def _extract_name(self, message: str) -> str:
        try:
            data = llm.chat_json(
                IDENTITY_EXTRACT_TEMPLATE.format(message=message),
                system=IDENTITY_EXTRACT_SYSTEM,
            )
            name = (data.get("name") if isinstance(data, dict) else "") or ""
            name = name.strip()
        except Exception:
            name = ""
        if not name:
            # fallback: use the trimmed message itself (short) or a default
            name = message.strip().split("\n")[0][:20] or "朋友"
        return name

    def _handle_identity(self, session_id: str, text: str) -> ChatResponse:
        name = self._extract_name(text)
        self.sessions.bind_person(session_id, name)
        self.self_memory.record_acquaintance(name)

        known = self.agent.store.persona.get(name)
        if known and known.mention_count > 0:
            traits = sorted(known.traits, key=known.traits.get, reverse=True)[:2]
            hint = f"我记得你～{('印象里你' + '、'.join(traits)) if traits else ''}。"
            reply = f"{name}，又见面啦！{hint} 今天想聊点什么？"
        else:
            reply = f"{name}，你好！很高兴认识你，想聊些什么都可以告诉我。"

        self.sessions.add_message(session_id, "assistant", reply)
        understanding = self._build_understanding(name)
        return ChatResponse(
            reply=reply,
            identified=True,
            person=name,
            understanding=understanding,
            used_memories=[],
        )

    # --------------------------------------------------------------- active
    def _handle_active(self, person: str, session_id: str, text: str) -> ChatResponse:
        self.self_memory.record_acquaintance(person)

        # 1) retrieve memory relevant to this person + message
        memories = self.agent.retriever.retrieve(f"{person} {text}", rerank=True)
        memory_block = "\n".join(f"- [{m.source}] {m.text}" for m in memories) or "（暂无相关记忆）"

        # 2) recent conversation history
        history_msgs = self.sessions.messages(session_id, limit=HISTORY_TURNS + 1)[:-1]
        history = "\n".join(
            f"{(self.assistant if m.role == 'assistant' else person)}: {m.content}"
            for m in history_msgs
        ) or "（这是对话开始）"

        # 3) memory-aware reply (with 三叶虫's own self + social memory)
        self_context = self.self_memory.self_context(person)
        prompt = CHAT_REPLY_TEMPLATE.format(
            person=person,
            self_context=self_context,
            memory=memory_block,
            history=history,
            message=text,
        )
        reply = llm.chat(prompt, system=CHAT_REPLY_SYSTEM, temperature=0.6).strip()
        self.sessions.add_message(session_id, "assistant", reply)

        # 4) ingest the whole exchange (user + assistant)
        try:
            self.agent.ingest(f"{person}: {text}\n{self.assistant}: {reply}", source="chat")
        except Exception:
            pass

        # 4b) 三叶虫 reflects on itself: grow its own traits / self-memory
        self.self_memory.reflect(person, text, reply)

        # 5) side-panel: understanding + behavior prediction
        understanding = self._build_understanding(person)
        prediction: Prediction | None = None
        try:
            prediction = self.agent.predict(person, text)
        except Exception:
            prediction = None

        return ChatResponse(
            reply=reply,
            identified=True,
            person=person,
            understanding=understanding,
            prediction=prediction,
            used_memories=memories,
        )

    # ---------------------------------------------------------------- voice
    def handle_voice(self, session_id: str, audio_bytes: bytes) -> ChatResponse:
        """Transcribe + voiceprint a spoken turn.

        - awaiting_identity: match the voiceprint against known people, also
          extract a candidate name from the transcript, stash the embedding and
          return suggestions WITHOUT binding (the user confirms via confirm_voice).
        - active: strengthen the bound person's voiceprint and run the normal
          memory-aware reply on the transcript.
        """
        import numpy as np  # local import keeps text-only mode numpy-light

        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError("session not found")

        from app.voice.engine import engine

        transcript, emb = engine.process(audio_bytes)
        emb = np.asarray(emb, dtype=np.float32)

        if session.state == "awaiting_identity":
            return self._voice_identity(session_id, transcript, emb)
        return self._voice_active(session.person or "对方", session_id, transcript, emb)

    def _voice_identity(self, session_id: str, transcript: str, emb) -> ChatResponse:
        self._pending_voiceprints[session_id] = emb

        suggestions: list[VoiceSuggestion] = []
        matches = self.voiceprints.match(emb)
        best_person = ""
        best_score = 0.0
        if matches:
            best_person, best_score = matches[0]

        # high-confidence voiceprint -> bind directly, skip the confirm step
        if best_person and best_score >= settings.voiceprint_strong_threshold:
            if transcript.strip():
                self.sessions.add_message(session_id, "user", transcript.strip())
            response = self.confirm_voice(session_id, best_person, auto=True)
            response.transcript = transcript
            return response

        for person, score in matches[:3]:
            if score >= settings.voiceprint_threshold:
                suggestions.append(
                    VoiceSuggestion(person=person, score=round(score, 4), source="voiceprint")
                )

        # also offer a name parsed from what they just said
        name_from_text = self._extract_name(transcript) if transcript.strip() else ""
        if name_from_text and not any(s.person == name_from_text for s in suggestions):
            suggestions.append(
                VoiceSuggestion(person=name_from_text, score=0.0, source="transcript")
            )

        if suggestions and suggestions[0].source == "voiceprint":
            top = suggestions[0].person
            reply = f"我好像听出你的声音了～你是 {top} 吗？是的话点确认，不是请告诉我你的名字。"
        elif name_from_text:
            reply = f"你好！我听你说你是 {name_from_text}，对吗？确认一下我就记住你的声音。"
        else:
            reply = "你好！我还没听出你是谁，能告诉我你的名字吗？"

        self.sessions.add_message(session_id, "assistant", reply)
        return ChatResponse(
            reply=reply,
            identified=False,
            person=None,
            transcript=transcript,
            voice_suggestions=suggestions,
        )

    def _voice_active(self, person: str, session_id: str, transcript: str, emb) -> ChatResponse:
        # strengthen the speaker's voiceprint with this fresh utterance
        try:
            self.voiceprints.enroll(person, emb)
        except Exception:
            pass

        message = transcript.strip() or "（这段语音没有听清）"
        self.sessions.add_message(session_id, "user", message)
        response = self._handle_active(person, session_id, message)
        response.transcript = transcript
        return response

    def confirm_voice(self, session_id: str, person: str, auto: bool = False) -> ChatResponse:
        """Bind the (confirmed / corrected / auto-recognised) identity.

        ``auto`` is set when the voiceprint matched with high confidence and we
        bound the person without asking, so the greeting can reflect that.
        """
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError("session not found")

        name = person.strip() or "朋友"
        self.sessions.bind_person(session_id, name)
        self.self_memory.record_acquaintance(name)

        emb = self._pending_voiceprints.pop(session_id, None)
        if emb is not None:
            try:
                self.voiceprints.enroll(name, emb)
            except Exception:
                pass

        known = self.agent.store.persona.get(name)
        if auto:
            if known and known.mention_count > 0:
                traits = sorted(known.traits, key=known.traits.get, reverse=True)[:2]
                hint = f"印象里你{'、'.join(traits)}。" if traits else ""
                reply = f"{name}！一听声音我就认出你啦～{hint}今天想聊点什么？"
            else:
                reply = f"听声音应该是{name}吧～我先这么叫你啦，要是认错了告诉我。今天想聊点什么？"
        elif known and known.mention_count > 0:
            traits = sorted(known.traits, key=known.traits.get, reverse=True)[:2]
            hint = f"我记得你～{('印象里你' + '、'.join(traits)) if traits else ''}。"
            reply = f"{name}，又见面啦！{hint} 我已经记住你的声音了，今天想聊点什么？"
        else:
            reply = f"{name}，你好！我记住你的声音啦，下次一开口我就能认出你。想聊些什么都可以告诉我。"

        self.sessions.add_message(session_id, "assistant", reply)
        understanding = self._build_understanding(name)
        return ChatResponse(
            reply=reply,
            identified=True,
            person=name,
            understanding=understanding,
            used_memories=[],
        )

    # --------------------------------------------------------- understanding
    def _build_understanding(self, person: str) -> Understanding:
        persona = self.agent.store.persona.get(person)
        graph = self.agent.store.semantic.neighbors(person)
        assistant_rel = self.self_memory.relationship_label(person)
        mutual = [m["person"] for m in self.self_memory.mutual_acquaintances(person)]
        if persona is None:
            return Understanding(
                name=person,
                summary="还不太了解这个人，继续聊聊吧。",
                assistant_relationship=assistant_rel,
                mutual_acquaintances=mutual,
            )
        traits = [
            TraitWeight(name=k, weight=v)
            for k, v in sorted(persona.traits.items(), key=lambda x: x[1], reverse=True)
        ]
        prefs = [
            TraitWeight(name=k, weight=v)
            for k, v in sorted(persona.preferences.items(), key=lambda x: x[1], reverse=True)
        ]
        return Understanding(
            name=persona.name,
            summary=persona.summary,
            traits=traits,
            preferences=prefs,
            patterns=persona.patterns,
            relations=graph.get("relations", []),
            mention_count=persona.mention_count,
            assistant_relationship=assistant_rel,
            mutual_acquaintances=mutual,
        )


chat_manager = ChatManager()
