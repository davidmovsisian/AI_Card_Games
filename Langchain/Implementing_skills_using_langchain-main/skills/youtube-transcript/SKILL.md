---
name: youtube-transcript
description: Extract the plain transcript or timestamped captions from any YouTube video.
             Trigger when the user shares a YouTube URL or video ID and asks for:
             transcript, captions, subtitles, timestamped transcript, full text of a video,
             what was said in a video, or copy/paste-able text from a video.
             DO NOT use this for summaries, guides, or blog posts — use youtube-tech-summarizer for those.
---

# YouTube Transcript Extraction

## Automatic Processing

When a user shares a YouTube URL or video ID and wants the raw transcript or captions, immediately extract it. Do NOT ask for confirmation.

## Accepted Input Formats

- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/shorts/VIDEO_ID`
- Bare 11-character video ID: `dQw4w9WgXcQ`

## Workflow

### Step 1 — Determine what the user wants
- **Plain transcript** → call `extract_youtube_transcript`
- **Timestamped transcript** → call `extract_youtube_transcript_with_timestamps`
- If unclear, default to `extract_youtube_transcript`

### Step 2 — Call the tool
Call the appropriate tool with the full URL or video ID exactly as provided.

### Step 3 — Present the result

**On success:**
- Show the transcript clearly formatted
- Include metadata: language, word count, extraction method
- If truncated, note that clearly

**On IpBlocked error:**
- Tell the user: "YouTube is blocking requests from this server's IP. Upload a `cookies.txt` file in the sidebar (▶ YouTube Access) to fix this."

**On "Transcripts disabled":**
- Tell the user the video creator has disabled captions

## Output Format

```
## 📝 Transcript — [Video ID]

**Language:** [language]  **Words:** [count]  **Method:** [api/ytdlp]

---

[full transcript text]
```

For timestamped:
```
[00:00] First line of transcript
[00:05] Next line...
```
