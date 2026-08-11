---
name: youtube-tech-summarizer
description: Generate a comprehensive guide, summary, or blog post FROM a YouTube video.
             Trigger when the user shares a YouTube URL and asks for:
             summarize, summary, explain, guide, blog post, write a post about, break down,
             key points, notes, what does this video cover, tech tutorial, step-by-step guide.
             Supports 4 output styles: guide (default), blog, summary, bullets.
             DO NOT use this for plain transcript extraction — use youtube-transcript for that.
---

# YouTube Technical Video Summarizer

Transform any YouTube video into a comprehensive guide, blog post, summary, or structured notes.

## Automatic Processing

When a user shares a YouTube URL and wants anything beyond raw text (summary, guide, blog, notes), use this skill immediately.

## Output Styles

| Style | When to use | Length |
|-------|-------------|--------|
| `guide` | Technical tutorials, how-to videos (default) | 900–2000 words |
| `blog` | Medium-style write-up | 900–2000 words |
| `summary` | Quick overview, "just the key points" | 600–900 words |
| `bullets` | Structured notes, checklists | Concise bullets |

## Workflow

### Step 1 — Parse user intent
- Extract the YouTube URL or video ID from the message
- Determine desired style from keywords:
  - "summarize / summary / key points" → `summary`
  - "blog post / write up / Medium" → `blog`
  - "notes / bullet points / outline" → `bullets`
  - "guide / tutorial / explain / how to / break down" → `guide` (default)

### Step 2 — Call the tool

Call `youtube_tech_summarizer_tool` with:
- Just the URL → uses default `guide` style
- Or JSON for explicit style: `{"url": "https://...", "style": "blog"}`

### Step 3 — Present the result

**On success:** Display `result["summary"]` directly — it is already formatted Markdown.

**On IpBlocked error:**
- Tell the user: "YouTube is blocking requests from this server's IP. Upload a `cookies.txt` file in the sidebar (▶ YouTube Access section) to fix this."
- Do NOT suggest alternatives that won't work either.

**On success with extraction_method = "ytdlp":** Note that yt-dlp was used as fallback.

## Output Format

Present the `summary` field from the tool result directly. Do not re-wrap it or add extra headers — the content is already structured.

Add a footer line:
```
---
*Source: [video_url] | Style: [style] | Transcript: [word_count] words*
```
