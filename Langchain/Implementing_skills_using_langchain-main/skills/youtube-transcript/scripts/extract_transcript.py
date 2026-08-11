#!/usr/bin/env python3
"""
YouTube Transcript Extractor
=============================
Extraction strategies tried in order:

  1. yt-dlp with cookies  — works on cloud IPs when cookies.txt is uploaded
  2. yt-dlp without cookies — works on non-blocked IPs
  3. youtube-transcript-api — fast fallback for non-blocked environments

NOTE: youtube-transcript-api v1.x has cookie auth DISABLED by the maintainer
("Cookie auth has been temporarily disabled, as it is not working properly
with YouTube's most recent changes.") — do NOT rely on it for IpBlocked fixes.
yt-dlp with a valid cookies.txt is the only reliable cloud solution.

Compatibility: youtube-transcript-api v0.x (dict) AND v1.x (FetchedTranscriptSnippet)
"""

import sys
import json
import re
import os
import tempfile
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# URL / ID helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract 11-char video ID from any YouTube URL format or bare ID."""
    url_or_id = url_or_id.strip()
    if re.match(r'^[A-Za-z0-9_-]{11}$', url_or_id):
        return url_or_id
    patterns = [
        r'(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})',
        r'youtube\.com/watch\?.*v=([A-Za-z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url_or_id)
        if m:
            return m.group(1)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Segment normalisation (v0.x dict vs v1.x object)
# ─────────────────────────────────────────────────────────────────────────────

def _seg(segment) -> Dict:
    """Return plain dict from either v0.x dict or v1.x FetchedTranscriptSnippet."""
    if isinstance(segment, dict):
        return {
            "text":     segment.get("text", ""),
            "start":    segment.get("start", 0.0),
            "duration": segment.get("duration", 0.0),
        }
    return {
        "text":     getattr(segment, "text", ""),
        "start":    getattr(segment, "start", 0.0),
        "duration": getattr(segment, "duration", 0.0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 1 — yt-dlp (PRIMARY for cloud; supports cookies properly)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_via_ytdlp(video_id: str, languages: List[str], cookies_file: str = "") -> Dict:
    """
    Download subtitles via yt-dlp.
    When cookies_file is provided, uses cookie-based auth to bypass IpBlocked.
    yt-dlp cookie support is fully functional unlike youtube-transcript-api v1.x
    which has cookie auth DISABLED.
    """
    try:
        import yt_dlp
    except ImportError:
        return {
            "error": "yt-dlp not installed — run: pip install yt-dlp",
            "_strategy": "ytdlp",
        }

    url = f"https://www.youtube.com/watch?v={video_id}"
    lang_codes = list(dict.fromkeys(languages + ["en"]))  # deduplicate, keep order

    with tempfile.TemporaryDirectory() as tmpdir:
        for lang in lang_codes:
            out_template = os.path.join(tmpdir, "sub")
            ydl_opts = {
                "skip_download":    True,
                "writesubtitles":   True,
                "writeautomaticsub": True,
                "subtitleslangs":   [lang],
                "subtitlesformat":  "vtt",
                "outtmpl":          out_template,
                "quiet":            True,
                "no_warnings":      True,
            }
            if cookies_file and os.path.exists(cookies_file):
                ydl_opts["cookiefile"] = cookies_file
                print(f"[Transcript] yt-dlp using cookies from {cookies_file}")
            else:
                print(f"[Transcript] yt-dlp running without cookies")

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                vtt_files = [f for f in os.listdir(tmpdir) if f.endswith(".vtt")]
                if not vtt_files:
                    print(f"[Transcript] yt-dlp: no VTT found for lang={lang}")
                    continue

                vtt_path = os.path.join(tmpdir, vtt_files[0])
                segments = _parse_vtt(vtt_path)
                if segments:
                    strategy = "ytdlp+cookies" if cookies_file else "ytdlp"
                    print(f"[Transcript] yt-dlp succeeded: {len(segments)} segments, lang={lang}")
                    return {
                        "success":    True,
                        "_strategy":  strategy,
                        "video_id":   video_id,
                        "language":   lang,
                        "segments":   segments,
                        "available_languages": [],
                    }
            except Exception as e:
                last_err = str(e)
                print(f"[Transcript] yt-dlp error for lang={lang}: {last_err[:120]}")
                continue

    last_err = locals().get("last_err", "No subtitles found")
    return {
        "error":     last_err,
        "_strategy": "ytdlp",
        "video_id":  video_id,
    }


def _parse_vtt(vtt_path: str) -> List[Dict]:
    """Parse a WebVTT subtitle file into segment dicts, deduplicating overlapping cues."""
    segments   = []
    seen_texts = set()

    with open(vtt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n\n+", content.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        ts_line, text_lines = None, []
        for i, line in enumerate(lines):
            if "-->" in line:
                ts_line    = line
                text_lines = lines[i + 1:]
                break
        if not ts_line or not text_lines:
            continue

        # Parse start time — supports HH:MM:SS.mmm and MM:SS.mmm
        m = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)", ts_line)
        if m:
            h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        else:
            m = re.match(r"(\d+):(\d+)[.,](\d+)", ts_line)
            if not m:
                continue
            h, mi, s, ms = 0, int(m.group(1)), int(m.group(2)), int(m.group(3))
        start_sec = h * 3600 + mi * 60 + s + ms / 1000

        # Strip VTT inline tags: <00:00:01.000>, <c>, </c>, etc.
        raw  = " ".join(text_lines)
        clean = re.sub(r"<[^>]+>", "", raw).strip()
        clean = re.sub(r"\s+", " ", clean)

        if not clean or clean in seen_texts:
            continue
        seen_texts.add(clean)
        segments.append({"text": clean, "start": start_sec, "duration": 0.0})

    return segments


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 2 — youtube-transcript-api (fast, works on non-blocked IPs)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_via_api(video_id: str, languages: List[str]) -> Dict:
    """
    Attempt extraction using youtube-transcript-api.
    NOTE: Cookie auth is disabled in v1.x — this won't bypass IpBlocked.
    Use yt-dlp+cookies for cloud environments.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {"error": "youtube-transcript-api not installed", "_strategy": "api"}

    try:
        api   = YouTubeTranscriptApi()
        tlist = api.list(video_id)

        transcript = None
        found_lang = None
        for lang in languages:
            try:
                transcript = tlist.find_transcript([lang])
                found_lang = lang
                break
            except Exception:
                continue

        if transcript is None:
            try:
                transcript = tlist.find_generated_transcript(["en"])
                found_lang = "en (auto-generated)"
            except Exception:
                available = list(tlist)
                if available:
                    transcript = available[0]
                    found_lang = transcript.language_code
                else:
                    return {
                        "error":     "No transcripts available",
                        "video_id":  video_id,
                        "_strategy": "api",
                    }

        raw      = transcript.fetch()
        segments = [_seg(s) for s in raw]

        available_languages = []
        try:
            for t in tlist:
                available_languages.append({
                    "language":      t.language,
                    "language_code": t.language_code,
                    "is_generated":  t.is_generated,
                })
        except Exception:
            pass

        print(f"[Transcript] API succeeded: {len(segments)} segments, lang={found_lang}")
        return {
            "success":            True,
            "_strategy":          "api",
            "video_id":           video_id,
            "language":           found_lang,
            "segments":           segments,
            "available_languages": available_languages,
        }

    except Exception as e:
        err_str = str(e)
        print(f"[Transcript] API failed: {type(e).__name__}: {err_str[:120]}")
        return {
            "error":      err_str,
            "error_type": type(e).__name__,
            "_strategy":  "api",
            "video_id":   video_id,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Result builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_full_result(video_id: str, raw: Dict, preserve_formatting: bool) -> Dict:
    segments = raw.get("segments", [])

    if preserve_formatting:
        full_text = ""
        for seg in segments:
            text = seg["text"].strip()
            if full_text and not full_text.endswith("\n"):
                if text and text[0].isupper() and full_text[-1] in ".!?":
                    full_text += "\n\n"
                else:
                    full_text += " "
            full_text += text
    else:
        full_text = " ".join(s["text"].strip() for s in segments)

    return {
        "success":             True,
        "video_id":            video_id,
        "language":            raw.get("language", "unknown"),
        "transcript":          full_text,
        "segments":            segments,
        "segment_count":       len(segments),
        "character_count":     len(full_text),
        "word_count":          len(full_text.split()),
        "available_languages": raw.get("available_languages", []),
        "extraction_method":   raw.get("_strategy", "unknown"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_transcript(
    video_id:            str,
    languages:           List[str] = None,
    preserve_formatting: bool      = True,
) -> Dict:
    """
    Get transcript for a YouTube video.

    Extraction order:
      1. yt-dlp WITH cookies  (if YT_COOKIES_FILE env var is set)
      2. youtube-transcript-api  (fast, no cookies needed on non-blocked IPs)
      3. yt-dlp WITHOUT cookies  (last resort)

    On Streamlit Cloud where the IP is blocked by YouTube:
      - Steps 2 and 3 will both fail with IpBlocked
      - Step 1 will succeed if a valid cookies.txt is uploaded in the sidebar
    """
    if languages is None:
        languages = ["en"]

    cookies_file = os.environ.get("YT_COOKIES_FILE", "").strip()
    has_cookies  = bool(cookies_file and os.path.exists(cookies_file))

    print(f"[Transcript] video={video_id}, cookies={'YES' if has_cookies else 'NO'}, "
          f"cookie_path={cookies_file or 'not set'}")

    # ── Strategy 1: yt-dlp WITH cookies (best for Streamlit Cloud) ──────────
    if has_cookies:
        result = _fetch_via_ytdlp(video_id, languages, cookies_file=cookies_file)
        if result.get("success"):
            return _build_full_result(video_id, result, preserve_formatting)
        print(f"[Transcript] yt-dlp+cookies failed: {result.get('error','')[:100]}")

    # ── Strategy 2: youtube-transcript-api (fast; fails on blocked IPs) ─────
    result2 = _fetch_via_api(video_id, languages)
    if result2.get("success"):
        return _build_full_result(video_id, result2, preserve_formatting)
    api_error = result2.get("error", "")
    print(f"[Transcript] API failed: {api_error[:100]}")

    # ── Strategy 3: yt-dlp WITHOUT cookies (last resort) ────────────────────
    if not has_cookies:
        result3 = _fetch_via_ytdlp(video_id, languages, cookies_file="")
        if result3.get("success"):
            return _build_full_result(video_id, result3, preserve_formatting)
        ytdlp_error = result3.get("error", "unknown")
        print(f"[Transcript] yt-dlp (no cookies) failed: {ytdlp_error[:100]}")
    else:
        ytdlp_error = "Already tried yt-dlp+cookies above"

    # ── All strategies failed ────────────────────────────────────────────────
    is_blocked = any(
        kw in api_error.lower()
        for kw in ("ipblocked", "ip", "blocked", "requestblocked")
    )

    if is_blocked and not has_cookies:
        user_msg = (
            "YouTube is blocking requests from this server's IP address.\n\n"
            "**Fix:** Upload your `cookies.txt` file in the sidebar under "
            "**🎬 YouTube Access** to authenticate as your Google account "
            "and bypass the block.\n\n"
            "**How to export cookies.txt:**\n"
            "1. Install **Get cookies.txt LOCALLY** (Chrome/Firefox extension)\n"
            "2. Go to youtube.com while logged in\n"
            "3. Click the extension → Export → save as `cookies.txt`\n"
            "4. Upload it in the sidebar"
        )
    elif is_blocked and has_cookies:
        user_msg = (
            "YouTube is still blocking requests even with your cookies.\n\n"
            "Your cookies may have **expired** or be from the wrong account.\n\n"
            "**Fix:** Re-export a fresh `cookies.txt` from your browser:\n"
            "1. Open Chrome/Firefox → go to youtube.com\n"
            "2. Make sure you are logged in to your Google account\n"
            "3. Use **Get cookies.txt LOCALLY** extension → Export\n"
            "4. Upload the new file in the sidebar"
        )
    elif "disabled" in api_error.lower():
        user_msg = "The creator has disabled captions/transcripts for this video."
    elif "unavailable" in api_error.lower() or "not found" in api_error.lower():
        user_msg = "This video is unavailable or private."
    else:
        user_msg = f"Could not retrieve transcript: {api_error}"

    return {
        "success":      False,
        "error":        user_msg,
        "api_error":    api_error,
        "ytdlp_error":  ytdlp_error,
        "has_cookies":  has_cookies,
        "video_id":     video_id,
    }


def get_transcript_with_timestamps(
    video_id:  str,
    languages: List[str] = None,
) -> Dict:
    """Get transcript with [MM:SS] or [HH:MM:SS] timestamp markers on each line."""
    result = get_transcript(video_id, languages, preserve_formatting=False)
    if not result.get("success"):
        return result

    timestamped_segments = []
    for seg in result["segments"]:
        t  = seg["start"]
        h  = int(t // 3600)
        mi = int((t % 3600) // 60)
        s  = int(t % 60)
        ts = f"{h:02d}:{mi:02d}:{s:02d}" if h > 0 else f"{mi:02d}:{s:02d}"
        timestamped_segments.append({
            "timestamp":    ts,
            "start_seconds": t,
            "duration":     seg["duration"],
            "text":         seg["text"],
        })

    formatted = "\n".join(
        f"[{s['timestamp']}] {s['text']}" for s in timestamped_segments
    )
    result["timestamped_segments"]      = timestamped_segments
    result["formatted_with_timestamps"] = formatted
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_transcript.py <url_or_id> [lang] [cookies.txt]")
        sys.exit(1)

    vid   = extract_video_id(sys.argv[1])
    langs = sys.argv[2].split(",") if len(sys.argv) > 2 else ["en"]
    if len(sys.argv) > 3:
        os.environ["YT_COOKIES_FILE"] = sys.argv[3]

    if not vid:
        print(f"Error: cannot parse video ID from: {sys.argv[1]}")
        sys.exit(1)

    res = get_transcript(vid, langs)
    if res.get("success"):
        print(f"✅ Got transcript ({res['word_count']} words, method={res['extraction_method']})")
        print(res["transcript"][:500])
    else:
        print(f"❌ {res['error']}")
    sys.exit(0 if res.get("success") else 1)
