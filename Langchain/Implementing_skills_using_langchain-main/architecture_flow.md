# Architecture & Workflow — LangChain Skills Agent

> Detailed breakdown of how the system is structured, how every component
> connects to the others, and how data flows through the full integrated pipeline
> including skill creation, hot-reload, chat execution, and testing.

---

## 1. System Overview

The application has four major subsystems that work together:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LangChain Skills Agent                             │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  app.py  (Streamlit — 3 tabs)                                       │   │
│  │                                                                     │   │
│  │  ┌──────────────┐  ┌──────────────────────┐  ┌───────────────────┐ │   │
│  │  │ 💬 Chat      │  │ 🛠️ Create Skill      │  │ 📦 Skill Library │ │   │
│  │  │              │  │                      │  │                   │ │   │
│  │  │ run_agent()  │  │ create_skill_        │  │ get_registry()    │ │   │
│  │  │ get_registry │  │ programmatic()       │  │ read SKILL.md     │ │   │
│  │  │              │  │ reload_tools()       │  │ read scripts      │ │   │
│  │  └──────┬───────┘  └──────────┬───────────┘  └───────────────────┘ │   │
│  └─────────┼────────────────────-┼─────────────────────────────────────┘   │
│            │                     │                                          │
│            ▼                     ▼                                          │
│  ┌─────────────────┐   ┌─────────────────────┐                             │
│  │  skill_agent.py │   │  create_skill.py     │                             │
│  │                 │   │                      │                             │
│  │  LangGraph      │   │  SkillCreator class  │                             │
│  │  StateGraph     │◄──│  8-step pipeline     │                             │
│  │  Gemini 2.0     │   │  (mirrors Claude     │                             │
│  │  Flash          │   │   Code skill-creator)│                             │
│  └────────┬────────┘   └──────────┬───────────┘                            │
│           │                       │                                         │
│           ▼                       ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  skills_registry.py                                                  │   │
│  │                                                                      │   │
│  │  get_registry()  ←── always reads fresh from disk                   │   │
│  │  format_skills_for_prompt()  parse_frontmatter()                     │   │
│  │  get_skill_instructions()                                            │   │
│  └──────────────────────────┬───────────────────────────────────────────┘  │
│                              │                                              │
│                              ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  skills/  (on-disk skill folders)                                     │  │
│  │                                                                       │  │
│  │  skills/youtube-transcript/SKILL.md                                   │  │
│  │  skills/youtube-transcript/scripts/extract_transcript.py              │  │
│  │  skills/youtube-tech-summarizer/SKILL.md                              │  │
│  │  skills/<new-skill>/SKILL.md          ← created by create_skill.py   │  │
│  │  skills/<new-skill>/scripts/<n>.py    ← generated by Gemini          │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer-by-Layer Breakdown

### Layer 1 — Skill Storage (`skills/`)

The lowest layer. Raw files that define what each skill can do. The agent never
reads these directly — it always goes through `skills_registry.py`.

```
skills/
├── youtube-transcript/
│   ├── SKILL.md
│   └── scripts/
│       └── extract_transcript.py
│
└── youtube-tech-summarizer/
    └── SKILL.md
```

Each `SKILL.md` has two distinct parts that serve different purposes:

```
┌───────────────────────────────────────────────────┐
│  ---                                              │
│  name: youtube-transcript                         │  ← ROUTING
│  description: Extract transcripts from YouTube   │    (injected into
│  ---                                              │     system prompt)
├───────────────────────────────────────────────────┤
│  # YouTube Transcript Extraction                  │
│  ## Overview                                      │
│  ## Automatic Processing                          │  ← EXECUTION
│  ## Workflow                                      │    (read by LLM via
│  ### Step 1: Extract Video ID                     │     read_skill_
│  ### Step 2: Ensure Dependencies                  │     instructions tool)
│  ### Step 3: Extract Transcript                   │
│  ## Error Handling                                │
│  ## Output Formatting                             │
└───────────────────────────────────────────────────┘
       ▲                          ▲
  used in Phase 2            used in Phase 3
  (routing)                  (execution)
```

---

### Layer 2 — Skills Registry (`skills_registry.py`)

Responsible for discovering skills and making them available to the rest of the system.

**Critical change from earlier versions:** the registry is no longer a module-level
singleton. `get_registry()` always reads from disk so newly created skills are
immediately visible without restarting the process.

```
get_registry() called
        │
        ▼
scan skills/ directory
        │
        ├── youtube-transcript/SKILL.md found
        │         │
        │         ├── parse_frontmatter()
        │         │     ├── name:        "youtube-transcript"
        │         │     ├── description: "Extract transcripts..."
        │         │     └── _body:       full SKILL.md content after second ---
        │         │
        │         └── store in registry dict
        │
        └── youtube-tech-summarizer/SKILL.md found
                  └── same → stored in registry dict

returns {
  "youtube-transcript": {
      "name":              "youtube-transcript",
      "description":       "Extract transcripts...",
      "full_instructions": "# YouTube Transcript Extraction\n## Workflow...",
      "skill_md_path":     Path("skills/youtube-transcript/SKILL.md"),
      "scripts_dir":       Path("skills/youtube-transcript/scripts"),
      "skill_dir":         Path("skills/youtube-transcript")
  },
  "youtube-tech-summarizer": { ... },
  "<any newly created skill>": { ... }   ← visible immediately
}
```

**Three functions power the rest of the system:**

| Function | What it returns | Used by |
|----------|-----------------|---------|
| `get_registry()` | Full dict of all loaded skills | `skill_agent.py`, `app.py`, `test_agent.py`, `create_skill.py` |
| `format_skills_for_prompt(registry)` | All names + descriptions as a prompt block | `build_system_prompt()` in `skill_agent.py` |
| `get_skill_instructions(registry, name)` | Full SKILL.md body for one skill | `read_skill_instructions` tool |

---

### Layer 3 — Agent Engine (`skill_agent.py`)

The core orchestration engine. Built as a LangGraph `StateGraph`.

#### Agent State

```python
class AgentState(TypedDict):
    messages:            Annotated[list, add_messages]
    # ↑ full conversation history — LangGraph merges automatically

    selected_skill:      Optional[str]
    # ↑ name of the skill chosen in the routing step

    skill_instructions:  Optional[str]
    # ↑ full SKILL.md body — populated when read_skill_instructions is called

    tool_results:        List[dict]
    # ↑ every tool call recorded with name, args, result preview

    final_response:      Optional[str]
    # ↑ the final synthesised answer
```

#### The Three Graph Nodes

```
┌─────────────────────────────────────────────────────────────────────┐
│  NODE: agent_node                                                   │
│                                                                     │
│  1. Build system prompt with ALL skill descriptions (fresh registry)│
│  2. Prepend SystemMessage to conversation history                   │
│  3. Call Gemini 2.0 Flash with full message history                 │
│  4. Gemini decides: call a tool OR produce final answer             │
│  5. Track selected_skill if read_skill_instructions was called      │
│  6. Return updated state                                            │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  NODE: tool_execution_node                                          │
│                                                                     │
│  1. Read tool_calls from the last AIMessage                         │
│  2. For each call: look up in TOOL_MAP, invoke with args            │
│  3. If read_skill_instructions → save result in skill_instructions  │
│  4. Append each result as ToolMessage to messages                   │
│  5. Append to tool_results list for traceability                    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  ROUTING: should_continue                                           │
│                                                                     │
│  last message has tool_calls?  →  "execute_tools"                  │
│  last message has no tool_calls → "end"                             │
└─────────────────────────────────────────────────────────────────────┘
```

#### Graph Edges

```
[START]
   │
   ▼
agent_node
   │
   ├── tool_calls present ──► execute_tools ──► agent_node  (loop)
   │
   └── no tool_calls ────────────────────────► [END]
```

This is a **ReAct loop** (Reason → Act → Observe → Reason) that runs until
Gemini decides it has enough information to produce a final answer.

#### Dynamic Registry Injection

```python
def run_agent(query, registry=None):
    if registry is None:
        registry = get_registry()      # always fresh if not supplied

    def agent_node_with_registry(state):
        return _agent_node(state, registry=registry)
    #             ↑
    #   registry captured in closure
    #   so every LLM call in this run uses the same snapshot

    # build fresh graph for this run
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node_with_registry)
    ...
```

Both `app.py` and `test_agent.py` call `get_registry()` immediately before
`run_agent()` and pass it in — so any skill created moments earlier is included.

#### Hot-Reload After Skill Creation

```python
def reload_tools():
    global TOOLS, TOOL_MAP, AGENT_GRAPH

    # Re-import this module to pick up newly appended @tool stubs
    mod = importlib.reload(sys.modules["skill_agent"])

    TOOLS    = mod.TOOLS_LIST        # updated list including new tool
    TOOL_MAP = {t.name: t for t in TOOLS}
    AGENT_GRAPH = _build_graph()     # rebuilt with new TOOLS

    # Streamlit session continues — no restart needed
```

---

### Layer 4 — Skill Creator (`create_skill.py`)

Mirrors Claude Code's `skill-creator` SKILL.md pipeline exactly.
Exposes a `SkillCreator` class where every step is a separate callable method,
plus a `create_skill_programmatic()` convenience function for non-interactive use.

```
SkillCreator methods
────────────────────
  build_brief_from_description(description)
  │   → sends description to Gemini
  │   → receives structured JSON brief
  │   → normalises skill_name, trigger_phrases, python_libraries
  │   → returns dict with all fields needed for generation
  │
  interview_user(description)            ← CLI only
  │   → calls build_brief_from_description()
  │   → prints inferred values, lets user correct each field
  │
  generate_skill_md(brief)
  │   → sends brief to Gemini with SKILL_MD_SYSTEM prompt
  │   → returns complete SKILL.md string (frontmatter + body)
  │
  generate_script(brief)
  │   → sends brief to Gemini with SCRIPT_SYSTEM prompt
  │   → returns complete Python implementation script
  │   → strips any accidental markdown fences
  │
  generate_tool_stub(brief)
  │   → sends brief + script path to Gemini with TOOL_STUB_SYSTEM
  │   → returns @tool function code ready to inject into skill_agent.py
  │
  write_to_disk(brief, skill_md, script_code)
  │   → creates skills/<n>/SKILL.md
  │   → creates skills/<n>/scripts/<n>.py
  │   → creates skills/<n>/requirements.txt   (if libraries present)
  │   → backs up existing skill folder if one exists
  │   → returns Path to the skill directory
  │
  register_tool(tool_stub, skill_name)
  │   → reads skill_agent.py
  │   → finds TOOLS_LIST = [ marker
  │   → inserts @tool stub just before it
  │   → adds function name to TOOLS_LIST
  │   → writes skill_agent.py back to disk
  │   → returns True if registered, False if already existed
  │
  test_routing(brief)
  │   → reloads registry (picks up new skill)
  │   → asks Gemini: "which skill matches this query?"
  │   → returns (passed: bool, reason: str)
  │
  interactive_review(brief, skill_dir, skill_md, script_code)  ← CLI only
  │   → shows 25-line previews of SKILL.md and script
  │   → menu: accept / redo SKILL.md / redo script / redo both / edit desc / quit
  │   → re-generates and saves as needed
  │   → returns final (skill_md, script_code)
  │
  run_full_pipeline(brief, interactive, log)
      → orchestrates all steps above in order
      → log() callback streams progress to caller
      → returns result dict with all artefacts + test outcomes
```

**`create_skill_programmatic(description, log)`** — the public entry point used by
`app.py` and `test_agent.py`. Calls `build_brief_from_description()` then
`run_full_pipeline()` with `interactive=False`. The `log` callback lets callers
stream progress however they want (`print`, Streamlit `st.markdown`, etc.).

---

### Layer 5 — Streamlit UI (`app.py`)

Three tabs that cover the full lifecycle: execute → create → browse.

#### Tab 1 — 💬 Chat

```
user types query
      │
      ▼
get_registry()          ← always fresh, includes any just-created skill
      │
      ▼
run_agent(query, registry=fresh_registry)
      │                         │
      │                   (inside skill_agent.py)
      │                   LangGraph pipeline runs:
      │                     agent_node → read_skill_instructions
      │                     → extract_youtube_transcript / other tools
      │                     → agent_node → [END]
      │
      ▼
display response
  + skill badge  (e.g. "Skill: youtube-transcript")
  + tools badge  (e.g. "extract_youtube_transcript")
```

#### Tab 2 — 🛠️ Create Skill

```
user types description
      │
      ▼
create_skill_programmatic(description, log=ui_log)
      │
      ├── build_brief_from_description()    → log("📋 Brief built")
      ├── generate_skill_md()               → log("⚙️ SKILL.md generated")
      ├── generate_script()                 → log("⚙️ Script generated")
      ├── generate_tool_stub()              → log("⚙️ Tool stub generated")
      ├── write_to_disk()                   → log("💾 Files written")
      ├── register_tool()                   → log("🔧 Tool registered")
      └── test_routing()                    → log("🧪 Routing test: PASS/FAIL")
      │
      ▼
reload_tools()                ← hot-reload skill_agent.py in memory
      │
      ▼
show result panel:
  - Generated SKILL.md   (code block)
  - Generated script     (code block)
  - @tool stub           (code block)
  - Files on disk        (list)
  - Routing test result  (success / warning)
```

#### Tab 3 — 📦 Skill Library

```
get_registry()
      │
      ▼
for each skill:
  ├── name + description
  ├── full SKILL.md content   (code block)
  ├── all scripts in scripts/ (code block each)
  └── "Test in chat" button   → pre-fills Chat tab input
```

---

### Layer 6 — Test Suite (`test_agent.py`)

Three test modes covering the full stack.

```
test modes
──────────
  --quick     Smoke test only (registry loads + list skills)
  default     Built-in skill tests (registry, list, transcript, summary, timestamps)
  --create    Create-then-run flow only (Phases A + B + C below)
  --full      Built-in tests + create-then-run flow

create-then-run flow (--create or --full)
─────────────────────────────────────────
  Phase A: Skill Creation
    create_skill_programmatic(description)
      ✔ SKILL.md written to skills/<n>/SKILL.md
      ✔ Script written to skills/<n>/scripts/<n>.py
      ✔ @tool stub registered in skill_agent.py
      ✔ Routing self-test: Gemini routes test query to new skill

  Phase B: Hot-reload
      reload_tools()
      ✔ TOOLS, TOOL_MAP, AGENT_GRAPH rebuilt in memory

  Phase C: End-to-end agent run
      get_registry()  → fresh registry includes new skill
      run_agent(suggested_test_query, registry=fresh)
      ✔ Agent routes to new skill
      ✔ Non-empty response returned

  TestSuite tracker records pass/fail for every sub-check
  sys.exit(0) if all passed, sys.exit(1) if any failed
```

---

## 3. Complete Request Lifecycle — Chat Flow

Full trace for: *"Get the transcript for https://youtu.be/abc123"*

```
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Registry Load                                                   │
│                                                                         │
│  app.py calls get_registry()                                            │
│  → scans skills/ directory from disk                                    │
│  → returns { "youtube-transcript": {...}, "youtube-tech-summarizer": {...} }│
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 2: System Prompt Construction                                      │
│                                                                         │
│  build_system_prompt(registry)                                          │
│  → format_skills_for_prompt(registry) produces:                         │
│                                                                         │
│    "## Available Skills                                                 │
│     ### Skill: youtube-transcript                                       │
│     **Description**: Extract transcripts, captions...                  │
│     ### Skill: youtube-tech-summarizer                                  │
│     **Description**: Generate comprehensive guides..."                  │
│                                                                         │
│  → injected into SystemMessage at the top of the context               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Skill Routing  (agent_node — Turn 1)                            │
│                                                                         │
│  Gemini receives:                                                       │
│    SystemMessage(<skills list + routing instructions>)                  │
│    HumanMessage("Get the transcript for https://youtu.be/abc123")       │
│                                                                         │
│  Gemini reasons:                                                        │
│    "User wants transcript → matches youtube-transcript description      │
│     Must call read_skill_instructions before acting"                    │
│                                                                         │
│  Returns AIMessage with tool_call:                                      │
│    { name: "read_skill_instructions",                                   │
│      args: { skill_name: "youtube-transcript" } }                      │
│                                                                         │
│  State update: selected_skill = "youtube-transcript"                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 4: Skill Reading  (tool_execution_node — Turn 1)                   │
│                                                                         │
│  Calls: read_skill_instructions("youtube-transcript")                   │
│  Internally: get_skill_instructions(registry, "youtube-transcript")     │
│  Returns: full SKILL.md body                                            │
│    "# YouTube Transcript Extraction                                     │
│     ## Automatic Processing                                             │
│     **CRITICAL**: When a user shares a YouTube URL...                   │
│     ## Workflow                                                         │
│     ### Step 1: Extract Video ID...                                     │
│     ### Step 3: Extract Transcript..."                                  │
│                                                                         │
│  Wrapped as ToolMessage → appended to messages                          │
│  State update: skill_instructions = <full SKILL.md body>                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 5: Skill Execution  (agent_node — Turn 2)                          │
│                                                                         │
│  Gemini now has in context:                                             │
│    - The SKILL.md workflow (from ToolMessage)                           │
│    - The YouTube URL (from HumanMessage)                                │
│                                                                         │
│  Follows SKILL.md Step 1 → extract video ID: "abc123"                  │
│  Follows SKILL.md Step 3 → call extract_youtube_transcript tool         │
│                                                                         │
│  Returns AIMessage with tool_call:                                      │
│    { name: "extract_youtube_transcript",                                │
│      args: { video_url_or_id: "abc123", languages: "en" } }            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 6: Tool Execution  (tool_execution_node — Turn 2)                  │
│                                                                         │
│  extract_youtube_transcript("abc123", "en")                             │
│    → sys.path.insert(0, "skills/youtube-transcript/scripts")            │
│    → import extract_transcript                                          │
│    → extract_video_id("abc123") → "abc123"                              │
│    → get_transcript("abc123", ["en"])                                   │
│        → YouTubeTranscriptApi().list("abc123")                          │
│        → find_transcript(["en"]) → fetch()                              │
│        → format with paragraph breaks                                   │
│    → returns { "success": true, "transcript": "...", "word_count": 1842 }│
│                                                                         │
│  JSON result wrapped as ToolMessage → appended to messages              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 7: Response Generation  (agent_node — Turn 3)                      │
│                                                                         │
│  Gemini has transcript data + SKILL.md output formatting rules:         │
│    "For Short Videos: present full transcript"                          │
│    "For Long Videos: structured summary with timestamps"                │
│                                                                         │
│  Gemini produces final formatted response                               │
│  No tool_calls in response → should_continue routes to END             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 8: Response Returned to app.py                                     │
│                                                                         │
│  run_agent() returns:                                                   │
│    {                                                                    │
│      "response":       "Here is the transcript for...",                 │
│      "selected_skill": "youtube-transcript",                            │
│      "tools_called":   ["read_skill_instructions",                      │
│                         "extract_youtube_transcript"]                   │
│    }                                                                    │
│                                                                         │
│  app.py displays response + skill badge + tools badge                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Complete Skill Creation Lifecycle

Full trace for typing *"Extract and summarise text from PDF files"* in the Create Skill tab:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Build Brief                                                     │
│                                                                         │
│  Gemini receives description + JSON schema                              │
│  Returns:                                                               │
│    {                                                                    │
│      "skill_name":          "pdf-extractor",                            │
│      "trigger_phrases":     ["extract pdf", "read pdf", "pdf text"],    │
│      "python_libraries":    ["pypdf2", "pdfplumber"],                   │
│      "suggested_test_query":"Extract text from this PDF: sample.pdf"   │
│      ...                                                                │
│    }                                                                    │
└─────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Generate SKILL.md                                               │
│                                                                         │
│  Gemini receives brief + SKILL_MD_SYSTEM prompt                         │
│  Returns full SKILL.md string:                                          │
│    ---                                                                  │
│    name: pdf-extractor                                                  │
│    description: Extract and summarise text from PDF files...            │
│    ---                                                                  │
│    # PDF Extractor                                                      │
│    ## Workflow                                                          │
│    ### Step 1: Validate PDF path ...                                    │
│    ...                                                                  │
└─────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Generate Script                                                 │
│                                                                         │
│  Gemini receives brief + SCRIPT_SYSTEM prompt                           │
│  Returns complete Python script:                                        │
│    import pdfplumber, sys, json                                         │
│    def run_pdf_extractor(file_path: str) -> dict:                       │
│        try:                                                             │
│            with pdfplumber.open(file_path) as pdf: ...                  │
│        except Exception as e:                                           │
│            return {"success": False, "error": str(e)}                  │
└─────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 4: Generate @tool Stub                                             │
│                                                                         │
│  Gemini receives brief + TOOL_STUB_SYSTEM prompt                        │
│  Returns @tool function:                                                │
│    @tool                                                                │
│    def pdf_extractor_tool(input_value: str) -> str:                    │
│        """Extract and summarise text from a PDF file path."""           │
│        scripts_dir = Path(__file__).parent / "skills" /                 │
│                      "pdf-extractor" / "scripts"                        │
│        sys.path.insert(0, str(scripts_dir))                             │
│        try:                                                             │
│            import pdf_extractor                                         │
│            result = pdf_extractor.run_pdf_extractor(input_value)        │
│            return json.dumps(result, ...)                               │
│        except Exception as e:                                           │
│            return json.dumps({"error": str(e)})                        │
│        finally:                                                         │
│            sys.path.remove(str(scripts_dir))                            │
└─────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 5: Write to Disk                                                   │
│                                                                         │
│  skills/pdf-extractor/SKILL.md            ← written                    │
│  skills/pdf-extractor/scripts/            ← created                    │
│  skills/pdf-extractor/scripts/pdf_extractor.py  ← written              │
│  skills/pdf-extractor/requirements.txt    ← written (pypdf2, pdfplumber)│
└─────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 6: Register @tool in skill_agent.py                                │
│                                                                         │
│  Read skill_agent.py                                                    │
│  Find:  TOOLS_LIST = [                                                  │
│  Insert @tool stub just before it                                       │
│  Change: TOOLS_LIST = [  →  TOOLS_LIST = [\n    pdf_extractor_tool,    │
│  Write skill_agent.py back to disk                                      │
└─────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 7: Routing Self-Test                                               │
│                                                                         │
│  get_registry()                 → picks up new skill from disk          │
│  format_skills_for_prompt()     → includes pdf-extractor description    │
│  Ask Gemini: "which skill for: 'Extract text from sample.pdf'?"         │
│  Gemini responds: { "selected_skill": "pdf-extractor", ... }           │
│  → test PASSED                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 8: Hot-Reload in app.py                                            │
│                                                                         │
│  reload_tools()                                                         │
│    → importlib.reload(skill_agent module)                               │
│    → TOOLS_LIST now includes pdf_extractor_tool                         │
│    → TOOL_MAP rebuilt with new tool                                     │
│    → AGENT_GRAPH recompiled with new TOOLS                              │
│                                                                         │
│  Next query in Chat tab can now call pdf_extractor_tool                 │
│  No Streamlit restart needed                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. State Transitions Through the Agent Graph

```
Initial State (after user sends query)
───────────────────────────────────────
  messages:           [HumanMessage("Get transcript for...")]
  selected_skill:     None
  skill_instructions: None
  tool_results:       []

After agent_node Turn 1
─────────────────────────
  messages:           [..., AIMessage(tool_calls=[read_skill_instructions])]
  selected_skill:     "youtube-transcript"   ← detected from tool call args
  skill_instructions: None

After tool_execution_node Turn 1
─────────────────────────────────
  messages:           [..., ToolMessage(content=<SKILL.md body>)]
  skill_instructions: "# YouTube Transcript Extraction\n## Workflow..."
  tool_results:       [{ tool: "read_skill_instructions", ... }]

After agent_node Turn 2
─────────────────────────
  messages:           [..., AIMessage(tool_calls=[extract_youtube_transcript])]

After tool_execution_node Turn 2
─────────────────────────────────
  messages:           [..., ToolMessage(content=<transcript JSON>)]
  tool_results:       [..., { tool: "extract_youtube_transcript", ... }]

After agent_node Turn 3
─────────────────────────
  messages:           [..., AIMessage(content="Here is the transcript...")]
                        ↑ no tool_calls → should_continue → END
```

---

## 6. Tool Architecture

```
TOOLS_LIST  (defined in skill_agent.py — new tools appended by create_skill.py)
────────────────────────────────────────────────────────────────────────────────
  extract_youtube_transcript
    → calls skills/youtube-transcript/scripts/extract_transcript.py::get_transcript()

  extract_youtube_transcript_with_timestamps
    → calls extract_transcript.py::get_transcript_with_timestamps()

  read_skill_instructions
    → calls skills_registry.get_skill_instructions(registry, skill_name)

  list_available_skills
    → calls get_registry() and formats result

  <new_skill>_tool            ← injected by create_skill.py::register_tool()
    → calls skills/<n>/scripts/<n>.py::run_<n>()

LLM Binding
────────────
  llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview")
  llm_with_tools = llm.bind_tools(TOOLS)
  ← Gemini sees the tool schema (name, description, arg types)
  ← Decides which tool to call based on tool docstrings + SKILL.md context
```

---

## 7. Claude vs. Our System — Full Comparison

| Claude | Our System |
|--------|-----------|
| `<available_skills>` block in system prompt | `format_skills_for_prompt()` injected into `SystemMessage` |
| `view /mnt/skills/.../SKILL.md` | `read_skill_instructions` tool → `get_skill_instructions()` |
| `bash_tool` runs Python scripts | `@tool` functions import and call Python scripts |
| Internal routing logic (LLM reads descriptions) | Gemini reads same formatted description block |
| Multi-turn tool use loop | LangGraph `StateGraph` ReAct loop |
| SKILL.md frontmatter parser | `parse_frontmatter()` in `skills_registry.py` |
| SKILL.md body passed to LLM | Passed as `ToolMessage` content in conversation history |
| Output format rules in SKILL.md | Gemini follows them in final `agent_node` response |
| `skill-creator` SKILL.md pipeline | `SkillCreator` class in `create_skill.py` |
| Skills auto-discovered from `/mnt/skills/` | `get_registry()` auto-discovers from `skills/` |
| Singleton registry at startup | `get_registry()` always reads fresh from disk |
| N/A (tools are built-in to Claude) | `register_tool()` injects `@tool` stub + `reload_tools()` hot-reloads |

---

## 8. File Dependency Map

```
app.py
  ├── skills_registry.get_registry()
  ├── skill_agent.run_agent(query, registry)
  │     ├── skills_registry.get_registry()
  │     ├── skills_registry.format_skills_for_prompt()
  │     ├── skills_registry.get_skill_instructions()
  │     ├── ChatGoogleGenerativeAI("gemini-3-flash-preview")
  │     └── Tools
  │           ├── extract_youtube_transcript
  │           │     └── skills/youtube-transcript/scripts/extract_transcript.py
  │           │           └── youtube-transcript-api (PyPI)
  │           ├── extract_youtube_transcript_with_timestamps
  │           │     └── (same script, different function)
  │           ├── read_skill_instructions
  │           │     └── skills_registry.get_skill_instructions()
  │           ├── list_available_skills
  │           │     └── skills_registry.get_registry()
  │           └── <new_skill>_tool              ← added by create_skill.py
  │                 └── skills/<n>/scripts/<n>.py
  │
  ├── create_skill.create_skill_programmatic(description, log)
  │     ├── SkillCreator.build_brief_from_description()
  │     │     └── ChatGoogleGenerativeAI (Gemini)
  │     ├── SkillCreator.generate_skill_md()
  │     │     └── ChatGoogleGenerativeAI (Gemini)
  │     ├── SkillCreator.generate_script()
  │     │     └── ChatGoogleGenerativeAI (Gemini)
  │     ├── SkillCreator.generate_tool_stub()
  │     │     └── ChatGoogleGenerativeAI (Gemini)
  │     ├── SkillCreator.write_to_disk()
  │     │     └── writes skills/<n>/ to filesystem
  │     ├── SkillCreator.register_tool()
  │     │     └── edits skill_agent.py on filesystem
  │     └── SkillCreator.test_routing()
  │           └── skills_registry.get_registry()
  │                 └── ChatGoogleGenerativeAI (Gemini)
  │
  └── skill_agent.reload_tools()
        └── importlib.reload(skill_agent)

test_agent.py
  ├── skills_registry.get_registry()
  ├── skill_agent.run_agent()
  ├── create_skill.create_skill_programmatic()
  └── skill_agent.reload_tools()
```

---

*Architecture document for LangChain Skills Agent — LangGraph + Gemini 2.0 Flash replica of Claude's skill execution pipeline, including integrated skill creation with hot-reload.*
