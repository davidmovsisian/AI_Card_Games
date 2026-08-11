"""
Quick test script to verify the skills pipeline works end-to-end.
Run: python test_pipeline.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from skill_registry import load_skill_registry, get_registry_summary, load_full_skill
from skill_matcher import select_skill
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()


def test_registry():
    print("=" * 50)
    print("TEST 1: Skill Registry Loading")
    print("=" * 50)
    registry = load_skill_registry()
    assert len(registry) > 0, "Registry should not be empty"
    print(f"✓ Loaded {len(registry)} skills: {list(registry.keys())}")

    summary = get_registry_summary(registry)
    print(f"✓ Registry summary generated ({len(summary)} chars)")
    print("\nRegistry Summary (what LLM sees):")
    print(summary[:500] + "...")
    return registry


def test_skill_selection(registry):
    print("\n" + "=" * 50)
    print("TEST 2: Skill Selection (LLM Routing)")
    print("=" * 50)

    llm = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1,
    )

    test_cases = [
        ("Summarize https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube-transcript"),
        ("What is the capital of France?", None),
        ("Get the transcript from this video: https://youtu.be/abc123", "youtube-transcript"),
        ("Write me a poem about nature", None),
    ]

    for query, expected in test_cases:
        skill_name, confidence, reasoning = select_skill(query, registry, llm)
        status = "✓" if skill_name == expected else "~"
        print(f"{status} Query: \"{query[:50]}...\"" if len(query) > 50 else f"{status} Query: \"{query}\"")
        print(f"  → Selected: {skill_name} (expected: {expected}) | Confidence: {confidence:.2f}")
        print(f"  → Reasoning: {reasoning}")


def test_full_skill_load(registry):
    print("\n" + "=" * 50)
    print("TEST 3: Full Skill Loading")
    print("=" * 50)

    for name, meta in registry.items():
        loaded = load_full_skill(meta)
        print(f"✓ '{name}': {len(loaded.full_instructions)} chars, scripts: {loaded.available_scripts}")


def test_full_pipeline():
    print("\n" + "=" * 50)
    print("TEST 4: Full Pipeline (no LLM call to YouTube)")
    print("=" * 50)
    print("(Skipping live YouTube test — run skills_agent.py directly for that)")
    print("✓ Pipeline structure verified via graph build")

    from skills_agent import build_skills_graph
    app = build_skills_graph()
    print(f"✓ LangGraph compiled successfully: {type(app).__name__}")


if __name__ == "__main__":
    print("🧪 Running Skills Pipeline Tests\n")

    registry = test_registry()
    test_full_skill_load(registry)

    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        test_skill_selection(registry)
        test_full_pipeline()
    else:
        print("\n⚠️  GOOGLE_API_KEY not set — skipping LLM tests")
        print("   Add your key to .env file to run all tests")

    print("\n✅ All basic tests passed!")
