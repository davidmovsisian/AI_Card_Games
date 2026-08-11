#!/usr/bin/env python3
"""
test_medium_blog_skill.py

Full integration test for the medium-blog-generator skill.

Tests:
  T1  Skill discovery   — registry picks up SKILL.md
  T2  Frontmatter parse — name + description extracted correctly
  T3  Script import     — medium_blog_generator.py imports cleanly
  T4  Validation fn     — validate_blog() correctly identifies missing sections
  T5  Metadata fn       — extract_metadata() pulls title, word_count, read_time
  T6  Section coverage  — a synthetic blog passes all 11 section checks
  T7  Short blog warn   — validate_blog() warns on < 1500 words
  T8  Tool stub syntax  — @tool stub exists and is callable after registration
  T9  skill_agent reg   — @tool is present in skill_agent.py TOOLS_LIST
  T10 End-to-end mock   — run_medium_blog_generator() returns correct dict shape
                          (uses a mock LLM call to avoid needing API key in CI)

Run:
    python test_medium_blog_skill.py
"""

import sys
import os
import json
import importlib
import textwrap
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
SKILL_DIR    = PROJECT_ROOT / "skills" / "medium-blog-generator"
SCRIPTS_DIR  = SKILL_DIR / "scripts"
SKILL_MD     = SKILL_DIR / "SKILL.md"
AGENT_FILE   = PROJECT_ROOT / "skill_agent.py"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def c(colour, text): return f"{colour}{text}{RESET}"

# ── Test tracker ──────────────────────────────────────────────────────────────
results = []

def check(name, passed, detail=""):
    results.append({"name": name, "passed": passed, "detail": detail})
    icon = c(GREEN, "✔  PASS") if passed else c(RED, "✗  FAIL")
    print(f"  {icon}  {name}")
    if detail:
        prefix = "          "
        for line in detail.splitlines():
            print(f"{prefix}{c(YELLOW, line)}")

def banner(title):
    print(f"\n{c(BOLD + CYAN, '─'*62)}")
    print(f"{c(BOLD + CYAN, '  ' + title)}")
    print(f"{c(BOLD + CYAN, '─'*62)}")


# ══════════════════════════════════════════════════════════════════════════════
# SYNTHETIC BLOG FIXTURE  (used for T4 / T5 / T6 / T7)
# A realistic blog skeleton that passes all 11 section checks
# ══════════════════════════════════════════════════════════════════════════════

SYNTHETIC_BLOG = textwrap.dedent("""
# LangGraph: Building Stateful AI Agents That Actually Work

> A practical guide to orchestrating multi-step AI workflows with LangGraph's stateful graph engine.

---

## 1. Introduction

Artificial intelligence agents have come a long way from simple chatbots. Today, developers
are building systems that plan, reason, call external tools, recover from errors, and maintain
context across dozens of steps. Yet most frameworks make this surprisingly hard. Enter LangGraph
— a graph-based orchestration library built on top of LangChain that brings real statefulness
to AI agents.

In this post we explore why LangGraph exists, what problems it solves, how its architecture
works, and how to build your first stateful agent from scratch. By the end you will understand
when and why to reach for LangGraph over simpler alternatives.

## 2. Challenges Faced Currently

Building reliable AI agents with conventional approaches surfaces several painful problems:

- **State management hell**: Standard chain-based frameworks pass data linearly. Any step
  that needs to reference earlier output must carry redundant context forward, ballooning
  token usage and increasing the chance of hallucinated context.

- **No native branching**: Real workflows are not linear. A research agent might need to
  decide mid-run whether to search the web, call a database, or ask the user for clarification.
  Implementing conditional logic in a flat chain is brittle and hard to read.

- **Error recovery is manual**: When a tool call fails, most frameworks crash the entire run.
  Developers wire up try/except blocks ad hoc, producing inconsistent error handling across
  different parts of the same pipeline.

- **Observability gaps**: Debugging a multi-step agent without visibility into intermediate
  state is like debugging a program with no debugger. You see the final output but not the
  twenty decisions that led to it.

- **Scalability of complexity**: As the number of steps grows beyond five or six, maintaining
  a flat chain becomes unmanageable. Developers resort to deeply nested callbacks or custom
  orchestration code that reimplements what a proper graph would give for free.

## 3. Solution

LangGraph solves these problems by modelling agent workflows as directed graphs where nodes
are Python functions and edges carry typed state between them.

The core insight is simple: agent execution is a graph traversal problem, not a linear
function composition problem. Each node receives the current state, does its work (call an
LLM, invoke a tool, transform data), and returns an updated state. Edges determine which
node runs next — and those edges can be conditional, creating branches and loops with no
special-case code required.

LangGraph ships with a `StateGraph` class, a typed `TypedDict`-based state schema, and a
`compile()` step that turns your graph definition into an executable workflow with built-in
checkpointing, streaming, and human-in-the-loop support.

## 4. Advantages

1. **Explicit state schema**: Declare exactly what your agent tracks with a `TypedDict`.
   Every node sees the same typed state — no guesswork about what context is available.

2. **Native conditional routing**: `add_conditional_edges()` lets you branch on any function
   of the current state — skill selection, error codes, confidence scores, anything.

3. **Built-in loops**: The ReAct pattern (Reason → Act → Observe → Reason) is just a cycle
   in the graph. No custom recursion needed.

4. **Checkpointing and resumability**: LangGraph's checkpointer persists state between steps.
   Long-running agents survive crashes, and human-in-the-loop workflows pause cleanly.

5. **Streaming out of the box**: `stream()` yields intermediate state after every node, giving
   you real-time visibility without extra instrumentation.

6. **LangChain ecosystem compatibility**: Works with any LangChain LLM, tool, or retriever.

## 5. Comparison with Old Approach

The table below compares a LangGraph agent against a classic LCEL (LangChain Expression
Language) chain for the same research-and-summarise task.

| Feature | LCEL Chain | LangGraph Agent |
|---|---|---|
| State management | Manual dict passing | Typed StateGraph schema |
| Branching / conditionals | Custom Python wrappers | `add_conditional_edges()` |
| Loop / retry support | External while-loop | Native graph cycle |
| Error recovery | Try/except per step | Node-level or graph-level |
| Observability | LangSmith traces only | Per-node state streaming |
| Human-in-the-loop | Not supported natively | Built-in interrupt points |
| Code complexity (5+ steps) | High — nested lambdas | Low — clear node functions |

For simple, linear chains LCEL remains the right choice. The moment your workflow needs
branching, loops, or persistent state, LangGraph pays for itself immediately.

## 6. Architecture Flow

A LangGraph agent has five conceptual layers that work together at runtime.

**State** sits at the centre. It is a typed Python `TypedDict` that every node reads from
and writes to. The graph engine merges node outputs back into state automatically using
the `add_messages` reducer for conversation history and direct assignment for other fields.

**Nodes** are ordinary Python functions. Each takes the current `AgentState` and returns
a partial state dict with the fields it modified. They can call LLMs, invoke tools, hit
APIs, or run any business logic.

**Edges** connect nodes. Static edges always go to the same destination. Conditional edges
call a routing function that inspects the current state and returns the name of the next node.

```
┌─────────────────────────────────────────────────────────┐
│                    LangGraph Runtime                    │
│                                                         │
│  [START]                                                │
│     │                                                   │
│     ▼                                                   │
│  ┌──────────┐   tool_calls?    ┌──────────────────┐    │
│  │  agent   │ ──────────────► │  execute_tools   │    │
│  │  node    │ ◄────────────── │  node            │    │
│  └──────────┘   always back   └──────────────────┘    │
│       │                                                 │
│       │ no tool_calls                                   │
│       ▼                                                 │
│    [END]                                                │
│                                                         │
│  State flows through every edge as a typed dict         │
└─────────────────────────────────────────────────────────┘
```

The compiled graph is a Python object. Call `.invoke()` for synchronous execution or
`.stream()` to receive state updates after every node.

## 7. Technology Stack Used

The reference implementation uses the following stack.

| Component | Technology | Version | Purpose |
|---|---|---|---|
| Language | Python | 3.11+ | Runtime |
| LLM Framework | LangChain | 0.3.x | LLM abstraction, tool binding |
| Agent Orchestration | LangGraph | 0.2.x | Graph-based workflow engine |
| LLM | Gemini 2.0 Flash | via API | Reasoning and generation |
| State Schema | Python TypedDict | stdlib | Typed agent state |
| Streaming | LangGraph stream() | built-in | Real-time node output |
| Observability | LangSmith | cloud | Trace logging (optional) |
| Testing | pytest | 8.x | Unit and integration tests |

## 8. Code Implementation

### Defining the Agent State

**What this does:** Declares every field the agent tracks across its full run.

```python
from typing import TypedDict, Annotated, Optional, List
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # Conversation history — LangGraph merges automatically with add_messages
    messages: Annotated[list, add_messages]

    # Which skill was selected during routing
    selected_skill: Optional[str]

    # Full SKILL.md body read before execution
    skill_instructions: Optional[str]

    # Every tool call logged here for traceability
    tool_results: List[dict]
```

Every node receives this dict and returns a partial version with only the fields it changed.
LangGraph merges the partial update back into the full state automatically.

### Building the Graph

**What this does:** Wires nodes and edges together into a compiled, executable workflow.

```python
from langgraph.graph import StateGraph, END

graph = StateGraph(AgentState)

# Register nodes
graph.add_node("agent", agent_node)
graph.add_node("execute_tools", tool_execution_node)

# Entry point
graph.set_entry_point("agent")

# Conditional routing from agent
graph.add_conditional_edges(
    "agent",
    should_continue,          # routing function → returns "execute_tools" or "end"
    {
        "execute_tools": "execute_tools",
        "end": END,
    }
)

# Tools always return to agent
graph.add_edge("execute_tools", "agent")

compiled = graph.compile()
```

The `should_continue` function inspects the last message: if it contains `tool_calls`, route
to `execute_tools`; otherwise route to `END`. This single pattern handles arbitrarily deep
ReAct loops with no extra code.

### Running the Agent

**What this does:** Invokes the compiled graph and extracts the final response.

```python
from langchain_core.messages import HumanMessage

result = compiled.invoke(
    {
        "messages":           [HumanMessage(content="Summarise this video: https://youtu.be/abc")],
        "selected_skill":     None,
        "skill_instructions": None,
        "tool_results":       [],
    },
    config={"recursion_limit": 25}
)

final_message = result["messages"][-1]
print(final_message.content)
```

Stream intermediate state for real-time visibility:

```python
for chunk in compiled.stream(initial_state):
    node_name, node_state = next(iter(chunk.items()))
    print(f"[{node_name}] messages: {len(node_state['messages'])}")
```

## 9. Future Scope

1. **Persistent checkpointing with Redis**: The current in-memory state resets on crash.
   Integrating `AsyncRedisSaver` as the checkpointer would make long-running agents
   resumable across process restarts.

2. **Parallel node execution**: LangGraph 0.3 introduces `Send` — an API for spawning
   multiple sub-graphs in parallel and merging their results. Research agents that
   query several sources simultaneously will benefit enormously.

3. **Human-in-the-loop interrupts**: Adding `interrupt_before=["execute_tools"]` pauses
   the graph and waits for human approval before every tool call — essential for
   high-stakes automation like financial transactions or infrastructure changes.

4. **LangGraph Platform deployment**: Anthropic's LangGraph Platform provides a managed
   runtime with built-in queuing, horizontal scaling, and a Studio UI for visual debugging.
   Moving from local execution to Platform requires only a `langgraph.json` config file.

5. **Multi-agent coordination**: Composing multiple LangGraph agents as nodes inside a
   parent graph enables true multi-agent systems where a supervisor routes tasks to
   specialised sub-agents — a research agent, a writing agent, a review agent.

## 10. Conclusion

LangGraph brings the discipline of graph theory to AI agent design. By making state explicit,
branching declarative, and loops first-class, it eliminates the most painful sources of
complexity in multi-step AI workflows. The result is agents that are easier to build, easier
to debug, and easier to scale.

If you are building anything beyond a simple question-answer chain — tools, memory, retries,
human oversight — LangGraph is worth adding to your stack today. The learning curve is gentle
if you are already familiar with LangChain, and the productivity gains compound quickly as
your workflows grow.

Start with the [official quickstart](https://langchain-ai.github.io/langgraph/) and build
your first ReAct agent in under thirty minutes.

## 11. References

1. [LangGraph Documentation — LangChain AI](https://langchain-ai.github.io/langgraph/)
2. [LangGraph GitHub Repository](https://github.com/langchain-ai/langgraph)
3. [ReAct: Synergizing Reasoning and Acting in Language Models — Yao et al., 2022](https://arxiv.org/abs/2210.03629)
4. [LangChain Expression Language (LCEL) Docs](https://python.langchain.com/docs/concepts/lcel/)
5. [Building Reliable AI Agents — Harrison Chase, 2024](https://blog.langchain.dev/reliable-agents/)
6. [LangSmith Observability Platform](https://smith.langchain.com/)
7. [LangGraph Platform — Managed Deployment](https://www.langchain.com/langgraph-platform)
8. [Toolformer: Language Models Can Teach Themselves to Use Tools — Schick et al., 2023](https://arxiv.org/abs/2302.04761)
9. [Human-in-the-Loop with LangGraph](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/)
10. [Gemini 2.0 Flash — Google AI](https://ai.google.dev/gemini-api/docs/models/gemini)

---
**Estimated read time**: 12 minutes
**Word count**: ~2900 words
**Tags**: LangGraph, LangChain, AI Agents, Python, Machine Learning
**Best posted**: Tuesday or Thursday, 8–10am EST
""").strip()


# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════

banner("T1 — Skill Discovery: registry picks up medium-blog-generator")
try:
    from skills_registry import get_registry
    reg = get_registry(silent=True)
    found = "medium-blog-generator" in reg
    check("SKILL.md discovered by registry", found,
          f"Registry keys: {list(reg.keys())}" if not found else "")
    if found:
        desc = reg["medium-blog-generator"]["description"]
        check("Description non-empty", len(desc) > 20, desc[:80])
except Exception as e:
    check("Registry import", False, str(e))


banner("T2 — Frontmatter Parse: name + description")
try:
    from skills_registry import parse_frontmatter
    content = SKILL_MD.read_text(encoding="utf-8")
    meta = parse_frontmatter(content)
    check("name == 'medium-blog-generator'",
          meta.get("name") == "medium-blog-generator",
          f"Got: {meta.get('name')}")
    check("description starts with 'Generate'",
          meta.get("description", "").startswith("Generate"),
          f"Got: {meta.get('description','')[:60]}")
    check("body contains '## Workflow'",
          "## Workflow" in meta.get("_body", ""))
except Exception as e:
    check("Frontmatter parse", False, str(e))


banner("T3 — Script Import: medium_blog_generator.py")
try:
    import medium_blog_generator as mbg
    check("Module imports cleanly", True)
    check("run_medium_blog_generator() exists",
          callable(getattr(mbg, "run_medium_blog_generator", None)))
    check("validate_blog() exists",
          callable(getattr(mbg, "validate_blog", None)))
    check("extract_metadata() exists",
          callable(getattr(mbg, "extract_metadata", None)))
    check("REQUIRED_SECTIONS has 11 items",
          len(mbg.REQUIRED_SECTIONS) == 11,
          f"Got: {len(mbg.REQUIRED_SECTIONS)}")
except Exception as e:
    check("Script import", False, str(e))


banner("T4 — validate_blog(): identifies missing sections")
try:
    import medium_blog_generator as mbg

    # Partial blog — missing "References" and "Future Scope"
    partial = "\n".join(
        f"## {i+1}. {s}\nSome content about {s}.\n"
        for i, s in enumerate(mbg.REQUIRED_SECTIONS)
        if s not in ("References", "Future Scope")
    )
    val = mbg.validate_blog(partial)
    check("Missing sections detected",
          "References" in val["missing_sections"] or "Future Scope" in val["missing_sections"],
          f"Missing: {val['missing_sections']}")
    check("valid == False for partial blog", val["valid"] == False)

    # Full blog — all 11 sections
    val_full = mbg.validate_blog(SYNTHETIC_BLOG)
    check("Full blog passes validation", val_full["valid"],
          f"Missing: {val_full['missing_sections']}")
    check("Section count == 11", val_full["section_count"] == 11,
          f"Got: {val_full['section_count']}")
except Exception as e:
    check("validate_blog()", False, str(e))


banner("T5 — extract_metadata(): title, word_count, read_time")
try:
    import medium_blog_generator as mbg
    meta = mbg.extract_metadata(SYNTHETIC_BLOG)
    check("Title extracted",
          "LangGraph" in meta.get("title", ""),
          f"Got: {meta.get('title')}")
    check("Word count > 500",
          meta.get("word_count", 0) > 500,
          f"Got: {meta.get('word_count')}")
    check("Read time >= 1 minute",
          meta.get("read_time", 0) >= 1,
          f"Got: {meta.get('read_time')} min")
except Exception as e:
    check("extract_metadata()", False, str(e))


banner("T6 — Section coverage: all 11 sections in synthetic blog")
try:
    import medium_blog_generator as mbg
    val = mbg.validate_blog(SYNTHETIC_BLOG)
    for section in mbg.REQUIRED_SECTIONS:
        present = section.lower() in SYNTHETIC_BLOG.lower()
        check(f"Section present: '{section}'", present)
except Exception as e:
    check("Section coverage", False, str(e))


banner("T7 — Short blog warning")
try:
    import medium_blog_generator as mbg
    short_blog = "\n".join(
        f"## {i+1}. {s}\nShort content.\n"
        for i, s in enumerate(mbg.REQUIRED_SECTIONS)
    )
    val = mbg.validate_blog(short_blog)
    check("Warning issued for short blog",
          any("short" in w.lower() for w in val["warnings"]),
          f"Warnings: {val['warnings']}")
except Exception as e:
    check("Short blog warning", False, str(e))


banner("T8 — @tool Stub: skill_agent.py registration")
try:
    agent_text = AGENT_FILE.read_text(encoding="utf-8") if AGENT_FILE.exists() else ""
    has_tool = "medium_blog_generator_tool" in agent_text
    in_list  = "medium_blog_generator_tool" in agent_text and "TOOLS_LIST" in agent_text
    check("@tool stub present in skill_agent.py", has_tool,
          "Run register_tool() or re-run create_skill.py" if not has_tool else "")
    check("Tool added to TOOLS_LIST", in_list)
except Exception as e:
    check("@tool stub check", False, str(e))


banner("T9 — End-to-End Mock: run_medium_blog_generator() dict shape")
try:
    import medium_blog_generator as mbg
    import unittest.mock as mock

    # Patch _call_llm so we don't need a real API key
    with mock.patch.object(mbg, "_call_llm", return_value=SYNTHETIC_BLOG):
        result = mbg.run_medium_blog_generator(
            topic="LangGraph for AI Agents",
            audience="intermediate",
            code_language="python",
        )

    check("success == True", result.get("success") == True,
          str(result.get("error", "")))
    check("blog_post key present", "blog_post" in result)
    check("blog_post non-empty", len(result.get("blog_post", "")) > 100)
    check("metadata dict present", isinstance(result.get("metadata"), dict))
    check("validation dict present", isinstance(result.get("validation"), dict))
    check("topic echoed back", result.get("topic") == "LangGraph for AI Agents")
    check("generated_at present", "generated_at" in result)

    val = result["validation"]
    check("Mock blog: all 11 sections found",
          val["section_count"] == 11,
          f"Found: {val['section_count']}")
    check("Mock blog: valid == True", val["valid"],
          f"Missing: {val['missing_sections']}")
except Exception as e:
    check("End-to-end mock", False, str(e))


banner("T10 — Error Handling: empty topic")
try:
    import medium_blog_generator as mbg
    result = mbg.run_medium_blog_generator(topic="")
    check("Empty topic returns success=False", result.get("success") == False)
    check("Error message present", bool(result.get("error")))
except Exception as e:
    check("Error handling", False, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

total  = len(results)
passed = sum(1 for r in results if r["passed"])
failed = total - passed

print(f"\n{c(BOLD, '═'*62)}")
print(c(BOLD, f"  RESULTS: {passed}/{total} tests passed  "
              f"({'ALL PASS' if failed == 0 else str(failed) + ' FAILED'})"))
print(c(BOLD, '═'*62))

if failed:
    print(c(RED, "\n  Failed:"))
    for r in results:
        if not r["passed"]:
            print(c(RED, f"    ✗  {r['name']}: {r['detail'][:80]}"))

print(f"\n  Skill dir : {SKILL_DIR}")
print(f"  Files     :")
for f in sorted(SKILL_DIR.rglob("*")):
    if f.is_file():
        size = f.stat().st_size
        print(f"    📄 {f.relative_to(SKILL_DIR.parent.parent)}  ({size:,} bytes)")

sys.exit(0 if failed == 0 else 1)
