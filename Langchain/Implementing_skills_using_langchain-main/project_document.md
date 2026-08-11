# LangChain Skills Agent — New Joiner Onboarding Guide

> **Audience:** New developers joining the project  
> **Goal:** Understand the full architecture, every Python script, how the LLM works, what "Skills" are, and how to contribute  
> **Reading time:** ~30 minutes

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [Repository Structure](#3-repository-structure)
4. [Core Concepts — What is a Skill?](#4-core-concepts--what-is-a-skill)
5. [How the LLM Identifies and Executes a Skill](#5-how-the-llm-identifies-and-executes-a-skill)
6. [Script-by-Script Reference](#6-script-by-script-reference)
   - [app.py](#61-apppy--streamlit-ui-entry-point)
   - [skill_agent.py](#62-skill_agentpy--langgraph-agent-engine)
   - [skills_registry.py](#63-skills_registrypy--skill-discovery)
   - [create_skill.py](#64-create_skillpy--skill-factory)
   - [skill_api_keys.py](#65-skill_api_keyspy--api-key-management)
   - [test_agent.py](#66-test_agentpy--test-runner)
7. [The Skills Directory — Deep Dive](#7-the-skills-directory--deep-dive)
8. [Complete Application Flow — Step by Step](#8-complete-application-flow--step-by-step)
9. [Skill Creation Pipeline — Step by Step](#9-skill-creation-pipeline--step-by-step)
10. [Token Usage Tracking](#10-token-usage-tracking)
11. [API Key Management](#11-api-key-management)
12. [Current Skills Reference](#12-current-skills-reference)
13. [Setup & Running Locally](#13-setup--running-locally)
14. [How to Add a New Skill](#14-how-to-add-a-new-skill)
15. [Troubleshooting](#15-troubleshooting)
16. [Architecture Diagram](#16-architecture-diagram)

---

## 1. Project Overview

This is a **LangGraph-powered AI agent** that uses **Google Gemini** as its LLM and a plug-in system called **Skills** to extend its capabilities. The agent is served as a **Streamlit web application**.

The key innovation is the Skills system — a file-based plugin architecture where each "skill" is a self-contained folder containing:
- A `SKILL.md` file (human + LLM-readable instructions)
- A Python implementation script
- A `requirements.txt` for dependencies

The agent reads all SKILL.md files at startup, injects their descriptions into the LLM's system prompt, and uses the LLM's reasoning to automatically route user queries to the correct skill and execute the appropriate workflow.

**In plain English:** A user types "get me the transcript of this YouTube video" and the agent:
1. Recognises this matches the `youtube-transcript` skill description
2. Reads the full SKILL.md workflow for that skill
3. Calls the appropriate Python tool
4. Returns a clean Markdown response

---

## 2. Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| LLM | Google Gemini (`gemini-3-pro-preview`) | Reasoning, routing, response generation |
| Agent Orchestration | LangGraph `StateGraph` | Stateful multi-step agent execution |
| LLM Framework | LangChain (`langchain-google-genai`) | LLM abstraction, tool binding |
| UI | Streamlit | Web application interface |
| YouTube | `youtube-transcript-api` | Transcript extraction |
| Search | SerpAPI + DataForSEO | Business URL discovery |
| Web Scraping | `requests` + `BeautifulSoup` | Web page content extraction |
| Language | Python 3.11+ | All backend logic |

---

## 3. Repository Structure

```
langchain_skills/
│
├── app.py                    ← Streamlit UI entry point (run this)
├── skill_agent.py            ← LangGraph agent engine
├── skills_registry.py        ← Scans & loads all SKILL.md files
├── create_skill.py           ← 8-step skill creation pipeline
├── skill_api_keys.py         ← Maps skills → required API keys
├── test_agent.py             ← End-to-end test runner
├── requirements.txt          ← Python dependencies
│
└── skills/                   ← All skill plugins live here
    ├── youtube-transcript/
    │   ├── SKILL.md          ← LLM reads this for routing + workflow
    │   └── scripts/
    │       └── extract_transcript.py
    │
    ├── youtube-tech-summarizer/
    │   ├── SKILL.md
    │   └── scripts/
    │       └── youtube_tech_summarizer.py
    │
    ├── medium-blog-generator/
    │   ├── SKILL.md
    │   └── scripts/
    │       └── medium_blog_generator.py
    │
    ├── web-page-scraper/
    │   ├── SKILL.md
    │   └── scripts/
    │       └── web_page_scraper.py
    │
    └── business-url-hybrid-search/
        ├── SKILL.md
        ├── requirements.txt  ← google-search-results, requests
        └── scripts/
            └── business_url_hybrid_search.py
```

---

## 4. Core Concepts — What is a Skill?

A **Skill** is the fundamental unit of capability in this system. It is modelled after how Anthropic's Claude handles skills/tools — each skill is a self-describing, self-contained plugin.

### Anatomy of a Skill

Every skill is a folder under `skills/` with this structure:

```
skills/my-skill/
├── SKILL.md          ← The "brain" of the skill
├── requirements.txt  ← pip dependencies (optional)
└── scripts/
    └── my_skill.py   ← The actual implementation
```

### The SKILL.md File — The Most Important Concept

`SKILL.md` serves **two purposes simultaneously**:

1. **For the LLM (routing)** — The frontmatter `description` field is injected into the LLM's system prompt. The LLM reads this to decide whether a user's query should trigger this skill.

2. **For the LLM (execution)** — Once a skill is selected, the full body of `SKILL.md` is read by the agent and followed as step-by-step workflow instructions.

```markdown
---
name: youtube-transcript
description: Extract transcripts, captions, and metadata from YouTube videos
             using the youtube-transcript-api Python library. Use when users
             share YouTube links requesting summaries, guides, explanations,
             transcripts, or content about videos. Automatically extracts
             transcripts, analyzes content, and provides comprehensive video
             summaries.
---

# YouTube Transcript Extraction

## Workflow

### Step 1: Input Extraction
Identify the YouTube URL or video ID from the user's message.

### Step 2: Call Tool
Call `extract_youtube_transcript` with the URL.

### Step 3: Format Response
...
```

### Why This Design?

- **Zero code changes for new skills** — you add a folder and the agent instantly discovers it
- **Self-documenting** — SKILL.md is readable by humans and machines
- **LLM-driven routing** — no hardcoded if/elif routing logic; the LLM decides
- **Pluggable** — skills can be created manually or auto-generated by the `create_skill.py` pipeline

---

## 5. How the LLM Identifies and Executes a Skill

This is the most important concept to understand. Here is the exact sequence:

### Phase 1 — Startup (Registry Loading)

When the app starts, `skills_registry.py` scans every folder in `skills/`, reads each `SKILL.md`, and builds a Python dictionary:

```python
registry = {
    "youtube-transcript": {
        "name": "youtube-transcript",
        "description": "Extract transcripts from YouTube...",   # from frontmatter
        "full_instructions": "# YouTube Transcript...",         # full SKILL.md body
        "skill_md_path": Path("skills/youtube-transcript/SKILL.md"),
        "scripts_dir": Path("skills/youtube-transcript/scripts/"),
    },
    "medium-blog-generator": { ... },
    ...
}
```

### Phase 2 — System Prompt Injection

When a user sends a message, `skill_agent.py` builds a system prompt by formatting all skill descriptions:

```
You are a helpful assistant with access to specialised Skills.

## Available Skills

### Skill: youtube-transcript
**Description**: Extract transcripts, captions, and metadata from YouTube videos...

### Skill: medium-blog-generator
**Description**: Generate a complete, publication-ready Medium blog post...

### Skill: web-page-scraper
**Description**: Trigger when user asks to scrape, read, or extract text from a URL...
```

This entire block is sent to Gemini on every request.

### Phase 3 — LLM Routing (Skill Selection)

Gemini reads the user's query alongside all skill descriptions and reasons about which skill to use. It doesn't pick a skill explicitly — instead it decides which **tool** to call first.

The key tool for routing is `read_skill_instructions`. When the LLM decides skill X is relevant, its first tool call is:

```python
read_skill_instructions(skill_name="youtube-transcript")
```

This is the routing signal — `skill_agent.py` detects this call and records `selected_skill = "youtube-transcript"`.

### Phase 4 — Skill Instructions Loading

The `read_skill_instructions` tool reads the **full body** of the selected `SKILL.md` and returns it to the LLM as a `ToolMessage`. Now the LLM has the complete workflow instructions.

### Phase 5 — Skill Execution

With the workflow instructions in its context, the LLM follows the steps in `SKILL.md` and calls the actual implementation tools:

```python
# LLM follows SKILL.md step 2: "Call extract_youtube_transcript with the URL"
extract_youtube_transcript(video_url_or_id="https://youtube.com/watch?v=...")
```

The Python `@tool` function in `skill_agent.py` runs, which:
1. Adds the `scripts/` directory to `sys.path`
2. Imports the skill's Python module
3. Calls the `run_*` function
4. Returns JSON results

### Phase 6 — Response Generation

The LLM receives the tool result and synthesises a clean Markdown response following the output formatting rules in `SKILL.md`.

### Visualised Flow

```
User query
    │
    ▼
System prompt built
(all skill descriptions injected)
    │
    ▼
Gemini reasons: "which skill matches?"
    │
    ▼
Tool call: read_skill_instructions("youtube-transcript")
    │                      ↑
    │              ROUTING DETECTED HERE
    ▼
Full SKILL.md body loaded into context
    │
    ▼
Gemini follows SKILL.md workflow steps
    │
    ▼
Tool call: extract_youtube_transcript(url)
    │
    ▼
Python script runs → returns JSON
    │
    ▼
Gemini synthesises clean Markdown response
    │
    ▼
User sees formatted answer
```

### What Makes Routing Accurate?

The `description` field in `SKILL.md` frontmatter is the most critical text in the whole system. It is deliberately written to be:

- **Keyword-rich** — mentions all scenarios, phrasings, and contexts where the skill should trigger
- **Specific** — mentions exact trigger phrases like "scrape", "transcript", "blog post"
- **Slightly pushy** — overstates when to use the skill so the LLM errs on the side of using it

Poor description → wrong skill selected or no skill used  
Good description → reliable routing every time

---

## 6. Script-by-Script Reference

### 6.1 `app.py` — Streamlit UI Entry Point

**Run with:** `streamlit run app.py`

This is the web application. It renders a four-tab interface and orchestrates everything else.

#### Session State Keys

| Key | Type | Purpose |
|-----|------|---------|
| `chat_messages` | `list[dict]` | Full conversation history |
| `token_history` | `list[dict]` | Record of every LLM call with token counts |
| `skill_keys` | `dict` | User-entered API keys (survives reruns) |
| `_pending_rerun` | `bool` | Signals `st.rerun()` needed after token recording |
| `last_created_skill` | `str` | Name of the most recently created skill (for UI badges) |
| `creation_result` | `dict` | Full result from `create_skill_programmatic()` |

#### Key Design: `_pending_rerun` + `st.rerun()`

Streamlit renders the sidebar **before** the chat form submission block runs. This means token counts would always show stale values. The fix:

1. Chat runs → `_record_tokens()` appends to history and sets `_pending_rerun = True`
2. `st.rerun()` is called
3. On the next script pass, `_pending_rerun` is checked **at the very top** before any rendering
4. Sidebar now renders with the updated token history

#### Key Design: Skill API Keys Widget

The sidebar renders `st.text_input` widgets for each skill's API keys. Streamlit's rule is: **once a widget is rendered with a `key=`, subsequent `value=` arguments are ignored**. The fix:

1. Pre-seed `st.session_state["sk_ENVVAR"] = os.environ.get("ENVVAR", "")` **before** the widget renders (first time only — checked with `if key not in st.session_state`)
2. The widget's `key` directly maps to `st.session_state` — Streamlit writes the live value there automatically
3. After the widget renders, sync `st.session_state["sk_ENVVAR"] → os.environ["ENVVAR"]` on every pass

#### Four Tabs

| Tab | Purpose |
|-----|---------|
| 💬 Chat | Main agent interface — user asks questions, agent responds |
| 🛠️ Create Skill | Form to describe a new skill — triggers `create_skill_programmatic()` |
| 📦 Skill Library | Browse all loaded skills with their SKILL.md and scripts |
| 📊 Token Usage | Dashboard showing all LLM calls, token counts, charts, CSV export |

---

### 6.2 `skill_agent.py` — LangGraph Agent Engine

This is the brain of the application. It defines the LangGraph `StateGraph`, all built-in tools, and the public `run_agent()` function.

#### AgentState (TypedDict)

```python
class AgentState(TypedDict):
    messages:           list           # Full conversation (HumanMessage, AIMessage, ToolMessage)
    selected_skill:     Optional[str]  # Which skill was routed to (set when read_skill_instructions is called)
    skill_instructions: Optional[str]  # Full SKILL.md body after read_skill_instructions runs
    tool_results:       List[dict]     # Log of every tool call {tool, args, result_preview}
    final_response:     Optional[str]  # Unused (response is extracted from last message)
    token_usage:        Dict           # Cumulative {input_tokens, output_tokens, total_tokens}
```

#### The LangGraph — Two Nodes

```
┌─────────────┐
│  [agent]    │ ←─────────────────────────────────────┐
│  LLM call   │                                       │
│  Decides:   │                                       │
│  call tool? │──→ YES → ┌──────────────────┐        │
│  or done?   │          │ [execute_tools]   │        │
│             │          │ Runs each @tool   │────────┘
└─────────────┘          │ Returns results   │
       │                 └──────────────────┘
       │ NO (done)
       ▼
      END
```

The graph loops until the LLM produces a response with no tool calls.

#### Built-in Tools

| Tool Name | Function | Purpose |
|-----------|----------|---------|
| `read_skill_instructions` | Returns full SKILL.md body | **Routing signal** — must be called first |
| `list_available_skills` | Returns formatted skills list | Fast path — bypasses LLM round-trip |
| `extract_youtube_transcript` | Calls `extract_transcript.py` | Get YouTube transcript |
| `extract_youtube_transcript_with_timestamps` | Same with `[MM:SS]` markers | Timestamped version |
| `web_page_scraper_tool` | Calls `web_page_scraper.py` | Scrape/search web pages |
| `business_url_hybrid_search_tool` | Calls `business_url_hybrid_search.py` | Find business websites |

#### Dynamic Tool Registration

When `create_skill.py` generates a new `@tool` stub, it **injects it directly into `skill_agent.py`** just before `TOOLS_LIST = [`. After injection, `TOOLS_LIST` is updated to include the new tool function.

The `reload_tools()` function re-imports `skill_agent` module to pick up the injected stub without restarting the server.

#### `extract_text_content()` — Why It Exists

Gemini's LangChain integration sometimes returns content as:
- A plain `str`
- A `list[dict]` like `[{"type": "text", "text": "..."}]`
- An object with `.text` attribute
- A raw Python repr string with internal Gemini metadata

`extract_text_content()` handles all these cases and always returns a clean `str`. Without this, users would see raw Python objects in their responses.

#### Fast Path for "List Skills"

If the user query matches patterns like "what skills", "list skills", "what can you do", the agent **skips the LLM round-trip entirely** and calls `list_available_skills.invoke({})` directly. This is faster, cheaper (zero tokens), and more reliable.

---

### 6.3 `skills_registry.py` — Skill Discovery

**Responsibility:** Scan the `skills/` directory and build the routing registry.

#### `parse_frontmatter(content: str) → dict`

Parses the `---` delimited YAML-style frontmatter from a `SKILL.md` file. Returns a dict with `name`, `description`, and `_body` (everything after the second `---`).

```python
# Input SKILL.md:
# ---
# name: my-skill
# description: Does something useful
# ---
# # My Skill content...

# Output:
{
    "name": "my-skill",
    "description": "Does something useful",
    "_body": "# My Skill content..."
}
```

#### `load_skill_registry(silent=False) → dict`

Iterates `skills/` directory, parses each `SKILL.md`, and builds the registry dict. Always reads from disk — never cached — so newly created skills appear immediately.

#### `get_registry(silent=True) → dict`

The public API. Always returns a fresh registry. Called by `app.py`, `skill_agent.py`, and `create_skill.py`.

#### `format_skills_for_prompt(registry) → str`

Formats all skill descriptions into a Markdown block for injection into the LLM system prompt. This is exactly what Claude receives in its `<available_skills>` block.

---

### 6.4 `create_skill.py` — Skill Factory

This is an 8-step pipeline that uses Gemini to **auto-generate** a complete new skill from a plain English description.

**Two entry points:**

| Mode | Function | Usage |
|------|----------|-------|
| Programmatic (UI) | `create_skill_programmatic(description, log)` | Called by `app.py` |
| CLI (interactive) | `python create_skill.py --skill "..."` | Developer use |

#### The 8 Pipeline Steps

| Step | Method | What Gemini Does | Output |
|------|--------|-----------------|--------|
| 1 | `build_brief_from_description()` | Extracts structured JSON brief from free-text | `dict` with skill_name, libraries, etc. |
| 2 | `generate_skill_md()` | Writes complete SKILL.md with frontmatter + workflow | `str` (raw SKILL.md) |
| 3 | `generate_script()` | Writes working Python implementation | `str` (Python code) |
| 4 | `generate_tool_stub()` | Writes `@tool` LangChain wrapper | `str` (Python @tool function) |
| 5 | `write_to_disk()` | Creates `skills/<name>/` folder tree | `Path` to skill dir |
| 6 | `register_tool()` | Injects `@tool` stub into `skill_agent.py` | `bool` (success) |
| 7 | `test_routing()` | Asks Gemini if it would route test query to new skill | `(bool, str)` |
| 8 | `interactive_review()` | CLI-only: show/edit/regenerate previews | Updated SKILL.md + script |

#### Token Accumulation

`create_skill.py` maintains a module-level `_CREATE_TOKENS` dict that accumulates token usage across all 5-7 LLM calls in the pipeline. This is reset at the start of each `create_skill_programmatic()` call and attached to the result dict as `result["token_usage"]`.

#### How Tool Injection Works (`register_tool`)

```python
# skill_agent.py before injection:
TOOLS_LIST = [
    web_page_scraper_tool,
    ...
]

# After inject for "pdf-extractor" skill:
@tool
def pdf_extractor_tool(input_value: str) -> str:
    """Extracts text from PDF files."""
    ...

TOOLS_LIST = [
    pdf_extractor_tool,   # ← added here
    web_page_scraper_tool,
    ...
]
```

The injection uses regex to find `TOOLS_LIST = [` in `skill_agent.py` and inserts the stub just before it, then adds the function name as the first element of the list.

---

### 6.5 `skill_api_keys.py` — API Key Management

**Responsibility:** Central registry mapping skill names → required API keys.

#### Structure

```python
SKILL_API_KEYS = {
    "business-url-hybrid-search": [
        {
            "env_var":     "SERPAPI_API_KEY",     # os.environ key
            "label":       "SerpAPI Key",          # shown in sidebar
            "help":        "Required — https://...", # tooltip text
            "required":    True,                   # skill fails without this
            "is_password": True,                   # mask the input
        },
        {
            "env_var":     "DATAFORSEO_LOGIN",
            "required":    False,                  # optional enhancement
            ...
        },
    ]
}
```

#### How app.py Uses It

1. At sidebar render time, `app.py` calls `get_keys_for_skill(name)` for every loaded skill
2. For skills that have key requirements, it pre-seeds `st.session_state["sk_ENVVAR"]` on first render
3. `st.text_input` widgets are rendered with `key="sk_ENVVAR"`
4. After each widget renders, `st.session_state["sk_ENVVAR"]` is synced to `os.environ["ENVVAR"]`
5. When a skill script calls `os.environ.get("SERPAPI_API_KEY")`, it finds the user-entered value

**Adding keys for a new skill:** Add one entry to `SKILL_API_KEYS` in this file. The sidebar auto-detects it.

---

### 6.6 `test_agent.py` — Test Runner

**Run with:** `python test_agent.py [options]`

A standalone end-to-end test suite with three modes:

| Mode | Command | Tests |
|------|---------|-------|
| Default | `python test_agent.py` | Registry loads, list skills, YouTube transcript/summary/timestamps |
| Quick smoke | `python test_agent.py --quick` | Registry + list skills only |
| Create+Run | `python test_agent.py --create --skill "..."` | Create a skill then immediately run it through the agent |
| Full suite | `python test_agent.py --full --skill "..."` | All built-in tests + create+run |

#### `TestSuite` Class

Tracks pass/fail for each test case. Prints coloured output and a final summary. Returns exit code 0 (all pass) or 1 (any fail) — suitable for CI pipelines.

#### The `test_create_then_run` Function — Most Important Test

This is the integration test that validates the entire end-to-end flow:

1. Calls `create_skill_programmatic()` to auto-generate a skill
2. Verifies `SKILL.md` was written to disk
3. Verifies the script was written to `scripts/`
4. Verifies the `@tool` stub was injected into `skill_agent.py`
5. Calls `reload_tools()` to hot-reload without restart
6. Runs the suggested test query through `run_agent()`
7. Verifies the new skill was selected and a response was generated

---

## 7. The Skills Directory — Deep Dive

### `youtube-transcript`

**Purpose:** Extract and format transcripts from any YouTube video.

**Trigger keywords:** YouTube URL, video ID, transcript, captions, subtitles, video summary

**Key Script:** `extract_transcript.py`
- `extract_video_id(url)` — parses YouTube URL formats to extract the 11-char video ID
- `get_transcript(video_id, languages)` — uses `youtube-transcript-api` to fetch captions
- `get_transcript_with_timestamps(video_id)` — returns segments with `[MM:SS]` prefixes
- Handles auto-generated captions, manual captions, language fallback

**Built-in tools (registered in `skill_agent.py`):**
- `extract_youtube_transcript` — plain text transcript
- `extract_youtube_transcript_with_timestamps` — timestamped version

---

### `youtube-tech-summarizer`

**Purpose:** Transform technical YouTube videos into comprehensive 2000–6000 word step-by-step guides.

**Trigger keywords:** YouTube URL + technical topic, programming tutorial, AI/ML, software framework, code explanation

**Distinction from `youtube-transcript`:** This skill goes beyond raw transcript — it generates a structured blog-post-style guide with enhanced code examples, architecture explanations, and practical takeaways.

---

### `medium-blog-generator`

**Purpose:** Generate publication-ready Medium blog posts on any technical topic.

**Trigger keywords:** "write a blog", "create an article", "Medium post", "blog about", "write about [topic]"

**Output structure:** Always generates with these sections: Introduction, Challenges, Solution, Advantages, Architecture Flow, Technology Stack, Code Implementation, Future Scope, Conclusion, References.

**Key Script:** `medium_blog_generator.py`
- Takes a topic/description as input
- Makes a single Gemini call with a comprehensive prompt
- Returns structured Markdown ready to paste into Medium

---

### `web-page-scraper`

**Purpose:** Retrieve and parse content from web pages, either by direct URL or by searching for a topic.

**Trigger keywords:** scrape, read URL, extract text from website, what does website X say, summarise this link

**Two modes:**
- **Direct mode:** User provides a URL → scrape it directly
- **Discovery mode:** User provides a topic → DuckDuckGo search → scrape top result

**Key Script:** `web_page_scraper.py`
- Rotates User-Agent headers to avoid 403 errors
- Strips `<script>`, `<style>`, navigation elements
- Returns structured JSON: `{title, url, headers, main_text, word_count}`

---

### `business-url-hybrid-search`

**Purpose:** Find the official website URL for a business given its name and physical address.

**Trigger keywords:** find website for [business], official URL, business URL, locate website, [company] at [address]

**API Keys Required:**
- `SERPAPI_API_KEY` (required) — free tier at https://serpapi.com/manage-api-key
- `DATAFORSEO_LOGIN` + `DATAFORSEO_PASSWORD` (optional) — cross-reference for higher accuracy

**Search Strategy (priority order):**
1. SerpAPI Knowledge Graph (highest confidence — Google-verified)
2. SerpAPI organic results filtered for official domains
3. DataForSEO organic cross-reference (if credentials available)
4. Return all candidates with low-confidence flag

**Domain filtering:** Automatically excludes Yelp, TripAdvisor, Facebook, LinkedIn, etc. to find the direct business website.

**Key Script:** `business_url_hybrid_search.py`
- Uses `requests.get()` directly to SerpAPI (no SDK dependency issues)
- Full error reporting — never silently swallows exceptions
- Returns `{success, business_url, confidence, source, candidates_checked, errors}`

---

## 8. Complete Application Flow — Step by Step

### User Sends a Chat Message

```
1. User types in st.chat_input()
   │
2. app.py: GOOGLE_API_KEY present? → No → show error, stop
   │
3. app.py: append user message to chat_messages session state
   │
4. app.py: call run_agent(user_input, registry=get_registry())
   │
5. skill_agent.py: is this a "list skills" query?
   │── Yes → call list_available_skills() directly (no LLM) → return
   │── No  → continue to LangGraph
   │
6. LangGraph: build initial AgentState with HumanMessage
   │
7. [agent node]: build system prompt with all skill descriptions
   │            invoke Gemini with [SystemMessage + all messages]
   │
8. Gemini reasons and returns tool_calls
   │── No tool calls → go to END (pure knowledge answer)
   │── Has tool calls → go to [execute_tools node]
   │
9. [execute_tools node]: for each tool_call:
   │   - look up function in TOOL_MAP
   │   - call tool with args
   │   - if tool is read_skill_instructions → record selected_skill
   │   - return ToolMessage with result
   │
10. Back to [agent node]: Gemini reads tool results
    │   - if read_skill_instructions was called → now has full SKILL.md workflow
    │   - follows workflow steps → calls implementation tool(s)
    │
11. Implementation tool runs:
    │   - sys.path.insert to skills/X/scripts/
    │   - import skill_module
    │   - call run_X(input_value)
    │   - return json.dumps(result)
    │
12. Loop continues until no more tool_calls
    │
13. skill_agent.py: extract_text_content(last_message) → clean str response
    │
14. app.py: display response in chat
    │       show skill badge and tool badges
    │       show token count
    │
15. app.py: _record_tokens() → append to token_history
    │       st.rerun() → sidebar updates with new totals
```

---

## 9. Skill Creation Pipeline — Step by Step

### When User Clicks "🚀 Create" in the Create Skill Tab

```
User enters: "Find the sentiment of any text using TextBlob"
                │
         app.py calls: create_skill_programmatic(description)
                │
    ┌───────────────────────────────────────────────────────┐
    │  STEP 1: Build Brief                                  │
    │  Gemini extracts structured JSON:                     │
    │  {                                                    │
    │    "skill_name": "sentiment-analyzer",               │
    │    "one_liner": "Analyze sentiment of text",         │
    │    "python_libraries": ["textblob"],                  │
    │    "suggested_test_query": "What is the sentiment..." │
    │  }                                                    │
    └───────────────────────────────────────────────────────┘
                │
    ┌───────────────────────────────────────────────────────┐
    │  STEP 2: Generate SKILL.md                            │
    │  Gemini writes complete SKILL.md with:                │
    │  - frontmatter (name + description)                   │
    │  - Overview, Workflow steps, Error Handling, etc.     │
    └───────────────────────────────────────────────────────┘
                │
    ┌───────────────────────────────────────────────────────┐
    │  STEP 3: Generate Python script                       │
    │  Gemini writes sentiment_analyzer.py with:           │
    │  - run_sentiment_analyzer(input_value) → dict        │
    │  - Full error handling, docstrings, CLI entry point   │
    └───────────────────────────────────────────────────────┘
                │
    ┌───────────────────────────────────────────────────────┐
    │  STEP 4: Generate @tool stub                          │
    │  Gemini writes the LangChain @tool wrapper:           │
    │  @tool                                                │
    │  def sentiment_analyzer_tool(input_value: str):      │
    │      """Analyzes sentiment of text..."""              │
    │      scripts_dir = Path(...) / "scripts"             │
    │      sys.path.insert(0, str(scripts_dir))            │
    │      import sentiment_analyzer                        │
    │      return json.dumps(sentiment_analyzer.run_...)   │
    └───────────────────────────────────────────────────────┘
                │
    ┌───────────────────────────────────────────────────────┐
    │  STEP 5: Write to disk                                │
    │  Creates: skills/sentiment-analyzer/                  │
    │           skills/sentiment-analyzer/SKILL.md          │
    │           skills/sentiment-analyzer/scripts/          │
    │           skills/sentiment-analyzer/scripts/          │
    │               sentiment_analyzer.py                   │
    │           skills/sentiment-analyzer/requirements.txt  │
    └───────────────────────────────────────────────────────┘
                │
    ┌───────────────────────────────────────────────────────┐
    │  STEP 6: Register @tool in skill_agent.py             │
    │  Injects the @tool stub just before TOOLS_LIST = [   │
    │  Adds sentiment_analyzer_tool to TOOLS_LIST           │
    └───────────────────────────────────────────────────────┘
                │
    ┌───────────────────────────────────────────────────────┐
    │  STEP 7: Self-test routing                            │
    │  Asks Gemini: "Would you route                        │
    │  'What is the sentiment of this review...'            │
    │  to sentiment-analyzer?"                              │
    │  Returns: (True, "High confidence match")             │
    └───────────────────────────────────────────────────────┘
                │
       app.py: reload_tools()       ← hot-reload, no restart needed
       app.py: display result summary, show SKILL.md + script
       app.py: st.rerun()           ← sidebar shows new skill
```

---

## 10. Token Usage Tracking

Every LLM call in the system tracks token usage. The tracking is extracted from Gemini's `response_metadata`:

```python
# Gemini returns this in response_metadata:
{
    "usage_metadata": {
        "prompt_token_count":     1234,   # input tokens
        "candidates_token_count": 456,    # output tokens
        "total_token_count":      1690
    }
}
```

The `_extract_token_usage()` function in `skill_agent.py` and `_accumulate_tokens()` in `create_skill.py` both handle:
- The Gemini SDK key names (`prompt_token_count`, `candidates_token_count`)
- The LangChain standard key names (`input_tokens`, `output_tokens`)
- Fallback to `input + output` if total is missing

Token data flows to `app.py` → stored in `st.session_state["token_history"]` → displayed in:
- Sidebar mini-panel (live totals)
- Inline caption under each chat response
- Token Usage tab dashboard with charts and CSV export

---

## 11. API Key Management

### GOOGLE_API_KEY

Required for all LLM calls. Set in sidebar at top. Flows directly into `os.environ["GOOGLE_API_KEY"]` and is read by both `skill_agent.py` and `create_skill.py` when creating the Gemini LLM instance.

### Skill-Specific Keys

Managed by `skill_api_keys.py`. The sidebar renders key inputs automatically for any loaded skill that has registered requirements.

**Critical Streamlit behaviour:** `st.text_input`'s `value=` parameter is ignored after first render. The solution is to pre-seed `st.session_state["sk_ENVVAR"]` before the widget renders, then sync to `os.environ` after every render.

### Security Notes

- Keys are stored only in `st.session_state` — cleared when the browser tab closes
- Keys are never written to disk
- Keys are masked with `type="password"` in the UI

---

## 12. Current Skills Reference

| Skill Name | Trigger | API Keys Needed | Script |
|------------|---------|-----------------|--------|
| `youtube-transcript` | YouTube URL + "transcript" | None | `extract_transcript.py` |
| `youtube-tech-summarizer` | YouTube URL + technical topic | None | `youtube_tech_summarizer.py` |
| `medium-blog-generator` | "write a blog", "Medium post", "article" | None | `medium_blog_generator.py` |
| `web-page-scraper` | "scrape", "read URL", "extract from website" | None | `web_page_scraper.py` |
| `business-url-hybrid-search` | "find website for [business]", "official URL" | `SERPAPI_API_KEY` (required) | `business_url_hybrid_search.py` |

---

## 13. Setup & Running Locally

### Prerequisites

- Python 3.11+
- Google AI Studio API key (free): https://aistudio.google.com/
- Git

### Installation

```bash
# 1. Clone the repo
git clone <repo-url>
cd langchain_skills

# 2. Create virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. For business-url-hybrid-search skill only:
pip install google-search-results requests

# 5. Set your Google API key
# Windows:
set GOOGLE_API_KEY=your_key_here
# Mac/Linux:
export GOOGLE_API_KEY=your_key_here

# 6. Launch the app
streamlit run app.py
```

### Running Tests

```bash
# Quick smoke test (fast, just verifies setup)
python test_agent.py --quick

# Full built-in test suite
python test_agent.py

# Test with a specific video
python test_agent.py --video "https://youtu.be/VIDEO_ID"

# Test skill creation pipeline
python test_agent.py --create --skill "count words in any text"
```

### CLI Skill Creation (without UI)

```bash
# Interactive (asks you questions)
python create_skill.py

# Direct
python create_skill.py --skill "convert text to uppercase"
```

---

## 14. How to Add a New Skill

### Option A — Auto-generate (Recommended)

1. Open the app: `streamlit run app.py`
2. Go to **🛠️ Create Skill** tab
3. Describe the skill in plain English
4. Click **🚀 Create**
5. The skill is live immediately — test it in the **💬 Chat** tab

### Option B — Manual (Full Control)

1. Create the folder structure:
```bash
mkdir -p skills/my-new-skill/scripts
```

2. Write `skills/my-new-skill/SKILL.md`:
```markdown
---
name: my-new-skill
description: Trigger this when [specific conditions]. Use for [use cases].
             Mention all keywords that should route here: X, Y, Z.
---

# My New Skill

## Workflow
### Step 1: Validate input
...
### Step 2: Call tool
Call `my_new_skill_tool` with the input.
...
```

3. Write `skills/my-new-skill/scripts/my_new_skill.py`:
```python
def run_my_new_skill(input_value: str) -> dict:
    """Main entry point."""
    try:
        # Your implementation here
        return {"success": True, "result": "..."}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

4. Add the `@tool` stub to `skill_agent.py` just before `TOOLS_LIST = [`:
```python
@tool
def my_new_skill_tool(input_value: str) -> str:
    """One-sentence description for LLM routing."""
    import sys, json
    from pathlib import Path
    scripts_dir = Path(__file__).parent / "skills" / "my-new-skill" / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import my_new_skill
        return json.dumps(my_new_skill.run_my_new_skill(input_value))
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        if str(scripts_dir) in sys.path:
            sys.path.remove(str(scripts_dir))
```

5. Add `my_new_skill_tool` to `TOOLS_LIST`:
```python
TOOLS_LIST = [
    my_new_skill_tool,  # ← add here
    ...
]
```

6. If the skill needs API keys, add to `skill_api_keys.py`:
```python
SKILL_API_KEYS["my-new-skill"] = [
    {"env_var": "MY_API_KEY", "label": "My API Key",
     "help": "Get at https://...", "required": True, "is_password": True}
]
```

7. Restart the app — the new skill appears in the registry automatically.

---

## 15. Troubleshooting

### Sidebar tokens show 0

**Cause:** Streamlit renders the sidebar before the chat response handler runs.  
**Solution:** Already fixed with `st.rerun()` + `_pending_rerun` flag. If it regresses, ensure `_check_pending_rerun()` is called at the top of `app.py` before any `st.` rendering call.

### Skill API key not being picked up

**Cause:** Streamlit ignores `value=` on `st.text_input` after first render.  
**Solution:** Pre-seed `st.session_state["sk_ENVVAR"]` before the widget renders. The current code does this — look for the `if _wk not in st.session_state` block in `app.py`.

### Skill not being routed (wrong skill selected)

**Cause:** The `description` field in `SKILL.md` frontmatter isn't keyword-rich enough.  
**Solution:** Edit the `description` field in the skill's `SKILL.md` to include more specific phrases. The description should explicitly mention all the ways a user might ask for this capability.

### `candidates_checked: []` from business-url-hybrid-search

**Cause:** SerpAPI or DataForSEO returning empty results — usually because the API key is missing or invalid.  
**Solution:** Check that `SERPAPI_API_KEY` is set in the sidebar. The rewritten script returns detailed error information in the `errors` field of the result.

### New skill not showing in chat after creation

**Cause:** `reload_tools()` hot-reload failed, or registry wasn't refreshed.  
**Solution:** Restart Streamlit (`Ctrl+C` then `streamlit run app.py`). The skill will load from disk automatically.

### Gemini response shows raw Python objects

**Cause:** Content extraction failed — the LLM returned a list of content blocks instead of a string.  
**Solution:** `extract_text_content()` in `skill_agent.py` handles this. If it still occurs, check that the function is being called on `last_msg.content` (not the raw message object).

---

## 16. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        STREAMLIT APP (app.py)                        │
│                                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ 💬 Chat  │  │🛠️ Create Skill│  │📦 Library   │  │📊 Tokens   │ │
│  └────┬─────┘  └──────┬───────┘  └──────┬──────┘  └──────┬──────┘ │
│       │               │                  │                 │         │
│  ┌────▼───────────────▼──────────────────▼─────────────── ▼──────┐ │
│  │              Session State (Streamlit)                         │ │
│  │  chat_messages | token_history | skill_keys | _pending_rerun  │ │
│  └─────────────────────────┬──────────────────────────────────────┘ │
│                            │                                        │
└────────────────────────────┼────────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  run_agent()    │
                    │ skill_agent.py  │
                    └────────┬────────┘
                             │
              ┌──────────────▼─────────────────┐
              │     LangGraph StateGraph        │
              │                                 │
              │  ┌─────────┐   ┌─────────────┐ │
              │  │ [agent] │◄──│[exec_tools] │ │
              │  │ Gemini  │──►│ @tool fns   │ │
              │  └─────────┘   └──────┬──────┘ │
              └───────────────────────┼─────────┘
                                      │
                          ┌───────────▼────────────┐
                          │   Built-in Tools        │
                          │                         │
                          │  read_skill_instructions│◄── skills_registry.py
                          │  extract_yt_transcript  │◄── extract_transcript.py
                          │  web_page_scraper_tool  │◄── web_page_scraper.py
                          │  business_url_..._tool  │◄── business_url_....py
                          │  [dynamically added]    │◄── create_skill.py injects
                          └─────────────────────────┘
                                      │
                    ┌─────────────────▼──────────────────┐
                    │         skills/ directory           │
                    │                                     │
                    │  youtube-transcript/SKILL.md        │
                    │  youtube-tech-summarizer/SKILL.md   │
                    │  medium-blog-generator/SKILL.md     │
                    │  web-page-scraper/SKILL.md          │
                    │  business-url-hybrid-search/SKILL.md│
                    │  [new skills appear here]           │
                    └─────────────────────────────────────┘
```

---

## Quick Reference Card

| Task | Command / Location |
|------|-------------------|
| Start the app | `streamlit run app.py` |
| Run quick test | `python test_agent.py --quick` |
| Create a skill (CLI) | `python create_skill.py --skill "..."` |
| Create a skill (UI) | 🛠️ Create Skill tab |
| Add API keys | Sidebar → 🔑 Skill API Keys |
| Add skill API key config | `skill_api_keys.py` → `SKILL_API_KEYS` dict |
| Find skill routing logic | `skill_agent.py` → `_agent_node()` |
| Find skill discovery | `skills_registry.py` → `load_skill_registry()` |
| Find tool injection | `create_skill.py` → `register_tool()` |
| Debug a skill | Check `skills/<name>/scripts/<name>.py` directly |
| Test skill routing | `python test_agent.py --create --skill "..."` |

---

*Document generated: 2026 | Project: LangChain Skills Agent | Stack: Gemini + LangGraph + Streamlit*