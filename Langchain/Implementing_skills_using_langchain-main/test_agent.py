"""
test_agent.py

End-to-end test runner for the LangChain Skills Agent.
Tests the complete integrated flow:

  Mode 1 — Run existing skills (default)
      Tests routing, execution, and response quality for loaded skills.

  Mode 2 — Create a skill then run it  (--create)
      1. Takes a skill description from --skill flag
      2. Calls create_skill_programmatic() to generate + save + register the skill
      3. Immediately runs the suggested test query through the agent
      4. Verifies the correct skill was routed and a response was generated

  Mode 3 — Full suite  (--full)
      Runs all built-in tests AND the create-then-run flow.

Usage:
    # Run all built-in skill tests
    python test_agent.py

    # Test with a specific YouTube video
    python test_agent.py --video "https://www.youtube.com/watch?v=YOUR_ID"

    # Create a new skill and immediately test it
    python test_agent.py --create --skill "extract text from PDF files"

    # Full suite: built-in tests + skill creation + execution
    python test_agent.py --full --skill "translate text to Spanish"
"""

import os
import sys
import argparse
import textwrap
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def c(colour, text):
    return f"{colour}{text}{RESET}"

def banner(title: str):
    w = 60
    print(f"\n{c(BOLD, '='*w)}")
    print(c(BOLD, f"  {title}"))
    print(c(BOLD, '='*w))


# ══════════════════════════════════════════════════════════════════════════════
# TEST RESULT TRACKER
# ══════════════════════════════════════════════════════════════════════════════

class TestSuite:
    def __init__(self):
        self.results: list[dict] = []

    def record(self, name: str, passed: bool, detail: str = ""):
        self.results.append({"name": name, "passed": passed, "detail": detail})
        icon = c(GREEN, "✔ PASS") if passed else c(RED, "✗ FAIL")
        print(f"  {icon}  {name}")
        if detail:
            print(f"          {c(YELLOW, detail)}")

    def summary(self):
        total  = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        print(c(BOLD, f"\n{'─'*60}"))
        print(c(BOLD, f"  RESULTS: {passed}/{total} tests passed"))
        print(c(BOLD, f"{'─'*60}"))
        if passed < total:
            print(c(RED, "\n  Failed tests:"))
            for r in self.results:
                if not r["passed"]:
                    print(c(RED, f"    ✗ {r['name']}: {r['detail']}"))
        return passed == total


# ══════════════════════════════════════════════════════════════════════════════
# INDIVIDUAL TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_registry_loads(suite: TestSuite):
    """Verify the skills registry loads at least one skill."""
    banner("TEST: Registry loads")
    from skills_registry import get_registry
    registry = get_registry()
    print(f"  Loaded skills: {list(registry.keys())}")
    suite.record(
        "Registry loads skills",
        len(registry) > 0,
        f"{len(registry)} skill(s) found" if registry else "No skills found",
    )
    return registry


def test_list_skills(suite: TestSuite):
    """Agent can list available skills."""
    banner("TEST: List available skills")
    from skill_agent import run_agent
    from skills_registry import get_registry

    registry = get_registry()
    result   = run_agent("What skills do you have available?",
                          verbose=False, registry=registry)
    response = result["response"]
    passed   = len(response) > 20
    suite.record("List skills response", passed,
                 response[:120] if not passed else "")
    return response


def test_youtube_transcript(suite: TestSuite, video_url: str):
    """Agent correctly routes a YouTube URL to the transcript skill."""
    banner(f"TEST: YouTube transcript — {video_url}")
    from skill_agent import run_agent
    from skills_registry import get_registry

    registry = get_registry()
    result   = run_agent(
        f"Get the transcript for: {video_url}",
        verbose=False, registry=registry,
    )
    response       = result["response"]
    selected_skill = result.get("selected_skill", "")
    tools_called   = result.get("tools_called", [])

    print(f"  Selected skill : {selected_skill}")
    print(f"  Tools called   : {tools_called}")
    print(f"  Response length: {len(response)} chars")

    suite.record(
        "Transcript — skill routed",
        "youtube" in (selected_skill or "").lower(),
        f"Got: '{selected_skill}'",
    )
    suite.record(
        "Transcript — tool called",
        any("transcript" in t.lower() for t in tools_called),
        f"Tools: {tools_called}",
    )
    suite.record(
        "Transcript — response non-empty",
        len(response) > 100,
        f"{len(response)} chars",
    )
    return result


def test_youtube_summary(suite: TestSuite, video_url: str):
    """Agent summarises a YouTube video."""
    banner(f"TEST: YouTube summary — {video_url}")
    from skill_agent import run_agent
    from skills_registry import get_registry

    registry = get_registry()
    result   = run_agent(
        f"Please summarise this YouTube video: {video_url}",
        verbose=False, registry=registry,
    )
    response = result["response"]
    print(f"  Response length: {len(response)} chars")
    suite.record(
        "Summary — response generated",
        len(response) > 100,
        f"{len(response)} chars",
    )
    return result


def test_timestamped_transcript(suite: TestSuite, video_url: str):
    """Agent returns a timestamped transcript."""
    banner(f"TEST: Timestamped transcript — {video_url}")
    from skill_agent import run_agent
    from skills_registry import get_registry

    registry = get_registry()
    result   = run_agent(
        f"Get the timestamped transcript for: {video_url}",
        verbose=False, registry=registry,
    )
    response     = result["response"]
    has_timestamp = "[" in response and ":" in response
    suite.record("Timestamped — response non-empty", len(response) > 50)
    suite.record("Timestamped — contains timestamp markers", has_timestamp,
                 "No [MM:SS] found" if not has_timestamp else "")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# CREATE-THEN-RUN FLOW
# This is the key integration test: create a skill and immediately use it
# ══════════════════════════════════════════════════════════════════════════════

def test_create_then_run(suite: TestSuite, skill_description: str):
    """
    Full integrated flow:
      1. Create a skill from the description
      2. Verify files were written to disk
      3. Verify @tool was registered in skill_agent.py
      4. Run the suggested test query through the agent
      5. Verify the new skill was routed and responded
    """
    banner(f"TEST: Create skill → Run it\n  Description: \"{skill_description}\"")

    from create_skill import create_skill_programmatic
    from skill_agent  import run_agent, reload_tools
    from skills_registry import get_registry

    # ── Phase A: Skill Creation ───────────────────────────────────────────────
    print(c(CYAN, "\n  Phase A: Creating skill..."))

    log_lines = []
    def log(msg):
        log_lines.append(msg)
        print(f"  {msg}")

    creation_result = create_skill_programmatic(skill_description, log=log)

    skill_name  = creation_result["skill_name"]
    skill_dir   = Path(creation_result["skill_dir"])
    registered  = creation_result["registered"]
    test_passed = creation_result["test_passed"]
    test_reason = creation_result["test_reason"]

    print(f"\n  Skill name : {skill_name}")
    print(f"  Skill dir  : {skill_dir}")
    print(f"  Registered : {registered}")
    print(f"  Route test : {'PASS' if test_passed else 'FAIL'} — {test_reason}")

    # Record creation sub-tests
    suite.record(
        f"Create '{skill_name}' — SKILL.md written",
        (skill_dir / "SKILL.md").exists(),
    )
    suite.record(
        f"Create '{skill_name}' — script written",
        any(skill_dir.rglob("scripts/*.py")),
        "No .py files found in scripts/" if not any(skill_dir.rglob("scripts/*.py")) else "",
    )
    suite.record(
        f"Create '{skill_name}' — @tool registered",
        registered,
        "Already registered or file not found" if not registered else "",
    )
    suite.record(
        f"Create '{skill_name}' — routing self-test",
        test_passed,
        test_reason,
    )

    # ── Phase B: Hot-reload tools ─────────────────────────────────────────────
    print(c(CYAN, "\n  Phase B: Reloading tools..."))
    try:
        reload_tools()
        reload_ok = True
        print(c(GREEN, "  ✔  Tools reloaded successfully."))
    except Exception as e:
        reload_ok = False
        print(c(YELLOW, f"  ⚠  Hot-reload failed ({e}) — continuing with static import."))

    suite.record(f"Create '{skill_name}' — hot-reload tools", reload_ok)

    # ── Phase C: Run the suggested test query ─────────────────────────────────
    print(c(CYAN, "\n  Phase C: Running test query through agent..."))

    # Build brief to get the test query
    from create_skill import SkillCreator
    creator = SkillCreator()
    brief   = creator.build_brief_from_description(skill_description)
    test_query = brief.get("suggested_test_query", f"Use the {skill_name} skill")

    print(f"  Query: \"{test_query}\"")

    fresh_registry = get_registry()
    print(f"  Registry: {list(fresh_registry.keys())}")

    agent_result   = run_agent(test_query, verbose=False, registry=fresh_registry)
    response       = agent_result["response"]
    selected_skill = agent_result.get("selected_skill", "")
    tools_called   = agent_result.get("tools_called", [])

    print(f"  Selected skill : {selected_skill}")
    print(f"  Tools called   : {tools_called}")
    print(f"  Response length: {len(response)} chars")
    print(f"  Response preview:\n  {response[:300]}")

    suite.record(
        f"Run '{skill_name}' — skill routed by agent",
        skill_name in (selected_skill or "").lower() or len(tools_called) > 0,
        f"Selected: '{selected_skill}'",
    )
    suite.record(
        f"Run '{skill_name}' — response generated",
        len(response) > 50,
        f"{len(response)} chars",
    )

    return {
        "creation_result": creation_result,
        "agent_result":    agent_result,
        "brief":           brief,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Test the LangChain Skills Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          # Basic skill tests
          python test_agent.py

          # Test with a specific video
          python test_agent.py --video "https://youtu.be/dQw4w9WgXcQ"

          # Create a skill then immediately run it
          python test_agent.py --create --skill "extract text from PDF files"

          # Full suite
          python test_agent.py --full --skill "translate text to any language"
        """),
    )
    parser.add_argument("--video",  default="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                        help="YouTube video URL for transcript tests")
    parser.add_argument("--skill",  default="count words and characters in any text",
                        help="Skill description for --create / --full modes")
    parser.add_argument("--create", action="store_true",
                        help="Create a new skill then run it (skips built-in tests)")
    parser.add_argument("--full",   action="store_true",
                        help="Run all built-in tests AND create+run flow")
    parser.add_argument("--quick",  action="store_true",
                        help="Only run list-skills test (fastest smoke test)")
    args = parser.parse_args()

    # ── API key check ─────────────────────────────────────────────────────────
    if not os.environ.get("GOOGLE_API_KEY"):
        print(c(RED, "\nERROR: GOOGLE_API_KEY environment variable not set."))
        print("  Windows : set GOOGLE_API_KEY=your_key")
        print("  Linux   : export GOOGLE_API_KEY=your_key")
        sys.exit(1)

    suite = TestSuite()

    print(c(BOLD + CYAN, "\n╔══════════════════════════════════════════════════════════╗"))
    print(c(BOLD + CYAN,   "║          LangChain Skills Agent — Test Suite             ║"))
    print(c(BOLD + CYAN,   "╚══════════════════════════════════════════════════════════╝"))

    # ── Mode: create-only ─────────────────────────────────────────────────────
    if args.create and not args.full:
        test_create_then_run(suite, args.skill)
        suite.summary()
        return

    # ── Mode: quick smoke test ────────────────────────────────────────────────
    if args.quick:
        test_registry_loads(suite)
        test_list_skills(suite)
        suite.summary()
        return

    # ── Mode: built-in tests (default or --full) ──────────────────────────────
    test_registry_loads(suite)
    test_list_skills(suite)
    test_youtube_transcript(suite,  args.video)
    test_youtube_summary(suite,     args.video)
    test_timestamped_transcript(suite, args.video)

    # ── Mode: full — also create+run ──────────────────────────────────────────
    if args.full:
        test_create_then_run(suite, args.skill)

    all_passed = suite.summary()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
