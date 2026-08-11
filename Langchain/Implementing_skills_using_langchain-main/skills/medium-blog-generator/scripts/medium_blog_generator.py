"""
medium_blog_generator.py

Implementation script for the Medium Blog Generator skill.

Generates complete, publication-ready Medium blog posts with all 11 required sections:
  1. Introduction
  2. Challenges Faced Currently
  3. Solution
  4. Advantages
  5. Comparison with Old Approach
  6. Architecture Flow
  7. Technology Stack Used
  8. Code Implementation
  9. Future Scope
  10. Conclusion
  11. References

Usage (programmatic):
    from medium_blog_generator import run_medium_blog_generator
    result = run_medium_blog_generator(
        topic="LangGraph for AI Agents",
        audience="intermediate",
        code_language="python"
    )
    print(result["blog_post"])

Usage (CLI):
    python medium_blog_generator.py --topic "LangGraph" --audience intermediate
"""

import os
import sys
import json
import math
import argparse
import textwrap
from pathlib import Path
from datetime import datetime
from typing import Optional


# ── LangChain / Gemini ────────────────────────────────────────────────────────
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage, SystemMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

REQUIRED_SECTIONS = [
    "Introduction",
    "Challenges Faced Currently",
    "Solution",
    "Advantages",
    "Comparison with Old Approach",
    "Architecture Flow",
    "Technology Stack Used",
    "Code Implementation",
    "Future Scope",
    "Conclusion",
    "References",
]

AUDIENCE_LEVELS = ("beginner", "intermediate", "advanced")

WORDS_PER_MINUTE = 238  # average Medium reader speed


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

BLOG_SYSTEM_PROMPT = textwrap.dedent("""
You are an expert technical writer who specialises in high-quality Medium blog posts.
Your posts are clear, well-structured, technically accurate, and genuinely useful.

You always write posts with ALL of these 11 sections in this exact order:
  1. Introduction
  2. Challenges Faced Currently
  3. Solution
  4. Advantages
  5. Comparison with Old Approach
  6. Architecture Flow
  7. Technology Stack Used
  8. Code Implementation
  9. Future Scope
  10. Conclusion
  11. References

FORMATTING RULES:
- Start directly with: # [Blog Title]
- Then: > [one-sentence compelling subtitle]
- Then: ---
- Use ## for section headings, ### for sub-headings
- Number each section heading: ## 1. Introduction, ## 2. Challenges Faced Currently, etc.
- Wrap all code in fenced blocks with language tags: ```python, ```bash, ```yaml, etc.
- Comparison tables must use valid Markdown table syntax
- Architecture diagrams must use ASCII art inside a code block
- References must be numbered Markdown links: 1. [Title](https://url)

QUALITY RULES:
- Total word count: 2500–4000 words
- Every section must have substantive content — no single-sentence sections
- Code examples must be real and runnable — no placeholder comments
- Comparison table must have specific, factual differences (not "better" vs "worse")
- All reference URLs must be real, existing pages
- Use active voice, short paragraphs (3–4 sentences), and concrete examples
- Never use filler openers like "In today's fast-paced world"
- Match technical depth to the audience level provided

SECTION MINIMUMS:
- Introduction:               150 words
- Challenges Faced Currently: 200 words
- Solution:                   200 words
- Advantages:                 150 words
- Comparison with Old Approach: table + 150 words
- Architecture Flow:          200 words + ASCII diagram
- Technology Stack Used:      table + 100 words
- Code Implementation:        2-3 real code snippets + explanations, 300+ words
- Future Scope:               150 words
- Conclusion:                 100 words
- References:                 8-12 real links

After the blog post, append this metadata block exactly:
---
**Estimated read time**: X minutes
**Word count**: ~XXXX words
**Tags**: tag1, tag2, tag3, tag4, tag5
**Best posted**: Tuesday or Thursday, 8–10am EST
""")


# ══════════════════════════════════════════════════════════════════════════════
# LLM CALL
# ══════════════════════════════════════════════════════════════════════════════

def _extract_text(content) -> str:
    """
    Safely extract plain text from any Gemini/LangChain content format.
    Gemini 3 Pro Preview returns content as a list of dicts, not a plain string.
    Handles: str, list of {type, text} dicts, objects with .text attribute.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p).strip()
    if hasattr(content, "text"):
        return str(content.text).strip()
    return str(content).strip()


def _call_llm(system: str, user: str, temperature: float = 0.7) -> str:
    """Call Gemini 3 Pro Preview and return the text response."""
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "GOOGLE_API_KEY environment variable not set.\n"
            "  Windows : set GOOGLE_API_KEY=your_key\n"
            "  Linux   : export GOOGLE_API_KEY=your_key"
        )

    if not LANGCHAIN_AVAILABLE:
        raise ImportError(
            "langchain-google-genai not installed.\n"
            "  pip install langchain-google-genai"
        )

    llm = ChatGoogleGenerativeAI(
        model="gemini-3-pro-preview",
        google_api_key=api_key,
        temperature=temperature,
        max_output_tokens=8192,
    )

    response = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=user),
    ])
    return _extract_text(response.content)


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def validate_blog(blog_text: str) -> dict:
    """
    Check that all 11 required sections are present and the post meets
    minimum length requirements.

    Returns:
        {
            "valid":            bool,
            "missing_sections": list[str],
            "word_count":       int,
            "section_count":    int,
            "warnings":         list[str],
        }
    """
    missing  = []
    warnings = []

    for section in REQUIRED_SECTIONS:
        # Check for the numbered heading pattern, e.g. "## 2. Challenges"
        if section.lower() not in blog_text.lower():
            missing.append(section)

    word_count = len(blog_text.split())

    if word_count < 1500:
        warnings.append(f"Blog is short ({word_count} words). Target: 2500–4000.")

    if "```" not in blog_text:
        warnings.append("No code blocks found. Code Implementation section may be missing examples.")

    if "|" not in blog_text:
        warnings.append("No Markdown tables found. Comparison / Tech Stack tables may be missing.")

    return {
        "valid":            len(missing) == 0,
        "missing_sections": missing,
        "word_count":       word_count,
        "section_count":    sum(1 for s in REQUIRED_SECTIONS if s.lower() in blog_text.lower()),
        "warnings":         warnings,
    }


# ══════════════════════════════════════════════════════════════════════════════
# METADATA EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_metadata(blog_text: str) -> dict:
    """
    Extract title, word count, read time, and tags from the generated blog.
    """
    lines      = blog_text.splitlines()
    title      = ""
    subtitle   = ""
    word_count = len(blog_text.split())
    read_time  = max(1, math.ceil(word_count / WORDS_PER_MINUTE))

    for line in lines:
        line = line.strip()
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("> ") and not subtitle:
            subtitle = line[2:].strip()

    return {
        "title":      title,
        "subtitle":   subtitle,
        "word_count": word_count,
        "read_time":  read_time,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def run_medium_blog_generator(
    topic:         str,
    sections:      Optional[str] = None,
    audience:      str  = "intermediate",
    code_language: str  = "python",
    temperature:   float = 0.7,
) -> dict:
    """
    Generate a complete Medium blog post on the given topic.

    Args:
        topic:         The subject of the blog post, e.g. "LangGraph for AI Agents"
        sections:      Comma-separated list of section names (uses all 11 if None)
        audience:      One of: "beginner", "intermediate", "advanced"
        code_language: Primary programming language for code examples, e.g. "python"
        temperature:   LLM temperature (0.7 gives creative but coherent output)

    Returns:
        {
            "success":      bool,
            "blog_post":    str,   — full Markdown blog post
            "metadata":     dict,  — title, subtitle, word_count, read_time
            "validation":   dict,  — section check, warnings
            "topic":        str,
            "audience":     str,
            "generated_at": str,
        }
    """
    if not topic or not topic.strip():
        return {
            "success":   False,
            "error":     "Topic is required and cannot be empty.",
            "error_type": "ValueError",
        }

    topic         = topic.strip()
    audience      = audience.lower() if audience.lower() in AUDIENCE_LEVELS else "intermediate"
    sections_list = REQUIRED_SECTIONS  # always use all 11

    # Build the user prompt
    user_prompt = textwrap.dedent(f"""
        Write a complete Medium blog post on this topic:

        Topic:            {topic}
        Target audience:  {audience}
        Code language:    {code_language}
        Required sections (in this exact order):
          {chr(10).join(f'  {i+1}. {s}' for i, s in enumerate(sections_list))}

        Produce the full blog post now. Include all 11 sections.
        Start directly with # [Your Title] — no preamble.
    """)

    try:
        print(f"[MediumBlogGenerator] Generating blog on: '{topic}' (audience={audience})")
        blog_text = _call_llm(BLOG_SYSTEM_PROMPT, user_prompt, temperature=temperature)

        validation = validate_blog(blog_text)
        metadata   = extract_metadata(blog_text)

        if not validation["valid"]:
            print(f"[MediumBlogGenerator] WARNING: Missing sections: {validation['missing_sections']}")

        return {
            "success":      True,
            "blog_post":    blog_text,
            "metadata":     metadata,
            "validation":   validation,
            "topic":        topic,
            "audience":     audience,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    except EnvironmentError as e:
        return {"success": False, "error": str(e), "error_type": "EnvironmentError"}
    except ImportError as e:
        return {"success": False, "error": str(e), "error_type": "ImportError"}
    except Exception as e:
        return {"success": False, "error": str(e), "error_type": type(e).__name__}


# ══════════════════════════════════════════════════════════════════════════════
# SAVE TO FILE
# ══════════════════════════════════════════════════════════════════════════════

def save_blog_to_file(blog_text: str, topic: str, output_dir: str = ".") -> str:
    """
    Save the generated blog post to a Markdown file.
    Filename is derived from the topic and current timestamp.

    Returns the full file path as a string.
    """
    slug      = topic.lower().replace(" ", "-")
    slug      = "".join(c if c.isalnum() or c == "-" else "" for c in slug)[:60]
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    filename  = f"blog-{slug}-{timestamp}.md"
    filepath  = Path(output_dir) / filename

    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(blog_text, encoding="utf-8")
    print(f"[MediumBlogGenerator] Blog saved to: {filepath}")
    return str(filepath)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Generate a complete Medium blog post on any technical topic",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python medium_blog_generator.py --topic "LangGraph for AI Agents"
          python medium_blog_generator.py --topic "FastAPI vs Flask" --audience beginner
          python medium_blog_generator.py --topic "Kubernetes" --lang yaml --save ./output
        """),
    )
    parser.add_argument("--topic",    "-t", required=True, help="Blog topic")
    parser.add_argument("--audience", "-a", default="intermediate",
                        choices=AUDIENCE_LEVELS, help="Target audience level")
    parser.add_argument("--lang",     "-l", default="python",
                        help="Primary code language (e.g. python, javascript, yaml)")
    parser.add_argument("--save",     "-s", default=None,
                        help="Directory to save the .md file (optional)")
    parser.add_argument("--temp",     type=float, default=0.7,
                        help="LLM temperature 0.0–1.0 (default: 0.7)")
    args = parser.parse_args()

    result = run_medium_blog_generator(
        topic=args.topic,
        audience=args.audience,
        code_language=args.lang,
        temperature=args.temp,
    )

    if not result["success"]:
        print(f"\nERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "="*70)
    print(result["blog_post"])
    print("="*70)

    meta = result["metadata"]
    val  = result["validation"]
    print(f"\nMetadata:")
    print(f"  Title:         {meta['title']}")
    print(f"  Word count:    {meta['word_count']}")
    print(f"  Read time:     {meta['read_time']} min")
    print(f"  Sections:      {val['section_count']}/11")
    print(f"  Valid:         {'YES' if val['valid'] else 'NO — missing: ' + str(val['missing_sections'])}")
    if val["warnings"]:
        print(f"  Warnings:      {'; '.join(val['warnings'])}")

    if args.save:
        save_blog_to_file(result["blog_post"], args.topic, args.save)


if __name__ == "__main__":
    main()
