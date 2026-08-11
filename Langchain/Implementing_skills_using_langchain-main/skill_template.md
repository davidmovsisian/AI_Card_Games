# Skill Template Guide
### How to Structure a Skill so the LangChain Skills Agent can Discover and Execute it

---

## Overview

Every skill is a self-contained folder inside the `skills/` directory. The agent
discovers skills automatically at startup by scanning for `SKILL.md` files. As long
as your skill folder follows the structure described in this document, the agent will
load it, route queries to it, and execute it — no changes to any other file required.

---

## Required Folder Structure

```
skills/
└── your-skill-name/              ← folder name (use lowercase, hyphens only)
    ├── SKILL.md                  ← REQUIRED: metadata + workflow instructions
    └── scripts/                  ← RECOMMENDED: Python implementation scripts
        └── your_script.py        ← the actual logic your skill runs
```

### Rules
- The folder name should be lowercase and hyphen-separated (e.g. `web-scraper`, `pdf-reader`)
- `SKILL.md` is mandatory — without it the skill will not be discovered
- The `scripts/` folder is optional but strongly recommended to keep logic separate from instructions
- You can have multiple scripts inside `scripts/` if your skill needs them

---

## The SKILL.md File — Full Specification

`SKILL.md` has two parts separated by `---` markers:

1. **Frontmatter block** — machine-readable metadata used by the registry for routing
2. **Body** — human-readable workflow instructions read by the LLM before execution

```
---
name: your-skill-name
description: One or two sentence description of what this skill does and WHEN to use it.
             This is the most important field — the LLM uses this to decide whether to
             invoke this skill for a given user query. Be specific about trigger conditions.
---

# Your Skill Title

(Everything below the second --- is the body — the LLM reads this before executing)
```

---

## Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ Yes | Unique skill identifier. Must match the folder name exactly. Used as the key in the registry. |
| `description` | ✅ Yes | Plain-English description of what the skill does and when to trigger it. This is injected directly into the LLM system prompt. Write it as if you are describing a tool to the LLM. |

### Writing a Good Description

The description is the single most important field. The LLM uses it for routing — it
reads all skill descriptions and picks the best match for the user's query.

**Bad description (too vague):**
```
description: Helps with YouTube videos.
```

**Good description (specific trigger conditions):**
```
description: Extract transcripts, captions, and metadata from YouTube videos using
             the youtube-transcript-api library. Use when users share YouTube links
             requesting summaries, guides, transcripts, or content about videos.
             Works directly without any external server.
```

A good description should answer:
- What does this skill **do**?
- **When** should the LLM trigger it? (what keywords, URL patterns, or request types)
- What is the **output** (transcript, summary, guide, image, document)?
- Any **constraints** or special notes the LLM should know upfront?

---

## SKILL.md Body — Sections to Include

The body is the full instruction set the LLM reads before executing your skill.
Think of it as the LLM's operating manual for this skill. Include as much detail
as needed so the LLM can follow the workflow without guessing.

Below are all the recommended sections. Use the ones that apply to your skill.

---

### Section 1: Overview
Brief description of what the skill does and its core purpose.

```markdown
## Overview

This skill extracts full transcripts from YouTube videos and formats them
for summarization, citation, or analysis. It uses the youtube-transcript-api
library and requires no external servers.
```

---

### Section 2: Automatic Processing Instruction
Tell the LLM whether to start immediately or ask for confirmation first.

```markdown
## Automatic Processing

**CRITICAL**: When a user shares a [trigger — e.g. YouTube URL], immediately
begin processing without asking for confirmation. The workflow is fully automated.
```

---

### Section 3: Core Capabilities
Bullet list of what the skill can do. Helps the LLM understand the full scope.

```markdown
## Core Capabilities

- Extract full transcripts in 100+ languages
- Return timestamped segments with HH:MM:SS markers
- Auto-fallback to available language if requested one is missing
- Summarize content for short, medium, and long videos differently
```

---

### Section 4: Workflow (Step by Step)
This is the most critical section. Describe every step the LLM must follow
in order. Be explicit — the LLM will follow this exactly.

```markdown
## Workflow

### Step 1: Extract the Input
Describe what to extract from the user query (URL, ID, keyword, file, etc.)

### Step 2: Check Dependencies
List any libraries or tools that must be available before running.

```bash
pip install your-library
```

### Step 3: Run the Script
Show exactly how to call the tool or script.

```python
from skills.your_skill.scripts.your_script import your_function
result = your_function(input_value)
```

### Step 4: Process and Present
Describe how to handle the result and what format to present it in.
```

---

### Section 5: Usage Patterns
Show the LLM concrete examples of user inputs and the correct response workflow.
This is like few-shot examples specifically for skill execution.

```markdown
## Usage Patterns

### Pattern 1: Basic Request
**User**: "Do X with this input: [input]"
**Action**: Call tool_a(input), then format the result as Y.

### Pattern 2: Detailed Request
**User**: "Give me a detailed breakdown of [input]"
**Action**: Call tool_a(input), then tool_b(result), present as structured report.

### Pattern 3: Edge Case
**User**: "Do X but only for the part about [topic]"
**Action**: Call tool_a(input), filter by topic, present filtered result only.
```

---

### Section 6: Error Handling
Tell the LLM what errors can happen and exactly what to say or do about each one.

```markdown
## Error Handling

| Error | Cause | What to Tell the User |
|-------|-------|----------------------|
| `library not installed` | Dependency missing | "Run: pip install your-library" |
| `input not found` | Bad URL or ID | "Please check the input and try again" |
| `feature disabled` | Source restriction | "This content is not accessible" |
```

---

### Section 7: Output Formatting
Define exactly how the response should look based on different conditions
(e.g. short vs long input, summary vs full output, etc.)

```markdown
## Output Formatting

### For Short Input (< 5 minutes / < 1 page)
Present the full output directly with minimal structure.

### For Medium Input (5–20 minutes / 1–5 pages)
Provide a summary first, then offer the full output on request.

### For Long Input (> 20 minutes / > 5 pages)
Default to a structured breakdown with section headers and key points.
Offer the full output as a follow-up if needed.
```

---

### Section 8: Best Practices
Tips and rules for the LLM to follow when executing this skill.

```markdown
## Best Practices

1. Always check dependencies before running the script
2. Handle errors gracefully — never show raw stack traces to the user
3. Adapt response length to the size/complexity of the input
4. Include metadata (language, length, source) in the response header
5. Offer follow-up options at the end (e.g. "Want the full transcript?")
```

---

## The scripts/ Folder — Implementation Guidelines

The `scripts/` folder holds the actual Python logic your skill runs.
The LLM does not read these files — it only calls the tools registered in `skill_agent.py`.

### Script File Conventions

```python
#!/usr/bin/env python3
"""
your_script.py
Short description of what this script does.
"""

import sys
import json
from typing import Dict, Optional


def main_function(input_value: str) -> Dict:
    """
    Main entry point for this skill's logic.

    Args:
        input_value: description of what this receives

    Returns:
        A dictionary with at minimum:
        - "success": True/False
        - "result": the main output
        - "error": error message if success is False
    """
    try:
        # your logic here
        result = do_something(input_value)

        return {
            "success": True,
            "result": result,
            "metadata": {
                "input": input_value,
                "length": len(result),
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "input": input_value,
        }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python your_script.py <input_value>")
        sys.exit(1)

    output = main_function(sys.argv[1])
    print(json.dumps(output, indent=2))
```

### Return Value Rules

Every script function should return a dictionary. The agent expects:

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `success` | `bool` | ✅ Yes | Whether the operation completed without error |
| `result` or named key | `any` | ✅ Yes | The main output (transcript, summary, data, etc.) |
| `error` | `str` | If failed | Human-readable error message |
| `error_type` | `str` | If failed | Exception class name for debugging |
| `metadata` | `dict` | Recommended | Stats like length, language, source, word count |

---

## Registering Your Tool in skill_agent.py

After creating your skill folder, you must register a `@tool` function in `skill_agent.py`
so the LangGraph agent can call it.

```python
from langchain_core.tools import tool
import json
import sys
from pathlib import Path


@tool
def your_skill_tool(input_value: str) -> str:
    """
    One-sentence description of what this tool does.
    The LLM reads this docstring to understand when to call the tool.

    Args:
        input_value: Description of what this argument expects

    Returns:
        JSON string with the result from your script
    """
    scripts_dir = Path(__file__).parent / "skills" / "your-skill-name" / "scripts"
    sys.path.insert(0, str(scripts_dir))

    try:
        import your_script
        result = your_script.main_function(input_value)
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e), "error_type": type(e).__name__})

    finally:
        if str(scripts_dir) in sys.path:
            sys.path.remove(str(scripts_dir))
```

Then add it to the `TOOLS` list:

```python
TOOLS = [
    extract_youtube_transcript,
    extract_youtube_transcript_with_timestamps,
    list_available_skills,
    read_skill_instructions,
    your_skill_tool,          # ← add your tool here
]
```

That is all. The registry discovers the SKILL.md automatically. The tool is now
available to the LLM and will be invoked whenever the skill is routed to.

---

## Complete Minimal Example

Here is the smallest possible working skill — a "word counter" that counts words in any text.

### Folder structure
```
skills/
└── word-counter/
    ├── SKILL.md
    └── scripts/
        └── count_words.py
```

### skills/word-counter/SKILL.md
```markdown
---
name: word-counter
description: Count the number of words, characters, sentences, and paragraphs in any
             text the user provides. Use when the user asks "how many words", "word count",
             "character count", or wants text statistics for a passage or document.
---

# Word Counter

## Overview
Counts words, characters, sentences, and paragraphs in any given text.

## Automatic Processing
When the user provides text and asks for a word or character count, immediately
run the counter without asking for confirmation.

## Workflow

### Step 1: Extract the Text
Get the full text from the user's message.

### Step 2: Run the Counter
Call the word_counter tool with the extracted text.

### Step 3: Present Results
Return a clean summary showing all statistics.

## Output Format
Present the results as a simple stats block:

    Words:      1,234
    Characters: 6,789
    Sentences:  45
    Paragraphs: 12
```

### skills/word-counter/scripts/count_words.py
```python
import re
from typing import Dict

def count_text(text: str) -> Dict:
    words      = len(text.split())
    characters = len(text)
    sentences  = len(re.findall(r'[.!?]+', text))
    paragraphs = len([p for p in text.split('\n\n') if p.strip()])

    return {
        "success":    True,
        "words":      words,
        "characters": characters,
        "sentences":  sentences,
        "paragraphs": paragraphs,
    }
```

### Tool registration in skill_agent.py
```python
@tool
def count_words_in_text(text: str) -> str:
    """Count words, characters, sentences, and paragraphs in a block of text."""
    scripts_dir = Path(__file__).parent / "skills" / "word-counter" / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import count_words
        return json.dumps(count_words.count_text(text))
    finally:
        if str(scripts_dir) in sys.path:
            sys.path.remove(str(scripts_dir))
```

---

## Quick Checklist Before Publishing a Skill

```
[ ] Folder name is lowercase and hyphen-separated
[ ] SKILL.md exists in the skill root folder
[ ] Frontmatter has both `name` and `description` fields
[ ] name in frontmatter matches the folder name exactly
[ ] Description clearly states WHEN to trigger the skill
[ ] Workflow section covers every step the LLM must follow
[ ] Error handling section covers all expected failure modes
[ ] Output formatting section defines response structure
[ ] Script returns a dict with at minimum { success, result/error }
[ ] @tool function registered in skill_agent.py
[ ] Tool added to the TOOLS list in skill_agent.py
[ ] Tested with at least one real user query end-to-end
```
