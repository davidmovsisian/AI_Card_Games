"""
Skill Registry — mirrors how Claude loads and indexes available skills.

How Claude processes skills (replicated here):
  1. On startup, scan all skill directories for SKILL.md files
  2. Parse YAML frontmatter → extract (name, description)
  3. Build a lightweight index: name + description only (~100 words each)
  4. At inference time: compare user query against all descriptions
  5. If a skill matches, load the full SKILL.md body into the LLM context
  6. Execute any referenced scripts from the bundled resources
"""

import os
import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


SKILLS_DIR = Path(__file__).parent.parent / "skills"


@dataclass
class SkillMetadata:
    """Lightweight index entry — always in context (mirrors Claude's always-loaded skill headers)."""
    name: str
    description: str
    skill_dir: Path

    @property
    def scripts_dir(self) -> Path:
        return self.skill_dir / "scripts"

    @property
    def references_dir(self) -> Path:
        return self.skill_dir / "references"

    @property
    def assets_dir(self) -> Path:
        return self.skill_dir / "assets"


@dataclass
class LoadedSkill:
    """Full skill loaded into context — mirrors SKILL.md body being injected when skill triggers."""
    metadata: SkillMetadata
    full_instructions: str           # entire SKILL.md body (sans frontmatter)
    available_scripts: list[str] = field(default_factory=list)
    available_references: list[str] = field(default_factory=list)


def _parse_skill_md(skill_md_path: Path) -> Optional[SkillMetadata]:
    """
    Parse a SKILL.md file and extract frontmatter metadata.
    Mimics how Claude reads skill name + description into its lightweight index.
    """
    content = skill_md_path.read_text(encoding="utf-8")

    # Extract YAML frontmatter between --- delimiters
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not fm_match:
        return None

    try:
        fm = yaml.safe_load(fm_match.group(1))
    except yaml.YAMLError:
        return None

    name = fm.get("name", "")
    description = fm.get("description", "")

    if not name or not description:
        return None

    return SkillMetadata(
        name=name,
        description=description,
        skill_dir=skill_md_path.parent,
    )


def _extract_skill_body(skill_md_path: Path) -> str:
    """Extract the markdown body (everything after frontmatter)."""
    content = skill_md_path.read_text(encoding="utf-8")
    # Remove frontmatter
    body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, count=1, flags=re.DOTALL)
    return body.strip()


def load_skill_registry() -> dict[str, SkillMetadata]:
    """
    Scan skills directory and build the lightweight registry index.
    This is analogous to Claude loading all skill name+description pairs into its context.
    """
    registry: dict[str, SkillMetadata] = {}

    if not SKILLS_DIR.exists():
        print(f"[SkillRegistry] Skills directory not found: {SKILLS_DIR}")
        return registry

    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        metadata = _parse_skill_md(skill_md)
        if metadata:
            registry[metadata.name] = metadata
            print(f"[SkillRegistry] Loaded skill: {metadata.name}")

    return registry


def load_full_skill(metadata: SkillMetadata) -> LoadedSkill:
    """
    Load the full SKILL.md body + discover available resources.
    Mirrors the moment Claude decides a skill matches and loads its full body into context.
    """
    skill_md = metadata.skill_dir / "SKILL.md"
    full_instructions = _extract_skill_body(skill_md)

    # Discover scripts
    scripts = []
    if metadata.scripts_dir.exists():
        scripts = [f.name for f in metadata.scripts_dir.iterdir() if f.is_file()]

    # Discover references
    references = []
    if metadata.references_dir.exists():
        references = [f.name for f in metadata.references_dir.iterdir() if f.is_file()]

    return LoadedSkill(
        metadata=metadata,
        full_instructions=full_instructions,
        available_scripts=scripts,
        available_references=references,
    )


def get_registry_summary(registry: dict[str, SkillMetadata]) -> str:
    """
    Format all skill name+description pairs for injection into the LLM context.
    This is exactly what Claude sees in its <available_skills> block.
    """
    lines = ["<available_skills>"]
    for name, meta in registry.items():
        lines.append(f"""<skill>
<name>{name}</name>
<description>{meta.description}</description>
</skill>""")
    lines.append("</available_skills>")
    return "\n".join(lines)
