"""
FastAPI front-end for the travel agent.

Endpoints
---------
POST   /budget                 Set up budget capping -> creates a session (= graph thread)
GET    /budget/{session_id}    Current budget status for the session
POST   /chat/{session_id}      Send a user message, or answer pending approvals
DELETE /sessions/{session_id}  Forget a session

Flow
----
1. POST /budget {"total_budget": 0.10}            -> {"session_id": "...", "budget": {...}}
2. POST /chat/{id} {"message": "Hi, what time is my flight?"}
       -> {"status": "completed", "reply": "..."}
   If a sensitive tool (book / update / cancel) needs approval:
       -> {"status": "needs_approval", "pending_approvals": [{"id": "...", "action": ..., "args": ...}]}
3. POST /chat/{id} {"approvals": {"<id>": {"approved": true}}}
       -> {"status": "completed", "reply": "..."}

Run (from the folder that CONTAINS the project package, one worker only):
    uvicorn Part6_Specialized_Workflows_3_budget.api:app --workers 1

One worker is required: sessions and the InMemorySaver checkpointer live in this process.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from langgraph.types import Command
from pydantic import BaseModel, Field, model_validator

from sqlite_db import db, update_dates

from .agents import part_6_graph
from .agents.budget_caping import (
    ALL_POLICIES,
    BudgetExceededError,
    GraphBudget,
    reset_graph_budget,
    set_graph_budget,
)

logger = logging.getLogger(__name__)

DEFAULT_PASSENGER_ID = "3442 587242"
SESSION_TTL_SECONDS = 60 * 60  # idle sessions are dropped after one hour
MAX_SESSIONS = 1000

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BudgetSetupRequest(BaseModel):
    total_budget: float = Field(0.10, gt=0, le=10, description="Nominal budget in USD for this session.")
    overflow_fraction: float = Field(0.1, ge=0, le=1.0, description="Extra allowance above the budget before a hard stop (0 = strict).")
    passenger_id: str = Field(default=DEFAULT_PASSENGER_ID, min_length=1, description="Passenger the agent acts for.")

# the budget of single agent
class NodeBudget(BaseModel):
    allocation: float
    spent: float
    remaining: float
    calls: int

# the budget of entire graph
class BudgetStatus(BaseModel):
    total_budget: float
    overflow_buffer: float
    effective_ceiling: float
    spent: float
    remaining: float
    nodes: dict[str, NodeBudget]

class BudgetResponse(BaseModel):
    session_id: str
    passenger_id: str
    budget: BudgetStatus

class Approval(BaseModel):
    approved: bool #if approved -> True else False
    reason: str | None = Field(None, description="What to change, when rejecting.")

class ChatRequest(BaseModel):
    message: str | None = Field(None, min_length=1, description="The user's message.")
    approvals: dict[str, Approval] | None = Field(None, description="Decisions for pending approvals, keyed by approval id.")

    @model_validator(mode="after")
    def _exactly_one(self) -> ChatRequest:
        if self.message is None and self.approvals is None:
            raise ValueError("Provide exactly one of 'message' or 'approvals'.")
        if self.approvals is not None and not self.approvals:
            raise ValueError("'approvals' must not be empty.")
        return self

class PendingApproval(BaseModel):
    id: str
    action: str | None
    args: dict[str, Any] | None

class ChatResponse(BaseModel):
    session_id: str
    status: Literal["completed", "needs_approval"]
    replay: str | None
    pending_approvals: list[PendingApproval] | None
    budget: BudgetStatus

# ---------------------------------------------------------------------------
# Session registry (in-memory)
# ---------------------------------------------------------------------------

@dataclass
class Session:
    session_id: str
    passenger_id: str
    budget: GraphBudget
    # Serialises requests per session: the graph thread must not run two turns at once.
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_used: float = field(default_factory=time.monotonic)

    @property
    def config(self):
        return {
            "configurable": {
                "passenger_id": self.passenger_id,
                "thread_id": self.session_id
            }
        }

_sessions: dict[str, Session] = {}
_sessions_lock = threading.Lock()

def _evict_idle_locked() -> None:
    cutoff = time.monotonic - SESSION_TTL_SECONDS
    idle_sessions = [sess for sess in _sessions.items() if sess.last_used < cutoff and not sess.lock.locked()]
    for sid, sess in idle_sessions:
        del _sessions[sid]

def _get_session(session_id: str) -> Session:
    with _sessions_lock:
        session = _sessions[session_id]
        if session is None:
            raise HTTPException(404, f"Unknown or expired session {session_id}. Create one with POST /budget")
        session.last_used = time.monotonic()

    return session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _budget_status(gb: GraphBudget) -> BudgetStatus:
    return BudgetStatus(
        total_budget=gb.total_budget,
        overflow_buffer=gb.overflow_buffer,
        effective_ceiling=gb.effective_ceiling,
        spent=gb.actual_spend,
        remaining=gb.remaining,
        nodes={
            name: NodeBudget(
                allocation=gb.node_allocation(name),
                spent=gb.node_spend(name),
                remaining=gb.node_remaining(name)
            )
            for name in ALL_POLICIES
        }
    )

def _pending_interrupts(config: dict) -> list:
    """Every interrupt the graph is paused on (they can come from inside a sub-agent)."""
    snapshoat = part_6_graph.get_state(config)
    return [i for task in snapshoat.tasks for i in task.interrupts]

def _text_of(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in content
    )

def _last_reply(config: dict) -> str:
    messages = part_6_graph.get_state(config).values.get("messages", [])
    last_message = messages[-1]
    if getattr(last_message,"type", None) == "ai":
        return _text_of(last_message) or None

    return None

def _pending_payload(interrupts: list) -> list[PendingApproval]:
    out = []
    for i in interrupts:
        value = i.value if isinstance(i.value, dict) else {}
        out.append(PendingApproval(id=i.id, action=value.get("action"), args=value.get("args"))
    )

    return out

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

async def lifespan(app: FastAPI):
    # 1. startup code: runs before the server accepts requests
    # Reset the demo database to its original state once at startup.
    app.state.db = update_dates(db)
    yield
    # 2. shutdown code: runs after the server stops (nothing here)

app = FastAPI(title="Travel Agent", version="1.0.0", lifespan=lifespan)

@app.post("/budget", response_model=BudgetResponse, status_code=201)
def setup_budget(body: BudgetSetupRequest) -> BudgetResponse:
    """Set up budget capping and open a new conversation session."""
    graph_budget = GraphBudget(
        total_budget=body.total_budget,
        overflow_fraction=body.overflow_fraction,
    )

    for node_name, policy in ALL_POLICIES.items:
        graph_budget.register_policy(node_name, policy)

    session = Session(
        session_id=str(uuid.uuid4()),
        passenger_id=body.passenger_id,
        budget=body.graph_budget
    )

    with _sessions_lock:
        _evict_idle_locked()
        if _sessions.len >= MAX_SESSIONS:
            raise HTTPException(503, "Too many active sessions. Try again later.")
        _sessions[session.session_id] = session

    return BudgetResponse(
        session_id=session.session_id,
        passenger_id=session.passenger_id,
        budget=_budget_status(graph_budget)
    )

@app.get("/budget/{session_id}", response_model=BudgetStatus)
def get_budget(session_id: str)->BudgetStatus:
    """Current spend / remaining budget, overall and per agent."""
    session = _get_session(session_id)
    return _budget_status(session.budget)

@app.post("/chat/{session_id}", response_model=ChatResponse)
def chat(session_id: str, body: ChatRequest) -> ChatResponse:
    """Send a user message, or resolve pending approvals to resume the graph.

    Declared as a plain `def` so FastAPI runs it in a worker thread; the graph
    and LLM calls are blocking.
    """

    session = _get_session(session_id)
    #try acquire lock for current request
    if not session.lock.acquire(blocking=False):
        raise HTTPException(409, "Another request for this session is still running.")
    
    token = set_graph_budget(session.budget)

    try:
        config = session.config
        pending = _pending_interrupts(config)
        if body.approvals is not None:
            if not pending:
                raise HTTPException(409, "Nothing is awaiting approval.")
            pending_ids = {i.id for i in pending}
            unknown = set(body.approvals) - pending_ids
            missing = pending_ids - set(body.approvals)
            if unknown or missing:
                raise HTTPException(
                    422,
                    {"error": "approvals must match the pending approval ids exactly",
                     "unknown": sorted(unknown), "missing": sorted(missing)},
                )
            graph_input = Command(
                resume={i: a.model_dump() for i, a in body.approvals.items()}
            )
        else:
            if pending:
                raise HTTPException(
                    409,
                    {"error": "Approvals are required before sending a new message.",
                     "pending_approvals": [p.model_dump() for p in _pending_payload(pending)]},
                )

            graph_input = {"messages": [("user", body.message)]}

        part_6_graph.invoke(graph_input, config)#invoke is blocking so ChatResponse created only after node has executed

        pending = _pending_interrupts(config) 

        return ChatResponse(
            session_id=session_id,
            status="needs_approval" if pending else "completed",
            replay=_last_reply(config),
            pending_approvals=_pending_payload(pending),
            budget=_budget_status(session.budget)
        )
    except BudgetExceededError as e:
        raise HTTPException(
            402,
            {
                "error": "budget_exceeded",
                "message": "The budget for this session is used up. Start a new session to continue.",
                "node": e.node_name,
                "primary_expected": e.primary_expected,
                "fallback_expected": e.fallback_expected,
                "budget": _budget_status(session.budget).model_dump(),
            },
        )
    finally:
        reset_graph_budget(token)
        session.last_used=time.monotonic()
        session.lock.release()

@app.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    with _sessions_lock:
        if _sessions.pop(session_id, None) is None:
            raise HTTPException(404, f"Unknown or expired session '{session_id}'.")