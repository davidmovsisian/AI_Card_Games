#!/usr/bin/env python3
"""
YouTube Technical Video Summarizer
Transforms a YouTube video transcript into a comprehensive, publication-ready guide.

Entry point: run_youtube_tech_summarizer(input_value: str) -> dict
  input_value: YouTube URL, video ID, or JSON string {"url": ..., "style": ...}

Output styles:
  "guide"     — step-by-step implementation guide with code (default)
  "blog"      — Medium-style blog post
  "summary"   — concise executive summary (500-800 words)
  "bullets"   — structured bullet-point notes
"""

import sys
import json
import os
import re
from pathlib import Path
from typing import Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Transcript extraction (reuses the youtube-transcript skill script)
# ─────────────────────────────────────────────────────────────────────────────

def _get_transcript(url_or_id: str) -> Dict:
    """Import and call the youtube-transcript script to get the transcript."""
    scripts_dir = Path(__file__).parent.parent.parent / "youtube-transcript" / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import extract_transcript as et
        import importlib
        importlib.reload(et)
        video_id = et.extract_video_id(url_or_id)
        if not video_id:
            return {"success": False, "error": f"Cannot extract video ID from: {url_or_id}"}
        result = et.get_transcript(video_id, ["en"])
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "error_type": type(e).__name__}
    finally:
        if str(scripts_dir) in sys.path:
            sys.path.remove(str(scripts_dir))


# ─────────────────────────────────────────────────────────────────────────────
# LLM summarization via Gemini
# ─────────────────────────────────────────────────────────────────────────────

def _llm_summarize(transcript: str, video_id: str, style: str, word_count: int) -> str:
    """Call Gemini to generate the summary/guide from the transcript."""
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        return _fallback_summary(transcript, style, word_count)

    # Estimate video length from word count to set output target
    if word_count < 1500:
        length_hint = "short video (under 10 min)"
        target_words = "600-900 words"
    elif word_count < 4000:
        length_hint = "medium video (10-30 min)"
        target_words = "900-1400 words"
    else:
        length_hint = "long video (30+ min)"
        target_words = "1400-2000 words"

    video_url = f"https://www.youtube.com/watch?v={video_id}"

    prompts = {
        "guide": f"""You are a technical writer. Transform this YouTube transcript into a comprehensive, 
publication-ready step-by-step guide of {target_words}.

Video URL: {video_url}
Video length hint: {length_hint}

Structure your guide with these sections (use only sections that are relevant):
1. **Title** — compelling, SEO-friendly
2. **Overview** — what this video covers and who it's for (2-3 sentences)
3. **Prerequisites** — tools, knowledge, setup needed
4. **Key Concepts** — core ideas explained clearly
5. **Step-by-Step Implementation** — numbered steps with:
   - What to do
   - Code snippets (original from video, then enhanced with comments/error handling)
   - Why it works
6. **Complete Working Code** — consolidated final version
7. **Common Issues & Fixes** — troubleshooting tips from the video
8. **Key Takeaways** — 5-7 bullet points
9. **Next Steps & Resources** — what to learn next

Rules:
- Use proper Markdown with headers, code blocks (```language), bold, bullets
- For every code snippet shown: present original first, then an improved version with comments
- Be specific — include actual names, versions, commands from the transcript
- Do NOT say "the video says" — write as a direct guide

TRANSCRIPT:
{transcript[:8000]}""",

        "blog": f"""You are a technical blogger. Write a compelling Medium-style blog post of {target_words}
based on this YouTube transcript. 

Video URL: {video_url}

Structure:
1. **Catchy Title**
2. **Hook** — why this matters (1 paragraph)
3. **Introduction** — context and problem being solved
4. **Main Content** — explain concepts with examples and code
5. **Code Examples** — practical, well-commented code blocks
6. **Real-World Applications** — where to use this
7. **Comparison / Advantages** — vs alternatives
8. **Conclusion** — summary and call to action
9. **References** — tools and links mentioned

Write in an engaging, direct style. Use Markdown formatting.

TRANSCRIPT:
{transcript[:8000]}""",

        "summary": f"""Summarize this YouTube video transcript in {target_words}.

Video URL: {video_url}

Format:
## Summary

[2-3 paragraph executive summary of the main content]

## Key Points
- [bullet 1]
- [bullet 2]
...

## Technologies / Tools Mentioned
- [list]

## Main Takeaway
[1-2 sentences]

TRANSCRIPT:
{transcript[:8000]}""",

        "bullets": f"""Extract structured notes from this YouTube transcript.

Video URL: {video_url}

Format:
## 📋 Video Notes: [Auto-detect title from content]

**Topics Covered:** [comma-separated]

### Main Points
- [point 1]
- [point 2]
...

### Code / Commands
```
[any code or commands mentioned]
```

### Tools & Technologies
- [tool]: [what it's used for]

### Action Items / Next Steps
- [ ] [actionable item]

### Quotes & Key Moments
> "[notable quote or key statement]"

TRANSCRIPT:
{transcript[:8000]}""",
    }

    prompt = prompts.get(style, prompts["guide"])

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage

        llm = ChatGoogleGenerativeAI(
            model="gemini-3-pro-preview",
            google_api_key=api_key,
            temperature=0.2,
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content

        # Handle list-of-dicts response format (Gemini v1.x)
        if isinstance(content, list):
            return "\n".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
        return str(content).strip()

    except Exception as e:
        return f"⚠️ LLM summarization failed: {e}\n\n{_fallback_summary(transcript, style, word_count)}"


def _fallback_summary(transcript: str, style: str, word_count: int) -> str:
    """Simple extractive summary when LLM is unavailable."""
    sentences = re.split(r'(?<=[.!?])\s+', transcript)
    # Take first 10% and last 5% of sentences as a rough summary
    n = max(10, len(sentences) // 10)
    selected = sentences[:n] + (["..."] if len(sentences) > n else []) + sentences[-max(3, n//2):]
    summary = " ".join(selected)
    return (
        f"## Video Summary (Extractive)\n\n"
        f"*Note: LLM unavailable — showing extractive summary.*\n\n"
        f"{summary[:3000]}\n\n"
        f"**Word count:** {word_count} words in transcript"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_youtube_tech_summarizer(input_value: str) -> Dict:
    """
    Main entry point for the youtube-tech-summarizer skill.

    Args:
        input_value: YouTube URL, video ID, or JSON:
                     {"url": "...", "style": "guide|blog|summary|bullets"}
    Returns:
        dict with keys: success, summary, video_id, word_count, style, extraction_method
    """
    # Parse input
    url_or_id = input_value.strip()
    style = "guide"

    if url_or_id.startswith("{"):
        try:
            data = json.loads(url_or_id)
            url_or_id = data.get("url", data.get("video_url", data.get("id", url_or_id)))
            style = data.get("style", "guide").lower()
        except Exception:
            pass

    valid_styles = ("guide", "blog", "summary", "bullets")
    if style not in valid_styles:
        style = "guide"

    # Step 1: Get transcript
    print(f"[YTSummarizer] Fetching transcript for: {url_or_id}")
    transcript_result = _get_transcript(url_or_id)

    if not transcript_result.get("success"):
        error = transcript_result.get("error", "Unknown error")
        return {
            "success": False,
            "error": error,
            "suggestion": (
                "If you see IpBlocked: install yt-dlp (pip install yt-dlp) "
                "or run the app locally rather than on a cloud server."
                if "ipblocked" in error.lower() or "ip" in error.lower() else
                "Check the video URL and ensure the video has captions enabled."
            ),
        }

    transcript = transcript_result.get("transcript", "")
    video_id   = transcript_result.get("video_id", "unknown")
    word_count = transcript_result.get("word_count", 0)
    method     = transcript_result.get("extraction_method", "unknown")

    if not transcript.strip():
        return {"success": False, "error": "Transcript is empty — video may have no captions."}

    print(f"[YTSummarizer] Transcript: {word_count} words via {method}. Generating {style}...")

    # Step 2: Generate summary/guide via LLM
    summary = _llm_summarize(transcript, video_id, style, word_count)

    return {
        "success":            True,
        "summary":            summary,
        "video_id":           video_id,
        "video_url":          f"https://www.youtube.com/watch?v={video_id}",
        "style":              style,
        "word_count":         word_count,
        "extraction_method":  method,
        "transcript_preview": transcript[:300] + "..." if len(transcript) > 300 else transcript,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python youtube_tech_summarizer.py <url_or_id> [guide|blog|summary|bullets]")
        sys.exit(1)

    url = sys.argv[1]
    sty = sys.argv[2] if len(sys.argv) > 2 else "guide"
    res = run_youtube_tech_summarizer(json.dumps({"url": url, "style": sty}))
    if res.get("success"):
        print(res["summary"])
    else:
        print(f"Error: {res['error']}")
        if res.get("suggestion"):
            print(f"Suggestion: {res['suggestion']}")
    sys.exit(0 if res.get("success") else 1)
