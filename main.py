"""
MindWeave - Multi-Agent Decision System
Track 3: Agent Society | Qwen Cloud Hackathon 2026

Pipeline:
User -> Sriti (memory/context) -> Buddhi (logic) -> Hriday (emotion/ethics)
     -> Debate Result (synthesis) -> Mat (final judge) -> User
     -> Sriti Feedback (memory write/update to OSS)

Stack: FastAPI (Alibaba ECS) + Qwen Cloud API + Alibaba OSS (JSON memory store)

Design rules followed throughout:
1. NO regex-guessed confidence values. Every agent is forced to return a
   structured JSON object (response_format=json_object). Confidence numbers
   come directly from the model's structured output, never from a fallback
   constant.
2. NO silent failure. Every Qwen/OSS call raises a specific exception on
   failure; the caller surfaces it as a warning in the API response instead
   of quietly substituting fake data.
3. Memory objects follow one fixed schema everywhere (see MemoryRecord).
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import httpx
import json
import os
import uuid
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import oss2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mindweave")

app = FastAPI(title="MindWeave API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== CONFIG ====================
QWEN_API_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3.7-plus")

QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY", os.getenv("QWEN_API_KEY", ""))
OSS_ACCESS_KEY = os.getenv("OSS_ACCESS_KEY_ID", "")
OSS_SECRET_KEY = os.getenv("OSS_ACCESS_KEY_SECRET", "")
OSS_BUCKET = os.getenv("OSS_BUCKET_NAME", "mindweave-memory")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "oss-ap-southeast-1.aliyuncs.com")

DEFAULT_MEMORY_TTL_DAYS = int(os.getenv("MEMORY_TTL_DAYS", "90"))


# ==================== ERRORS ====================
class MemoryServiceError(Exception):
    """Raised on any real OSS read/write failure. Never swallowed silently."""


class QwenServiceError(Exception):
    """Raised on any Qwen API failure, including malformed JSON responses."""


# ==================== MEMORY SCHEMA ====================
class MemoryRecord(BaseModel):
    """Canonical memory object. Every memory stored in OSS uses exactly
    this shape -- no ad-hoc fields added elsewhere in the codebase."""
    memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    content: str
    summary_en: str
    summary_bn: str
    memory_type: str  # e.g. "preference" | "fact" | "decision" | "event"
    importance: float  # 0.0 - 1.0, set by the model, not hardcoded
    tags: List[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    last_accessed: str
    access_count: int = 0
    expires_at: str
    source: str  # "user" | "sriti_inference"


# ==================== OSS MEMORY STORE ====================
def _oss_bucket():
    auth = oss2.Auth(OSS_ACCESS_KEY, OSS_SECRET_KEY)
    return oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)


def _memory_key(user_id: str) -> str:
    return f"users/{user_id}/memories.json"


def load_memories(user_id: str) -> List[Dict[str, Any]]:
    """Returns the user's memory list. Raises MemoryServiceError on real
    failure. Returns [] only when the object genuinely does not exist yet
    (new user), which is distinguished from an OSS error."""
    try:
        bucket = _oss_bucket()
        key = _memory_key(user_id)
        if not bucket.object_exists(key):
            return []
        raw = bucket.get_object(key).read()
        data = json.loads(raw)
        if not isinstance(data, list):
            raise MemoryServiceError("Memory store corrupted: expected a list")
        return data
    except MemoryServiceError:
        raise
    except Exception as e:
        raise MemoryServiceError(f"OSS read failed for user {user_id}: {e}")


def save_memories(user_id: str, memories: List[Dict[str, Any]]) -> None:
    try:
        bucket = _oss_bucket()
        bucket.put_object(_memory_key(user_id), json.dumps(memories, indent=2, ensure_ascii=False))
    except Exception as e:
        raise MemoryServiceError(f"OSS write failed for user {user_id}: {e}")


def prune_expired(memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    now = datetime.utcnow().isoformat()
    return [m for m in memories if m.get("expires_at", "9999") > now]


def rank_relevant_memories(query: str, context_tags: List[str],
                            memories: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    """Ranks memories by a transparent, inspectable score:
    keyword overlap with the query/tags (relevance) combined with the
    model-assigned importance score. This is real, explainable ranking
    logic -- not a hidden constant, not a fake sort."""
    query_terms = set(w.lower() for w in query.split() if len(w) > 2)
    tag_terms = set(t.lower() for t in context_tags)
    search_terms = query_terms | tag_terms

    scored = []
    for m in memories:
        content_terms = set(w.lower() for w in m.get("content", "").split())
        mem_tags = set(t.lower() for t in m.get("tags", []))
        overlap = len(search_terms & (content_terms | mem_tags))
        relevance = overlap / max(len(search_terms), 1)
        importance = float(m.get("importance", 0.0))
        score = (0.6 * relevance) + (0.4 * importance)
        if overlap > 0 or importance >= 0.7:
            scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:limit]]


# ==================== QWEN STRUCTURED CALL ====================
async def call_qwen_json(system_prompt: str, user_prompt: str,
                          temperature: float = 0.4) -> Dict[str, Any]:
    """Every agent call goes through here. Forces JSON-object output so
    confidence/opinion fields are genuine structured data, never text
    that has to be regex-parsed."""
    if not QWEN_API_KEY:
        raise QwenServiceError("DASHSCOPE_API_KEY is not configured")

    for attempt in range(2):  # try once, retry once on transient network failure
        async with httpx.AsyncClient(timeout=70.0) as client:
            try:
                resp = await client.post(
                    QWEN_API_URL,
                    headers={
                        "Authorization": f"Bearer {QWEN_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": QWEN_MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": 800,
                        "response_format": {"type": "json_object"},
                    },
                )
                break  # success, exit retry loop
            except httpx.RequestError as e:
                if attempt == 0:
                    await asyncio.sleep(1.5)  # brief pause before retry
                    continue
                raise QwenServiceError(f"Qwen request failed: {e}")

    if resp.status_code != 200:
        raise QwenServiceError(f"Qwen API returned {resp.status_code}: {resp.text[:300]}")

    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        raise QwenServiceError(f"Unexpected Qwen response shape: {e}")

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise QwenServiceError(f"Qwen did not return valid JSON: {e} | raw: {content[:300]}")


# ==================== AGENT PROMPTS ====================
def lang_instruction(language: str) -> str:
    if language == "bn":
        return "Respond in Bengali (বাংলা) for every user-facing text field. JSON keys stay in English."
    return "Respond in English for every user-facing text field. JSON keys stay in English."


SRITI_SYSTEM_TEMPLATE = """You are Sriti, the Memory & Context Intelligence agent in MindWeave.
Given the user's message and their relevant stored memories, build context for the
other agents. Only use the memories provided -- never invent past events.

{lang}

Respond with ONLY a JSON object of exactly this shape:
{{
  "user_context": "string, 1-2 sentences summarizing what the user is asking/dealing with",
  "relevant_memory_summary": "string, summary of the memories actually provided, or 'No relevant memory found.'",
  "initial_analysis": "string, 2-3 sentences",
  "sriti_opinion": "string, Sriti's own take on the best direction",
  "confidence": integer 0-100
}}"""

BUDDHI_SYSTEM_TEMPLATE = """You are Buddhi, the Reasoning & Logic Intelligence agent in MindWeave.
You receive the user's input, Sriti's context/opinion, and relevant memory. Analyze
logically, generate a proposed solution, and challenge Sriti's opinion if warranted.

{lang}

Respond with ONLY a JSON object of exactly this shape:
{{
  "reasoning": "string, step-by-step logical analysis, 2-4 sentences",
  "arguments": ["string", "string"],
  "proposed_solution": "string",
  "buddhi_opinion": "string, agree or disagree with Sriti and why",
  "confidence": integer 0-100
}}"""

HRIDAY_SYSTEM_TEMPLATE = """You are Hriday, the Emotion, Ethics & Human Perspective agent in MindWeave.
You receive the user's input, Sriti's opinion, and Buddhi's reasoning. Evaluate the
emotional and ethical dimensions, and challenge Buddhi's reasoning if it ignores
human impact.

{lang}

Respond with ONLY a JSON object of exactly this shape:
{{
  "emotional_analysis": "string",
  "ethical_analysis": "string",
  "human_perspective": "string",
  "hriday_opinion": "string, agree or disagree with Buddhi and why",
  "confidence": integer 0-100
}}"""

DEBATE_SYSTEM_TEMPLATE = """You are the Debate Synthesizer in MindWeave. You receive Buddhi's
reasoning and Hriday's perspective, which may conflict. Summarize the debate honestly
-- do not paper over real disagreements.

{lang}

Respond with ONLY a JSON object of exactly this shape:
{{
  "debate_summary": "string, 2-3 sentences",
  "agreements": ["string"],
  "disagreements": ["string"],
  "final_debate_outcome": "string, which position the debate favors and why"
}}"""

MAT_SYSTEM_TEMPLATE = """You are Mat, the Final Judge & Decision Maker in MindWeave. You receive
everything: user input, memory context, Sriti/Buddhi/Hriday opinions, and the debate
result. Weigh logic and emotion/ethics together, resolve conflicts explicitly, and
produce one final, actionable answer.

{lang}

Respond with ONLY a JSON object of exactly this shape:
{{
  "final_answer": "string, the actual answer/recommendation for the user",
  "reasoning_summary": "string, 2-3 sentences explaining how you reached this",
  "confidence_score": integer 0-100
}}"""

SRITI_FEEDBACK_SYSTEM_TEMPLATE = """You are Sriti in Memory Feedback mode. The conversation is
complete. Decide whether this exchange is worth remembering long-term, and if so,
produce the memory record fields. Do not invent memory_type/tags that don't fit the
conversation.

Produce summary_en (English) and summary_bn (Bengali) -- both fields, regardless of
which language the conversation happened in, so the memory is retrievable for users
of either language.

Respond with ONLY a JSON object of exactly this shape:
{
  "should_store": true or false,
  "memory_type": "preference" or "fact" or "decision" or "event",
  "summary_en": "string, 1 sentence summary in English",
  "summary_bn": "string, same summary in Bengali",
  "importance": number between 0.0 and 1.0,
  "tags": ["string"],
  "is_update_of_existing": true or false,
  "existing_memory_id": "string or null, only if is_update_of_existing is true and it matches a provided memory_id"
}"""


# ==================== API MODELS ====================
class ChatRequest(BaseModel):
    message: str
    user_id: str
    session_id: Optional[str] = None
    language: str = "en"  # "en" or "bn" -- set by the frontend's Language selector


class AgentOutput(BaseModel):
    agent: str
    role: str
    content: Dict[str, Any]
    confidence: Optional[int] = None
    color: str


class ChatResponse(BaseModel):
    sriti: AgentOutput
    buddhi: AgentOutput
    hriday: AgentOutput
    debate_result: Dict[str, Any]
    mat: AgentOutput
    memories_used: List[Dict[str, Any]]
    memory_feedback: Dict[str, Any]
    warnings: List[str] = []


# ==================== MAIN PIPELINE ====================
@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    user_message = request.message
    user_id = request.user_id
    language = request.language if request.language in ("en", "bn") else "en"
    lang = lang_instruction(language)
    SRITI_SYSTEM = SRITI_SYSTEM_TEMPLATE.format(lang=lang)
    BUDDHI_SYSTEM = BUDDHI_SYSTEM_TEMPLATE.format(lang=lang)
    HRIDAY_SYSTEM = HRIDAY_SYSTEM_TEMPLATE.format(lang=lang)
    DEBATE_SYSTEM = DEBATE_SYSTEM_TEMPLATE.format(lang=lang)
    MAT_SYSTEM = MAT_SYSTEM_TEMPLATE.format(lang=lang)
    SRITI_FEEDBACK_SYSTEM = SRITI_FEEDBACK_SYSTEM_TEMPLATE
    now = datetime.utcnow()
    warnings: List[str] = []

    # ---- Load memory (real OSS call, real failure surfaced) ----
    try:
        all_memories = load_memories(user_id)
        all_memories = prune_expired(all_memories)
    except MemoryServiceError as e:
        warnings.append(f"Memory service unavailable: {e}")
        all_memories = []

    relevant_memories = rank_relevant_memories(user_message, [], all_memories)

    # touch access metadata on memories that were actually retrieved
    now_iso = now.isoformat()
    retrieved_ids = {m["memory_id"] for m in relevant_memories if "memory_id" in m}
    for m in all_memories:
        if m.get("memory_id") in retrieved_ids:
            m["last_accessed"] = now_iso
            m["access_count"] = int(m.get("access_count", 0)) + 1

    summary_field = "summary_bn" if language == "bn" else "summary_en"
    memory_text = "\n".join(
        f"- [{m.get('memory_type', '?')}, importance={m.get('importance', 0)}] "
        f"{m.get(summary_field, m.get('summary_en', m.get('content', '')))}"
        for m in relevant_memories
    ) or ("কোনো প্রাসঙ্গিক মেমোরি পাওয়া যায়নি।" if language == "bn" else "No relevant memories found.")

    # ---- Sriti ----
    sriti_prompt = f'User message: "{user_message}"\n\nRelevant memories:\n{memory_text}'
    try:
        sriti = await call_qwen_json(SRITI_SYSTEM, sriti_prompt)
    except QwenServiceError as e:
        warnings.append(f"Sriti agent failed: {e}")
        sriti = {
            "user_context": "unavailable", "relevant_memory_summary": memory_text,
            "initial_analysis": "unavailable", "sriti_opinion": "unavailable", "confidence": None
        }

    # ---- Buddhi (receives Sriti) ----
    buddhi_prompt = (
        f'User message: "{user_message}"\n'
        f'Sriti context: {sriti.get("user_context")}\n'
        f'Sriti opinion: {sriti.get("sriti_opinion")}\n'
        f'Memory summary: {sriti.get("relevant_memory_summary")}'
    )
    try:
        buddhi = await call_qwen_json(BUDDHI_SYSTEM, buddhi_prompt)
    except QwenServiceError as e:
        warnings.append(f"Buddhi agent failed: {e}")
        buddhi = {"reasoning": "unavailable", "arguments": [], "proposed_solution": "unavailable",
                  "buddhi_opinion": "unavailable", "confidence": None}

    # ---- Hriday (receives Sriti + Buddhi) ----
    hriday_prompt = (
        f'User message: "{user_message}"\n'
        f'Sriti memory context: {sriti.get("user_context")}\n'
        f'Sriti opinion: {sriti.get("sriti_opinion")}\n'
        f'Buddhi reasoning: {buddhi.get("reasoning")}\n'
        f'Buddhi proposed solution: {buddhi.get("proposed_solution")}'
    )
    try:
        hriday = await call_qwen_json(HRIDAY_SYSTEM, hriday_prompt)
    except QwenServiceError as e:
        warnings.append(f"Hriday agent failed: {e}")
        hriday = {"emotional_analysis": "unavailable", "ethical_analysis": "unavailable",
                  "human_perspective": "unavailable", "hriday_opinion": "unavailable", "confidence": None}

    # ---- Debate synthesis ----
    debate_prompt = (
        f'Buddhi reasoning: {buddhi.get("reasoning")}\n'
        f'Buddhi opinion: {buddhi.get("buddhi_opinion")}\n'
        f'Hriday perspective: {hriday.get("human_perspective")}\n'
        f'Hriday opinion: {hriday.get("hriday_opinion")}'
    )
    try:
        debate_result = await call_qwen_json(DEBATE_SYSTEM, debate_prompt)
    except QwenServiceError as e:
        warnings.append(f"Debate synthesis failed: {e}")
        debate_result = {"debate_summary": "unavailable", "agreements": [],
                          "disagreements": [], "final_debate_outcome": "unavailable"}

    # ---- Mat (final judge) ----
    mat_prompt = (
        f'User message: "{user_message}"\n'
        f'Historical memory records: {sriti.get("relevant_memory_summary")}\n'
        f'Sriti opinion: {sriti.get("sriti_opinion")}\n'
        f'Buddhi reasoning: {buddhi.get("reasoning")}\n'
        f'Buddhi opinion: {buddhi.get("buddhi_opinion")}\n'
        f'Hriday perspective: {hriday.get("human_perspective")}\n'
        f'Hriday opinion: {hriday.get("hriday_opinion")}\n'
        f'Debate outcome: {debate_result.get("final_debate_outcome")}'
    )
    try:
        mat = await call_qwen_json(MAT_SYSTEM, mat_prompt)
    except QwenServiceError as e:
        warnings.append(f"Mat agent failed: {e}")
        mat = {"final_answer": "unavailable -- see individual agent outputs",
               "reasoning_summary": "unavailable", "confidence_score": None}

    # ---- Sriti feedback: decide what to remember ----
    feedback_prompt = (
        f'User message: "{user_message}"\n'
        f'Final answer: {mat.get("final_answer")}\n'
        f'-- Complete pipeline log --\n'
        f'Sriti context: {sriti.get("user_context")}\n'
        f'Sriti opinion: {sriti.get("sriti_opinion")}\n'
        f'Buddhi reasoning: {buddhi.get("reasoning")}\n'
        f'Buddhi opinion: {buddhi.get("buddhi_opinion")}\n'
        f'Hriday perspective: {hriday.get("human_perspective")}\n'
        f'Hriday opinion: {hriday.get("hriday_opinion")}\n'
        f'Debate summary: {debate_result.get("debate_summary")}\n'
        f'Debate outcome: {debate_result.get("final_debate_outcome")}\n'
        f'Existing memory IDs available for update: {[m.get("memory_id") for m in relevant_memories]}'
    )
    memory_feedback: Dict[str, Any] = {"should_store": False}
    try:
        memory_feedback = await call_qwen_json(SRITI_FEEDBACK_SYSTEM, feedback_prompt)
    except QwenServiceError as e:
        warnings.append(f"Sriti memory feedback failed: {e}")

    if memory_feedback.get("should_store"):
        if memory_feedback.get("is_update_of_existing") and memory_feedback.get("existing_memory_id"):
            target_id = memory_feedback["existing_memory_id"]
            for m in all_memories:
                if m.get("memory_id") == target_id:
                    m["summary_en"] = memory_feedback.get("summary_en", m.get("summary_en"))
                    m["summary_bn"] = memory_feedback.get("summary_bn", m.get("summary_bn"))
                    m["importance"] = float(memory_feedback.get("importance", m.get("importance", 0.5)))
                    m["tags"] = memory_feedback.get("tags", m.get("tags", []))
                    m["updated_at"] = now_iso
                    m["last_accessed"] = now_iso
                    m["access_count"] = int(m.get("access_count", 0)) + 1
                    break
        else:
            new_record = MemoryRecord(
                user_id=user_id,
                content=user_message,
                summary_en=memory_feedback.get("summary_en", user_message[:200]),
                summary_bn=memory_feedback.get("summary_bn", user_message[:200]),
                memory_type=memory_feedback.get("memory_type", "fact"),
                importance=float(memory_feedback.get("importance", 0.5)),
                tags=memory_feedback.get("tags", []),
                created_at=now_iso,
                updated_at=now_iso,
                last_accessed=now_iso,
                access_count=1,
                expires_at=(now + timedelta(days=DEFAULT_MEMORY_TTL_DAYS)).isoformat(),
                source="sriti_inference",
            )
            all_memories.append(new_record.model_dump())

        try:
            save_memories(user_id, all_memories)
        except MemoryServiceError as e:
            warnings.append(f"Memory write failed (this turn was not persisted): {e}")
    else:
        try:
            save_memories(user_id, all_memories)
        except MemoryServiceError as e:
            warnings.append(f"Memory metadata update failed: {e}")

    return ChatResponse(
        sriti=AgentOutput(agent="Sriti", role="Memory & Context", content=sriti,
                           confidence=sriti.get("confidence"), color="#2E7D8C"),
        buddhi=AgentOutput(agent="Buddhi", role="Reasoning & Logic", content=buddhi,
                            confidence=buddhi.get("confidence"), color="#2F6FB0"),
        hriday=AgentOutput(agent="Hriday", role="Emotion & Ethics", content=hriday,
                            confidence=hriday.get("confidence"), color="#C2416B"),
        debate_result=debate_result,
        mat=AgentOutput(agent="Mat", role="Final Judge", content=mat,
                         confidence=mat.get("confidence_score"), color="#2E8B57"),
        memories_used=relevant_memories,
        memory_feedback=memory_feedback,
        warnings=warnings,
    )


# ==================== MEMORY MANAGEMENT ENDPOINTS ====================
@app.get("/api/memory/{user_id}")
async def get_memory(user_id: str):
    try:
        memories = load_memories(user_id)
    except MemoryServiceError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"user_id": user_id, "count": len(memories), "memories": memories}


@app.delete("/api/memory/{user_id}")
async def clear_memory(user_id: str):
    try:
        save_memories(user_id, [])
    except MemoryServiceError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"status": "cleared", "user_id": user_id}


@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "qwen_configured": bool(QWEN_API_KEY),
        "oss_configured": bool(OSS_ACCESS_KEY and OSS_SECRET_KEY),
        "model": QWEN_MODEL,
        "memory_ttl_days": DEFAULT_MEMORY_TTL_DAYS,
    }


@app.on_event("startup")
async def startup_validation():
    if not QWEN_API_KEY:
        logger.warning("DASHSCOPE_API_KEY / QWEN_API_KEY is NOT set -- Qwen calls will fail.")
    if not (OSS_ACCESS_KEY and OSS_SECRET_KEY):
        logger.warning("OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET is NOT set -- memory will not persist.")
    logger.info(f"MindWeave started. model={QWEN_MODEL} bucket={OSS_BUCKET} endpoint={OSS_ENDPOINT}")


# ==================== STATIC FRONTEND (served from the same ECS instance) ====================
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/{filename}")
    async def serve_root_file(filename: str):
        # allows index.html to reference styles.css / app.js / manifest.json at root paths
        path = os.path.join(STATIC_DIR, filename)
        if os.path.isfile(path):
            return FileResponse(path)
        raise HTTPException(status_code=404, detail="Not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
