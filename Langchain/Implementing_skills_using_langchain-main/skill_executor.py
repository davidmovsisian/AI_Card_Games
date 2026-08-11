"""
Skill Executor — runs the actual skill logic after it has been selected and loaded.

This mirrors how Claude:
  1. Reads the full SKILL.md body (injected into context)
  2. Follows the workflow instructions step by step
  3. Executes any referenced scripts (bash tool calls)
  4. Produces the final response incorporating script outputs

For youtube-transcript specifically:
  - Extracts the video ID from the URL
  - Runs the extract_transcript.py script
  - Formats the response based on video length
"""

import sys
import subprocess
import importlib.util
from pathlib import Path
from typing import Any
from skill_registry import LoadedSkill


def run_script(script_path: Path, *args: str) -> dict[str, Any]:
    """
    Execute a skill's bundled Python script and capture output.
    Mirrors how Claude's bash_tool executes scripts from skill bundles.
    """
    if not script_path.exists():
        return {"success": False, "error": f"Script not found: {script_path}"}

    try:
        result = subprocess.run(
            [sys.executable, str(script_path), *args],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Script timed out after 60 seconds"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def import_script_module(script_path: Path):
    """
    Dynamically import a skill script as a Python module.
    This allows calling script functions directly (cleaner than subprocess).
    """
    spec = importlib.util.spec_from_file_location("skill_script", str(script_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute_youtube_transcript_skill(skill: LoadedSkill, user_query: str, video_url: str) -> dict[str, Any]:
    """
    Execute the youtube-transcript skill workflow.
    Follows the exact steps defined in the SKILL.md:
      Step 1: Extract video ID
      Step 2: Check dependencies
      Step 3: Extract transcript
      Step 4: Format output based on video length
    """
    script_path = skill.metadata.scripts_dir / "extract_transcript.py"
    steps_log = []

    # ── Step 1: Extract video ID ─────────────────────────────────────────────
    steps_log.append("Step 1: Extracting video ID from URL...")
    try:
        module = import_script_module(script_path)
        video_id = module.extract_video_id(video_url)
    except Exception as e:
        steps_log.append(f"  Direct import failed ({e}), falling back to subprocess")
        video_id = None

    if not video_id:
        # Subprocess fallback
        result = run_script(script_path, video_url)
        if not result["success"]:
            return {
                "success": False,
                "steps": steps_log,
                "error": f"Could not extract video ID: {result.get('error') or result.get('stderr', 'Unknown error')}",
            }

    steps_log.append(f"  ✓ Video ID: {video_id}")

    # ── Step 2: Check / install dependencies ─────────────────────────────────
    steps_log.append("Step 2: Checking dependencies (youtube-transcript-api)...")
    try:
        import youtube_transcript_api  # noqa
        steps_log.append("  ✓ youtube-transcript-api is installed")
    except ImportError:
        steps_log.append("  Installing youtube-transcript-api...")
        install = subprocess.run(
            [sys.executable, "-m", "pip", "install", "youtube-transcript-api"],
            capture_output=True, text=True
        )
        if install.returncode != 0:
            return {
                "success": False,
                "steps": steps_log,
                "error": f"Failed to install dependency: {install.stderr}",
            }
        steps_log.append("  ✓ Installed successfully")

    # ── Step 3: Extract transcript ────────────────────────────────────────────
    steps_log.append("Step 3: Extracting transcript...")
    try:
        module = import_script_module(script_path)
        transcript_result = module.get_transcript_with_timestamps(video_id)
    except Exception as e:
        steps_log.append(f"  Direct call failed: {e}")
        transcript_result = {"success": False, "error": str(e)}

    if not transcript_result["success"]:
        return {
            "success": False,
            "steps": steps_log,
            "error": transcript_result.get("error", "Transcript extraction failed"),
        }

    duration = transcript_result.get("duration_seconds", 0)
    steps_log.append(f"  ✓ Extracted {transcript_result['segment_count']} segments, {duration:.0f}s duration")

    # ── Step 4: Determine output format based on video length ─────────────────
    steps_log.append("Step 4: Determining output format...")
    if duration < 300:
        format_type = "short"
    elif duration < 1200:
        format_type = "medium"
    else:
        format_type = "long"
    steps_log.append(f"  ✓ Format: {format_type} video")

    return {
        "success": True,
        "steps": steps_log,
        "video_id": video_id,
        "format_type": format_type,
        "transcript": transcript_result.get("transcript", ""),
        "transcript_with_timestamps": transcript_result.get("formatted_with_timestamps", ""),
        "segments": transcript_result.get("segments", []),
        "duration_seconds": duration,
        "segment_count": transcript_result.get("segment_count", 0),
        "character_count": transcript_result.get("character_count", 0),
        "language_used": transcript_result.get("language_used", "en"),
        "available_languages": transcript_result.get("available_languages", []),
    }


def execute_skill(skill: LoadedSkill, user_query: str, extracted_params: dict) -> dict[str, Any]:
    """
    Route to the correct skill executor based on skill name.
    This is the dispatch layer — each skill has its own execution logic.
    """
    skill_name = skill.metadata.name

    if skill_name == "youtube-transcript":
        video_url = extracted_params.get("video_url", "")
        if not video_url:
            return {"success": False, "error": "No YouTube URL found in the query"}
        return execute_youtube_transcript_skill(skill, user_query, video_url)

    # Generic skill: just return instructions for the LLM to follow
    return {
        "success": True,
        "mode": "llm_follows_instructions",
        "instructions": skill.full_instructions,
        "params": extracted_params,
    }
