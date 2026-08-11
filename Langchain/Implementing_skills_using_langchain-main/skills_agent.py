"""
LangGraph Skills Agent — exact replica of Claude's skill processing pipeline.

════════════════════════════════════════════════════════════════
HOW CLAUDE PROCESSES SKILLS (the mental model we're replicating)
════════════════════════════════════════════════════════════════

Layer 1 — Skill Index (always in context):
  • On startup, Claude receives all skill name+description pairs
  • These are ~100-word summaries, always present in the system prompt
  • Example: <skill><name>youtube-transcript</name><description>...</description></skill>

Layer 2 — Skill Triggering (LLM decision):
  • For every user message, Claude decides: "Does this need a skill?"
  • It matches the query against available descriptions
  • Complex, multi-step queries trigger skills; simple ones don't

Layer 3 — Full Skill Loading (conditional context expansion):
  • Once a skill is selected, its full SKILL.md body is loaded into context
  • This includes step-by-step workflow, code examples, error handling
  • Referenced scripts are executed as bash tool calls

Layer 4 — Execution (follow the workflow):
  • Claude follows the skill's documented workflow step by step
  • Executes scripts, processes output, formats the response
  • Returns a structured, skill-aware response

════════════════════════════════════════════════════════════════
LANGGRAPH IMPLEMENTATION
════════════════════════════════════════════════════════════════

State machine nodes:
  initialize  → load skill registry (Layer 1)
  route       → select skill via LLM (Layer 2)
  load_skill  → load full SKILL.md body (Layer 3)
  extract     → extract parameters from query
  execute     → run skill scripts / tools (Layer 4)
  synthesize  → LLM produces final response with skill context
  respond     → no skill needed, plain LLM response
"""

import os
import re
from typing import TypedDict, Optional, Any
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

from skill_registry import load_skill_registry, load_full_skill, SkillMetadata, LoadedSkill
from skill_matcher import select_skill
from skill_executor import execute_skill

load_dotenv()


# ═══════════════════════════════════════════════════════════════════════════════
# Graph State Definition
# ═══════════════════════════════════════════════════════════════════════════════

class SkillAgentState(TypedDict):
    # Input
    user_query: str

    # Registry (loaded once at startup, carried through state)
    skill_registry: dict[str, SkillMetadata]

    # Skill selection results
    selected_skill_name: Optional[str]
    skill_confidence: float
    skill_selection_reasoning: str

    # Loaded skill (full SKILL.md body)
    loaded_skill: Optional[LoadedSkill]

    # Parameter extraction
    extracted_params: dict[str, Any]

    # Execution results
    execution_result: Optional[dict[str, Any]]

    # LLM conversation history
    messages: list

    # Final response
    final_response: str

    # Pipeline trace (for debugging / transparency)
    pipeline_trace: list[str]


# ═══════════════════════════════════════════════════════════════════════════════
# Node Implementations
# ═══════════════════════════════════════════════════════════════════════════════

def build_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1,
    )


# ── Node 1: Initialize ────────────────────────────────────────────────────────

def node_initialize(state: SkillAgentState) -> SkillAgentState:
    """
    Load the skill registry.
    Mirrors: Claude receiving <available_skills> in its system prompt.
    """
    trace = state.get("pipeline_trace", [])
    trace.append("📦 [INITIALIZE] Loading skill registry...")

    registry = load_skill_registry()
    skill_names = list(registry.keys())
    trace.append(f"   ✓ Loaded {len(registry)} skills: {skill_names}")

    return {
        **state,
        "skill_registry": registry,
        "pipeline_trace": trace,
    }


# ── Node 2: Route (Skill Selection) ──────────────────────────────────────────

def node_route(state: SkillAgentState) -> SkillAgentState:
    """
    Use Gemini to decide which skill matches the user query.
    Mirrors: Claude's internal skill-triggering logic.
    """
    trace = state["pipeline_trace"]
    trace.append(f"\n🔍 [ROUTE] Analyzing query for skill match...")
    trace.append(f"   Query: \"{state['user_query']}\"")

    llm = build_llm()
    skill_name, confidence, reasoning = select_skill(
        state["user_query"],
        state["skill_registry"],
        llm,
    )

    if skill_name:
        trace.append(f"   ✓ Skill selected: '{skill_name}' (confidence: {confidence:.2f})")
        trace.append(f"   Reasoning: {reasoning}")
    else:
        trace.append(f"   ✗ No skill needed (confidence: {confidence:.2f})")
        trace.append(f"   Reasoning: {reasoning}")

    return {
        **state,
        "selected_skill_name": skill_name,
        "skill_confidence": confidence,
        "skill_selection_reasoning": reasoning,
        "pipeline_trace": trace,
    }


def route_condition(state: SkillAgentState) -> str:
    """Conditional edge: go to skill pipeline or plain response."""
    if state.get("selected_skill_name"):
        return "load_skill"
    return "respond"


# ── Node 3: Load Full Skill ───────────────────────────────────────────────────

def node_load_skill(state: SkillAgentState) -> SkillAgentState:
    """
    Load the full SKILL.md body for the selected skill.
    Mirrors: Claude expanding a skill's context from metadata-only to full instructions.
    """
    trace = state["pipeline_trace"]
    skill_name = state["selected_skill_name"]
    trace.append(f"\n📖 [LOAD_SKILL] Loading full SKILL.md for '{skill_name}'...")

    registry = state["skill_registry"]
    metadata = registry[skill_name]
    loaded = load_full_skill(metadata)

    trace.append(f"   ✓ Instructions loaded ({len(loaded.full_instructions)} chars)")
    if loaded.available_scripts:
        trace.append(f"   ✓ Available scripts: {loaded.available_scripts}")
    if loaded.available_references:
        trace.append(f"   ✓ Available references: {loaded.available_references}")

    return {
        **state,
        "loaded_skill": loaded,
        "pipeline_trace": trace,
    }


# ── Node 4: Extract Parameters ────────────────────────────────────────────────

def node_extract_params(state: SkillAgentState) -> SkillAgentState:
    """
    Extract skill-specific parameters from the user query using Gemini.
    E.g., for youtube-transcript: extract the video URL.
    Mirrors: Claude parsing the user query to find what the skill needs.
    """
    trace = state["pipeline_trace"]
    skill_name = state["selected_skill_name"]
    trace.append(f"\n🔎 [EXTRACT] Extracting parameters for '{skill_name}'...")

    params = {}

    if skill_name == "youtube-transcript":
        # Try regex first for YouTube URLs
        url_pattern = r'(https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)[\w_-]+(?:\?[\w=&%-]*)?|(?<!\w)[a-zA-Z0-9_-]{11}(?!\w))'
        matches = re.findall(url_pattern, state["user_query"])
        if matches:
            params["video_url"] = matches[0]
            trace.append(f"   ✓ Extracted video URL: {matches[0]}")
        else:
            # Ask Gemini to extract it
            llm = build_llm()
            extract_prompt = f"""Extract the YouTube video URL or video ID from this text.
Respond with ONLY the URL or ID, nothing else.
If none found, respond with: NONE

Text: {state['user_query']}"""
            resp = llm.invoke([HumanMessage(content=extract_prompt)])
            extracted = resp.content.strip()
            if extracted and extracted != "NONE":
                params["video_url"] = extracted
                trace.append(f"   ✓ LLM extracted: {extracted}")
            else:
                trace.append("   ✗ No video URL found")

        # Extract language preference if mentioned
        lang_match = re.search(r'\b(spanish|french|german|hindi|japanese|korean|portuguese|italian|arabic|russian)\b',
                                state["user_query"], re.IGNORECASE)
        lang_map = {
            'spanish': 'es', 'french': 'fr', 'german': 'de', 'hindi': 'hi',
            'japanese': 'ja', 'korean': 'ko', 'portuguese': 'pt', 'italian': 'it',
            'arabic': 'ar', 'russian': 'ru'
        }
        if lang_match:
            params["language"] = lang_map.get(lang_match.group(1).lower(), 'en')
            trace.append(f"   ✓ Language preference: {params['language']}")

    return {
        **state,
        "extracted_params": params,
        "pipeline_trace": trace,
    }


# ── Node 5: Execute Skill ─────────────────────────────────────────────────────

def node_execute(state: SkillAgentState) -> SkillAgentState:
    """
    Execute the skill's scripts and tools.
    Mirrors: Claude calling bash_tool to run scripts referenced in SKILL.md.
    """
    trace = state["pipeline_trace"]
    skill_name = state["selected_skill_name"]
    trace.append(f"\n⚙️  [EXECUTE] Running skill '{skill_name}'...")

    loaded_skill = state["loaded_skill"]
    result = execute_skill(loaded_skill, state["user_query"], state["extracted_params"])

    if result.get("success"):
        trace.append(f"   ✓ Execution successful")
        for step in result.get("steps", []):
            trace.append(f"   {step}")
    else:
        trace.append(f"   ✗ Execution failed: {result.get('error')}")

    return {
        **state,
        "execution_result": result,
        "pipeline_trace": trace,
    }


# ── Node 6: Synthesize Response (with skill context) ─────────────────────────

def node_synthesize(state: SkillAgentState) -> SkillAgentState:
    """
    Use Gemini to produce the final response, informed by:
      - The full SKILL.md instructions
      - The execution results (transcript data, etc.)
    Mirrors: Claude generating its final response after executing the skill workflow.
    """
    trace = state["pipeline_trace"]
    trace.append(f"\n✍️  [SYNTHESIZE] Generating response with skill context...")

    llm = build_llm()
    exec_result = state["execution_result"]
    loaded_skill = state["loaded_skill"]

    # Build system prompt with full skill instructions (Layer 3 context injection)
    system_content = f"""You are a helpful AI assistant with access to specialized skills.

You have loaded the following skill and must follow its instructions precisely:

--- SKILL INSTRUCTIONS START ---
{loaded_skill.full_instructions}
--- SKILL INSTRUCTIONS END ---

Follow the skill's workflow and output format guidelines to respond to the user."""

    # Build user message with execution results
    if exec_result and exec_result.get("success"):
        skill_name = state["selected_skill_name"]

        if skill_name == "youtube-transcript":
            format_type = exec_result.get("format_type", "medium")
            duration = exec_result.get("duration_seconds", 0)
            transcript = exec_result.get("transcript", "")
            timestamped = exec_result.get("transcript_with_timestamps", "")
            video_id = exec_result.get("video_id", "")
            lang = exec_result.get("language_used", "en")
            segments = exec_result.get("segment_count", 0)

            user_content = f"""User request: {state['user_query']}

Execution results:
- Video ID: {video_id}
- Duration: {duration:.0f} seconds ({format_type} video)
- Language: {lang}
- Segments: {segments}
- Character count: {exec_result.get('character_count', 0)}

TRANSCRIPT DATA:
{transcript[:8000]}{"..." if len(transcript) > 8000 else ""}

TIMESTAMPED VERSION (first 3000 chars):
{timestamped[:3000]}{"..." if len(timestamped) > 3000 else ""}

Please format the response according to the skill's output formatting guidelines for a {format_type} video."""

        else:
            user_content = f"""User request: {state['user_query']}
Skill execution result: {exec_result}"""

    else:
        error = exec_result.get("error", "Unknown error") if exec_result else "Execution failed"
        user_content = f"""User request: {state['user_query']}

The skill execution encountered an error: {error}

Please inform the user of the issue and provide helpful guidance."""

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_content),
    ]

    response = llm.invoke(messages)
    final_response = response.content

    trace.append(f"   ✓ Response generated ({len(final_response)} chars)")

    return {
        **state,
        "final_response": final_response,
        "messages": messages + [AIMessage(content=final_response)],
        "pipeline_trace": trace,
    }


# ── Node 7: Plain Response (no skill) ────────────────────────────────────────

def node_respond(state: SkillAgentState) -> SkillAgentState:
    """
    Plain LLM response when no skill is needed.
    Mirrors: Claude answering directly without loading any skill.
    """
    trace = state["pipeline_trace"]
    trace.append(f"\n💬 [RESPOND] No skill needed — generating direct response...")

    llm = build_llm()
    messages = [
        SystemMessage(content="You are a helpful AI assistant."),
        HumanMessage(content=state["user_query"]),
    ]
    response = llm.invoke(messages)

    trace.append(f"   ✓ Direct response generated")

    return {
        **state,
        "final_response": response.content,
        "messages": messages + [AIMessage(content=response.content)],
        "pipeline_trace": trace,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Graph Assembly
# ═══════════════════════════════════════════════════════════════════════════════

def build_skills_graph() -> StateGraph:
    """
    Assemble the LangGraph state machine that mirrors Claude's skill pipeline.

    Flow:
      initialize → route → [load_skill → extract → execute → synthesize]
                         ↘ [respond]
    """
    graph = StateGraph(SkillAgentState)

    # Register nodes
    graph.add_node("initialize", node_initialize)
    graph.add_node("route", node_route)
    graph.add_node("load_skill", node_load_skill)
    graph.add_node("extract", node_extract_params)
    graph.add_node("execute", node_execute)
    graph.add_node("synthesize", node_synthesize)
    graph.add_node("respond", node_respond)

    # Define edges
    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "route")

    # Conditional edge: skill path vs. plain path
    graph.add_conditional_edges(
        "route",
        route_condition,
        {
            "load_skill": "load_skill",
            "respond": "respond",
        }
    )

    # Skill execution pipeline
    graph.add_edge("load_skill", "extract")
    graph.add_edge("extract", "execute")
    graph.add_edge("execute", "synthesize")

    # Terminal edges
    graph.add_edge("synthesize", END)
    graph.add_edge("respond", END)

    return graph.compile()


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def run_query(user_query: str, verbose: bool = True) -> dict[str, Any]:
    """
    Run a user query through the full skills pipeline.
    Returns the final response and pipeline trace.
    """
    app = build_skills_graph()

    initial_state: SkillAgentState = {
        "user_query": user_query,
        "skill_registry": {},
        "selected_skill_name": None,
        "skill_confidence": 0.0,
        "skill_selection_reasoning": "",
        "loaded_skill": None,
        "extracted_params": {},
        "execution_result": None,
        "messages": [],
        "final_response": "",
        "pipeline_trace": [f"🚀 Starting skills pipeline for query: \"{user_query}\""],
    }

    final_state = app.invoke(initial_state)

    if verbose:
        print("\n" + "═" * 60)
        print("PIPELINE TRACE")
        print("═" * 60)
        for line in final_state["pipeline_trace"]:
            print(line)
        print("═" * 60)

    return {
        "response": final_state["final_response"],
        "skill_used": final_state.get("selected_skill_name"),
        "confidence": final_state.get("skill_confidence", 0.0),
        "trace": final_state["pipeline_trace"],
    }


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "Please summarize this YouTube video: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )

    result = run_query(query)

    print("\n" + "═" * 60)
    print("FINAL RESPONSE")
    print("═" * 60)
    print(result["response"])

    if result["skill_used"]:
        print(f"\n[Skill used: {result['skill_used']} | Confidence: {result['confidence']:.2f}]")
