"""
skill_agent.py

LangGraph agent that replicates Claude's skill execution pipeline.

NEW in this version:
  - Registry is always loaded fresh (get_registry()) so newly created skills
    are immediately visible without restarting the process.
  - Dynamic tool loading: after a new skill is created and its @tool stub is
    appended to this file, reload_tools() re-imports this module and rebuilds
    the TOOLS list and compiled graph in memory.
  - run_agent() accepts an optional `registry` override so callers (app.py,
    test_agent.py) can pass a freshly-loaded registry after skill creation.

Pipeline steps (unchanged):
  STEP 1  — SKILL DISCOVERY   (system prompt injection from registry)
  STEP 2  — SKILL ROUTING     (LLM picks best skill from descriptions)
  STEP 3  — SKILL READING     (read_skill_instructions called first)
  STEP 4  — SKILL EXECUTION   (LLM follows SKILL.md workflow, calls tools)
  STEP 5  — RESPONSE GENERATION

LLM: Google Gemini 2.0 Flash (langchain-google-genai)
Orchestration: LangGraph StateGraph
"""

import os
import sys
import json
import importlib
import importlib.util
from pathlib import Path
from typing import TypedDict, Annotated, Optional, List, Dict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from skills_registry import get_registry, format_skills_for_prompt, get_skill_instructions

PROJECT_ROOT   = Path(__file__).parent
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")


# ══════════════════════════════════════════════════════════════════════════════
# STATE
# ══════════════════════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    messages:           Annotated[list, add_messages]
    selected_skill:     Optional[str]
    skill_instructions: Optional[str]
    tool_results:       List[dict]
    final_response:     Optional[str]


# ══════════════════════════════════════════════════════════════════════════════
# BUILT-IN TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@tool
def extract_youtube_transcript(video_url_or_id: str, languages: str = "en") -> str:
    """
    Extract the transcript from a YouTube video.
    Use this when the user provides a YouTube URL or video ID and wants the transcript,
    summary, or any content derived from the video.

    Args:
        video_url_or_id: Full YouTube URL or 11-character video ID.
        languages: Comma-separated language codes to try, e.g. "en,es,fr".
    Returns:
        JSON string with transcript text, segments, and metadata.
    """
    scripts_dir = PROJECT_ROOT / "skills" / "youtube-transcript" / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import extract_transcript as et
        importlib.reload(et)
        video_id = et.extract_video_id(video_url_or_id)
        if not video_id:
            return json.dumps({"error": f"Could not extract video ID from: {video_url_or_id}"})
        lang_list = [l.strip() for l in languages.split(",") if l.strip()]
        result = et.get_transcript(video_id, lang_list)
        if result.get("success") and len(result.get("transcript", "")) > 12000:
            result["transcript"] = result["transcript"][:12000] + "\n\n[... truncated ...]"
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "error_type": type(e).__name__})
    finally:
        if str(scripts_dir) in sys.path:
            sys.path.remove(str(scripts_dir))


@tool
def extract_youtube_transcript_with_timestamps(video_url_or_id: str) -> str:
    """
    Extract a YouTube transcript with [MM:SS] timestamp markers on every segment.

    Args:
        video_url_or_id: Full YouTube URL or 11-character video ID.
    Returns:
        JSON string with timestamped segments.
    """
    scripts_dir = PROJECT_ROOT / "skills" / "youtube-transcript" / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import extract_transcript as et
        importlib.reload(et)
        video_id = et.extract_video_id(video_url_or_id)
        if not video_id:
            return json.dumps({"error": f"Could not extract video ID from: {video_url_or_id}"})
        result = et.get_transcript_with_timestamps(video_id)
        if result.get("success") and len(result.get("formatted_with_timestamps", "")) > 10000:
            result["formatted_with_timestamps"] = (
                result["formatted_with_timestamps"][:10000] + "\n[... truncated ...]"
            )
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        if str(scripts_dir) in sys.path:
            sys.path.remove(str(scripts_dir))


@tool
def list_available_skills() -> str:
    """List all skills currently in the skills registry with their descriptions."""
    registry = get_registry()
    if not registry:
        return "No skills are currently loaded."
    return "\n".join(
        f"- **{name}**: {skill['description']}" for name, skill in registry.items()
    )


@tool
def read_skill_instructions(skill_name: str) -> str:
    """
    Read the full SKILL.md workflow instructions for a skill before executing it.
    MUST be called before any skill-specific tool so the LLM knows the exact workflow.

    Args:
        skill_name: Exact skill name, e.g. 'youtube-transcript'.
    Returns:
        Full SKILL.md body with workflow, patterns, error handling, and output format.
    """
    registry = get_registry()
    instructions = get_skill_instructions(registry, skill_name)
    if not instructions:
        return f"Skill '{skill_name}' not found. Available: {list(registry.keys())}"
    return instructions


# ══════════════════════════════════════════════════════════════════════════════
# DYNAMIC TOOL REGISTRY
# Keeps all tools in one place so reload_tools() can rebuild everything.
# New @tool stubs injected by create_skill.py are appended above TOOLS_LIST.
# ══════════════════════════════════════════════════════════════════════════════


@tool
def medium_blog_generator_tool(topic: str) -> str:
    """
    Generate a complete, publication-ready Medium blog post on any technical topic.
    Use this when the user asks to write a blog post, article, Medium post, or any
    long-form technical content. The post includes all 11 sections: Introduction,
    Challenges Faced Currently, Solution, Advantages, Comparison with Old Approach,
    Architecture Flow, Technology Stack Used, Code Implementation, Future Scope,
    Conclusion, and References.
    """
    scripts_dir = Path(__file__).parent / "skills" / "medium-blog-generator" / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import medium_blog_generator as mbg
        importlib.reload(mbg)

        # Parse optional flags from the topic string
        audience = "intermediate"
        code_language = "python"
        for token in topic.split():
            if token.lower() in ("beginner", "intermediate", "advanced"):
                audience = token.lower()
            if token.lower() in ("python", "javascript", "typescript", "go", "java", "rust", "yaml"):
                code_language = token.lower()

        result = mbg.run_medium_blog_generator(
            topic=topic,
            audience=audience,
            code_language=code_language,
        )

        if result.get("success"):
            meta = result.get("metadata", {})
            val  = result.get("validation", {})
            header = (
                f"<!-- Generated by medium-blog-generator skill | "
                f"Words: {meta.get('word_count','?')} | "
                f"Sections: {val.get('section_count','?')}/11 | "
                f"Read: {meta.get('read_time','?')} min -->\n\n"
            )
            return header + result["blog_post"]
        else:
            return json.dumps({"error": result.get("error"), "success": False})

    except Exception as e:
        return json.dumps({"error": str(e), "error_type": type(e).__name__})
    finally:
        if str(scripts_dir) in sys.path:
            sys.path.remove(str(scripts_dir))


TOOLS_LIST = [
    medium_blog_generator_tool,
    extract_youtube_transcript,
    extract_youtube_transcript_with_timestamps,
    list_available_skills,
    read_skill_instructions,
]

# These are the live objects used by the agent — updated by reload_tools()
TOOLS    = list(TOOLS_LIST)
TOOL_MAP = {t.name: t for t in TOOLS}


def reload_tools():
    """
    Rebuild TOOLS and TOOL_MAP from the current module state.
    Called by app.py after a new skill is created so the new @tool is live
    immediately without restarting Streamlit.
    """
    global TOOLS, TOOL_MAP, AGENT_GRAPH

    # Re-import this module to pick up newly appended @tool functions
    module_name = Path(__file__).stem
    if module_name in sys.modules:
        mod = importlib.reload(sys.modules[module_name])
        TOOLS    = mod.TOOLS_LIST
        TOOL_MAP = {t.name: t for t in TOOLS}
    else:
        TOOLS    = list(TOOLS_LIST)
        TOOL_MAP = {t.name: t for t in TOOLS}

    # Rebuild the compiled graph with the new tool set
    AGENT_GRAPH = _build_graph()
    print(f"[SkillAgent] Tools reloaded — {len(TOOLS)} tools active: "
          f"{[t.name for t in TOOLS]}")


# ══════════════════════════════════════════════════════════════════════════════
# LLM FACTORY
# ══════════════════════════════════════════════════════════════════════════════

def _get_llm():
    """Return Gemini 2.0 Flash bound to current TOOLS list."""
    api_key = os.environ.get("GOOGLE_API_KEY", GOOGLE_API_KEY)
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY environment variable not set.\n"
            "  Windows : set GOOGLE_API_KEY=your_key\n"
            "  Linux   : export GOOGLE_API_KEY=your_key"
        )
    llm = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        google_api_key=api_key,
        temperature=0.1,
    )
    return llm.bind_tools(TOOLS)


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

def build_system_prompt(registry: Optional[Dict] = None) -> str:
    """
    Build the system prompt that injects all skill descriptions.
    Mirrors Claude's <available_skills> block.
    Accepts an optional registry override for freshly-loaded post-creation state.
    """
    if registry is None:
        registry = get_registry()

    skills_block = format_skills_for_prompt(registry)

    return f"""You are an intelligent assistant with access to a set of **Skills** — \
specialized capabilities with documented workflows.

## How to Handle Requests

1. **Identify** whether any available skill matches the user's request.
2. **Read instructions first** — always call `read_skill_instructions` with the skill name \
before calling any skill-specific tool.
3. **Execute** the skill workflow exactly as documented.
4. **Synthesize** all tool outputs into a comprehensive, well-formatted final response.

---

{skills_block}

---

## Rules
- Call `read_skill_instructions` BEFORE any skill-specific tool — no exceptions.
- For YouTube URLs or video IDs → **youtube-transcript** skill.
- For technical video guides/summaries → **youtube-tech-summarizer** skill.
- Follow each skill's output formatting guidelines precisely.
- If no skill applies, answer directly from your own knowledge.
- Execute immediately — do not ask for confirmation before starting.
"""


# ══════════════════════════════════════════════════════════════════════════════
# LANGGRAPH NODES
# ══════════════════════════════════════════════════════════════════════════════

def _agent_node(state: AgentState, registry: Optional[Dict] = None) -> AgentState:
    """Main reasoning node — LLM decides what tool to call next (or ends)."""
    llm      = _get_llm()
    messages = [SystemMessage(content=build_system_prompt(registry))] + state["messages"]
    response = llm.invoke(messages)

    selected_skill = state.get("selected_skill")
    if response.tool_calls:
        for tc in response.tool_calls:
            if tc["name"] == "read_skill_instructions":
                selected_skill = tc["args"].get("skill_name", selected_skill)

    return {
        "messages":           [response],
        "selected_skill":     selected_skill,
        "skill_instructions": state.get("skill_instructions"),
        "tool_results":       state.get("tool_results", []),
        "final_response":     state.get("final_response"),
    }


def _tool_node(state: AgentState) -> AgentState:
    """Tool execution node — runs each tool call and wraps results as ToolMessages."""
    last_msg           = state["messages"][-1]
    tool_results       = state.get("tool_results", [])
    skill_instructions = state.get("skill_instructions")
    new_messages       = []

    for tc in last_msg.tool_calls:
        name    = tc["name"]
        args    = tc["args"]
        call_id = tc["id"]

        print(f"[ToolExecution] → {name}({json.dumps(args)[:120]})")

        if name in TOOL_MAP:
            try:
                result = TOOL_MAP[name].invoke(args)
            except Exception as e:
                result = json.dumps({"error": str(e), "tool": name})
        else:
            result = json.dumps({"error": f"Unknown tool: {name}"})

        print(f"[ToolExecution] ← {str(result)[:200]}")

        if name == "read_skill_instructions":
            skill_instructions = result

        tool_results.append({
            "tool":           name,
            "args":           args,
            "result_preview": str(result)[:500],
        })

        new_messages.append(ToolMessage(content=result, tool_call_id=call_id, name=name))

    return {
        "messages":           new_messages,
        "selected_skill":     state.get("selected_skill"),
        "skill_instructions": skill_instructions,
        "tool_results":       tool_results,
        "final_response":     state.get("final_response"),
    }


def _should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "execute_tools"
    return "end"


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH
# ══════════════════════════════════════════════════════════════════════════════

def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("agent",         _agent_node)
    graph.add_node("execute_tools", _tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent", _should_continue,
        {"execute_tools": "execute_tools", "end": END}
    )
    graph.add_edge("execute_tools", "agent")
    return graph.compile()


AGENT_GRAPH = _build_graph()


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def run_agent(
    user_query:  str,
    verbose:     bool           = True,
    registry:    Optional[Dict] = None,
) -> Dict:
    """
    Run the skill agent for a single user query.

    Args:
        user_query : The user's natural-language request.
        verbose    : Print the execution trace to stdout.
        registry   : Optional pre-loaded registry dict. When None, a fresh one
                     is loaded from disk — so newly created skills are always visible.

    Returns:
        A dict with keys:
            response       (str)  — the final text answer
            selected_skill (str)  — which skill was used, or None
            tools_called   (list) — names of every tool that was invoked
    """
    if registry is None:
        registry = get_registry()

    if verbose:
        print(f"\n{'='*60}")
        print(f"QUERY : {user_query}")
        print(f"SKILLS: {list(registry.keys())}")
        print(f"{'='*60}\n")

    # Patch the agent node so it uses the caller-supplied registry
    def agent_node_with_registry(state: AgentState) -> AgentState:
        return _agent_node(state, registry=registry)

    # Build a fresh graph that captures the registry in its closure
    graph = StateGraph(AgentState)
    graph.add_node("agent",         agent_node_with_registry)
    graph.add_node("execute_tools", _tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent", _should_continue,
        {"execute_tools": "execute_tools", "end": END}
    )
    graph.add_edge("execute_tools", "agent")
    compiled = graph.compile()

    initial_state: AgentState = {
        "messages":           [HumanMessage(content=user_query)],
        "selected_skill":     None,
        "skill_instructions": None,
        "tool_results":       [],
        "final_response":     None,
    }

    final_state = compiled.invoke(initial_state, config={"recursion_limit": 25})

    last_msg   = final_state["messages"][-1]
    response   = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    tools_used = [t["tool"] for t in final_state.get("tool_results", [])]

    if verbose:
        print(f"\n{'='*60}")
        print("RESPONSE:")
        print(f"{'='*60}")
        print(response)
        print(f"\nSkill used  : {final_state.get('selected_skill')}")
        print(f"Tools called: {tools_used}")

    return {
        "response":       response,
        "selected_skill": final_state.get("selected_skill"),
        "tools_called":   tools_used,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "Get the transcript for this video: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
    result = run_agent(query)
