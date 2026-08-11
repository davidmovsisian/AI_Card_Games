# LangChain Skills Agent
### A LangGraph + Gemini 2.0 Flash Replica of Claude's Skill Execution Pipeline
### Now with integrated Skill Creation, Hot-Reload, and a 3-Tab Streamlit UI

---

## 📁 Project Structure

```
langchain_skills/
│
├── app.py                  ← 3-tab Streamlit UI (Chat / Create Skill / Skill Library)
├── skill_agent.py          ← LangGraph agent engine with hot-reload support
├── skills_registry.py      ← Skill discovery — always reads fresh from disk
├── create_skill.py         ← Skill creation pipeline (CLI + programmatic API)
├── test_agent.py           ← Test suite (3 modes: built-in / create+run / full)
├── requirements.txt        ← All Python dependencies
│
├── README.md               ← This file
├── architecture_flow.md    ← Detailed architecture and data flow
├── skill_template.md       ← How to structure a skill folder
│
└── skills/
    ├── youtube-transcript/
    │   ├── SKILL.md                      ← Skill metadata + workflow instructions
    │   └── scripts/
    │       └── extract_transcript.py     ← YouTube transcript extraction logic
    │
    └── youtube-tech-summarizer/
        └── SKILL.md                      ← Technical video → guide workflow
```

---

## 📦 The Core Files

| File | Role | Key Exports |
|------|------|-------------|
| `skills_registry.py` | **Skill discovery** — scans `skills/*/SKILL.md`, parses YAML frontmatter, builds registry. Always reads fresh from disk via `get_registry()`. | `get_registry()`, `format_skills_for_prompt()`, `get_skill_instructions()` |
| `skill_agent.py` | **Agent engine** — LangGraph `StateGraph` with Gemini 2.0 Flash. Supports fresh-registry injection and hot-reload after skill creation. | `run_agent()`, `reload_tools()` |
| `create_skill.py` | **Skill creator** — mimics Claude Code's skill-creator pipeline. Works both interactively (CLI) and programmatically (called by `app.py`). | `SkillCreator`, `create_skill_programmatic()` |
| `app.py` | **Streamlit UI** — 3-tab interface: Chat, Create Skill, Skill Library. Created skills are live in Chat immediately (no restart). | Streamlit app |
| `test_agent.py` | **Test suite** — 3 modes covering registry, routing, execution, skill creation, and the end-to-end create-then-run flow. | CLI test runner |

---

## 🔄 How It Replicates Claude's Pipeline

Claude processes skills through a precise 5-step pipeline. Every step is mirrored here.

| Step | Claude's Mechanism | Our Implementation |
|------|-------------------|--------------------|
| **1. Skill Discovery** | All skill names + descriptions injected into system prompt via `<available_skills>` block | `get_registry()` + `format_skills_for_prompt()` inject the same block into Gemini's system prompt |
| **2. Skill Routing** | LLM matches user query against skill descriptions using trigger-pattern logic | Gemini reads the formatted skill block and selects the best skill by description keywords |
| **3. Skill Reading** | Claude calls `view /mnt/skills/.../SKILL.md` — reads the FULL workflow before acting | Agent calls `read_skill_instructions` tool which loads the full SKILL.md body |
| **4. Skill Execution** | Claude follows the SKILL.md workflow, calling `bash_tool` and `view` as instructed | LangGraph tool execution node runs `@tool` functions as directed by the SKILL.md workflow |
| **5. Response Generation** | Claude synthesizes tool outputs, formatted per SKILL.md output guidelines | Agent node formats the final response following the skill's documented output rules |

### New in this version: Skill Creation Pipeline

Claude Code's `skill-creator` SKILL.md describes an 8-step process for creating new skills. This is now fully replicated in `create_skill.py`:

| Step | Claude Code | Our Implementation |
|------|-------------|-------------------|
| **1. Capture Intent** | Interview to extract name, triggers, I/O, dependencies | `SkillCreator.build_brief_from_description()` — LLM extracts a structured JSON brief |
| **2. Write SKILL.md** | LLM generates frontmatter + full workflow body | `SkillCreator.generate_skill_md()` — Gemini generates complete SKILL.md |
| **3. Write script** | Bundled Python scripts for deterministic tasks | `SkillCreator.generate_script()` — Gemini writes a working implementation |
| **4. Write @tool stub** | N/A (Claude uses bash_tool directly) | `SkillCreator.generate_tool_stub()` — Gemini writes a LangChain `@tool` wrapper |
| **5. Write to disk** | Saves skill folder to `skills/` | `SkillCreator.write_to_disk()` — creates full folder tree |
| **6. Register tool** | N/A (Claude's tools are built-in) | `SkillCreator.register_tool()` — injects `@tool` stub into `skill_agent.py` |
| **7. Self-test routing** | Run test prompts, check triggers | `SkillCreator.test_routing()` — Gemini verifies the skill would be routed correctly |
| **8. Review & iterate** | User evaluates outputs, feedback loop | `SkillCreator.interactive_review()` — CLI menu for regeneration and editing |

---

## 🏗️ Integrated Application Flow

The three main files work together as a single connected pipeline:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          app.py  (Streamlit UI)                         │
│                                                                         │
│  Tab 1: 💬 Chat          Tab 2: 🛠️ Create Skill   Tab 3: 📦 Library   │
│  ─────────────────        ─────────────────────    ─────────────────    │
│  User sends query         User describes skill      Browse all skills    │
│        │                        │                   with SKILL.md        │
│        │                        │                   and script previews  │
│        ▼                        ▼                                        │
│  get_registry()          create_skill_programmatic()                     │
│  run_agent(query,              │                                         │
│    registry)                   ├── build_brief_from_description()        │
│        │                       ├── generate_skill_md()                   │
│        │                       ├── generate_script()                     │
│        │                       ├── generate_tool_stub()                  │
│        │                       ├── write_to_disk()                       │
│        │                       ├── register_tool()                       │
│        │                       ├── test_routing()                        │
│        │                       └── reload_tools()  ←── hot-reload        │
│        │                              │                                  │
│        │                    Skill immediately live                       │
│        │                    in Tab 1 Chat ─────────────────────►         │
└────────┼────────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────┐
│              skill_agent.py                    │
│                                                │
│  run_agent(query, registry)                    │
│       │                                        │
│       ▼                                        │
│  LangGraph StateGraph                          │
│       │                                        │
│  agent_node ──► execute_tools ──► agent_node   │
│       │              │                 │       │
│  (routing)    (tool calls)       (response)    │
└────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────┐
│           skills_registry.py                   │
│                                                │
│  get_registry()  ←── always reads fresh disk  │
│       │                                        │
│  format_skills_for_prompt()  → system prompt  │
│  get_skill_instructions()    → SKILL.md body  │
└────────────────────────────────────────────────┘
```

### Key integration points

**Fresh registry on every call** — `run_agent()` accepts an optional `registry` parameter. Both `app.py` and `test_agent.py` call `get_registry()` and pass it in, so a skill created 1 second ago is already visible to the next agent call.

**Hot-reload after creation** — after `create_skill_programmatic()` writes files and registers the `@tool` stub in `skill_agent.py`, `app.py` calls `reload_tools()`. This re-imports `skill_agent.py`, rebuilds `TOOLS`, `TOOL_MAP`, and `AGENT_GRAPH` in memory. The new skill becomes callable in the Chat tab with no Streamlit restart.

**Shared `SkillCreator` class** — `create_skill.py` exposes both a full `SkillCreator` class (every pipeline step as an individual method) and a `create_skill_programmatic()` convenience function. Both `app.py` and `test_agent.py` use the convenience function; power users can call individual methods directly.

---

## 🚀 Quick Start

### 1. Install dependencies

```bash
cd C:\Users\nayak\Documents\langchain_skills
pip install -r requirements.txt
```

### 2. Set your Google API Key

Get your key from: https://aistudio.google.com/

```bash
# Windows (Command Prompt)
set GEMINI_API_KEY=your_gemini_api_key_here

# Windows (PowerShell)
$env:GEMINI_API_KEY = "your_gemini_api_key_here"

# Linux / Mac
export GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Launch the Streamlit UI

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser. You will see three tabs.

### 4. Use the Chat tab

Paste a YouTube URL or type any request. The agent routes it to the matching skill, reads the SKILL.md, and executes the workflow automatically.

```
Get the transcript for: https://www.youtube.com/watch?v=dQw4w9WgXcQ
Summarise this video: https://youtu.be/dQw4w9WgXcQ
Get the timestamped transcript for video ID: dQw4w9WgXcQ
What skills do you have available?
```

### 5. Create a new skill from the UI

Switch to the **🛠️ Create Skill** tab, type a description, and click **Create Skill**. For example:

```
Extract and summarise text from PDF files
Scrape a webpage and return its main content
Translate any text to a target language
Count words, sentences, and paragraphs in text
```

The pipeline runs (~30–60 seconds), shows the generated SKILL.md, script, and `@tool` stub, then makes the skill immediately available in the Chat tab.

### 6. Or create a skill from the CLI

```bash
# Interactive (full interview + review loop)
python create_skill.py

# With description upfront
python create_skill.py --skill "extract text from PDF files"

# Skip routing self-test
python create_skill.py --skill "translate text to Spanish" --no-test
```

---

## 🧪 Running Tests

```bash
# Smoke test — registry loads + list skills (fastest)
python test_agent.py --quick

# Full built-in tests — transcript, summary, timestamps
python test_agent.py

# Test with a specific YouTube video
python test_agent.py --video "https://www.youtube.com/watch?v=YOUR_ID"

# Create a skill then immediately run it end-to-end
python test_agent.py --create --skill "count words and characters in any text"

# Everything — built-in tests + create+run flow
python test_agent.py --full --skill "translate text to Spanish"
```

### What `--create` tests (the integrated flow)

```
Phase A: Skill Creation
  ✔  SKILL.md written to disk
  ✔  Implementation script written
  ✔  @tool stub registered in skill_agent.py
  ✔  Routing self-test passes

Phase B: Hot-reload
  ✔  reload_tools() succeeds

Phase C: End-to-end run
  ✔  Test query routed to the new skill by the agent
  ✔  Non-empty response generated
```

---

## ➕ Adding Skills Manually

You can also add skills by hand following `skill_template.md`. The minimum is:

**1. Create the folder:**
```
skills/
└── my-skill/
    ├── SKILL.md
    └── scripts/
        └── my_skill.py
```

**2. Write `SKILL.md` with frontmatter:**
```markdown
---
name: my-skill
description: What this skill does and WHEN to trigger it. Include specific
             keywords so the LLM routes to it correctly.
---

# My Skill

## Workflow
### Step 1: ...
### Step 2: ...
```

**3. Add a `@tool` in `skill_agent.py`:**
```python
@tool
def my_skill_tool(input_value: str) -> str:
    """One-sentence description for the LLM routing system."""
    scripts_dir = Path(__file__).parent / "skills" / "my-skill" / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import my_skill
        result = my_skill.run_my_skill(input_value)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        if str(scripts_dir) in sys.path:
            sys.path.remove(str(scripts_dir))
```

**4. Add to `TOOLS_LIST`** in `skill_agent.py`.

The registry auto-discovers the `SKILL.md` on the next call to `get_registry()`.

See `skill_template.md` for the complete specification with all sections and a full worked example.

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Google Gemini 2.0 Flash (`gemini-3-flash-preview`) |
| Agent Orchestration | LangGraph `StateGraph` |
| LLM Framework | LangChain (`langchain-google-genai`) |
| Skill Creation | Gemini 2.0 Flash (generates SKILL.md + scripts) |
| Transcript Extraction | `youtube-transcript-api` |
| UI | Streamlit (3-tab layout) |
| Skill Format | Markdown with YAML frontmatter (identical to Claude) |
| Hot-reload | Python `importlib.reload()` |

---

## 📝 Key Design Decisions

**`get_registry()` instead of a singleton** — the old implementation loaded the registry once at module import. Now `get_registry()` always reads from disk. This means a skill created mid-session is immediately visible to the next agent call without any restart.

**`run_agent()` accepts a `registry` parameter** — callers pass `get_registry()` at call-time so the agent always routes against the freshest skill set. When `None` is passed, it loads fresh internally.

**`SkillCreator` class exposes individual steps** — each phase of the creation pipeline is a separate method. `create_skill_programmatic()` is the convenience wrapper for `app.py` and `test_agent.py`. Power users can call `generate_skill_md()`, `generate_script()`, `write_to_disk()`, etc. independently.

**`log` callback pattern** — `create_skill_programmatic()` and `run_full_pipeline()` accept a `log` callable (default: `print`). `app.py` passes a Streamlit `st.empty().markdown` writer so progress streams into the UI in real time. `test_agent.py` uses the default `print`.

**`reload_tools()` for zero-downtime updates** — after writing new files and registering a `@tool` stub, `reload_tools()` calls `importlib.reload()` on `skill_agent`, rebuilds `TOOLS`, `TOOL_MAP`, and `AGENT_GRAPH`. The Streamlit session continues uninterrupted.
