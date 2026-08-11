---
name: medium-blog-generator
description: Generate a complete, publication-ready Medium blog post on any technical topic. Use this skill whenever the user asks to write a blog post, article, technical write-up, Medium post, or any long-form content about a technology, tool, framework, concept, or project. Always trigger when the user says "write a blog", "create an article", "generate a post", "Medium post", "blog about", "write about [topic]", or asks for structured technical writing. The blog is automatically structured with all standard sections: Introduction, Challenges, Solution, Advantages, Comparison with Old Approach, Architecture Flow, Technology Stack, Code Implementation, Future Scope, Conclusion, and References.
---

# Medium Blog Generator

## Overview

This skill generates complete, publication-ready Medium blog posts on any technical topic.
It produces a structured, in-depth article with all standard professional sections including
code samples, architecture descriptions, comparisons, and curated references.
The output is ready to paste directly into Medium's editor.

## Automatic Processing

**CRITICAL**: When a user provides a topic, immediately begin generating the full blog post
without asking for confirmation or additional details. If you need the technology stack or
code language, infer it from the topic. The entire workflow is automated — call the tool
and return the formatted post.

## Core Capabilities

- Generates 2000–4000 word Medium-quality technical blog posts
- Produces all 11 required sections in correct order
- Writes real, runnable code examples tailored to the topic
- Compares modern vs legacy approaches with clear tables
- Draws an ASCII or descriptive architecture flow diagram
- Lists a curated technology stack with version numbers where relevant
- Provides 5–8 real, checkable references (docs, papers, GitHub repos)
- Adapts tone to the topic: beginner-friendly for fundamentals, advanced for deep dives

## Workflow

### Step 1: Parse the Topic

Extract from the user's message:
- **Primary topic**: the technology, tool, framework, or concept
- **Angle**: is it a tutorial, comparison, deep-dive, or introduction?
- **Audience level**: beginner / intermediate / advanced (default: intermediate)
- **Code language**: infer from topic (Python for ML/AI, JavaScript for web, etc.)

### Step 2: Call the Blog Generation Tool

Call `generate_medium_blog` with:
- `topic`: the extracted primary topic string
- `sections`: the comma-separated list of all required sections
- `audience`: the inferred audience level
- `code_language`: the inferred programming language

### Step 3: Format and Return

Present the complete blog post in this order — use Markdown headings exactly as shown:

```
# [Title]

> [One-sentence hook / subtitle]

---

## 1. Introduction
## 2. Challenges Faced Currently
## 3. Solution
## 4. Advantages
## 5. Comparison with Old Approach
## 6. Architecture Flow
## 7. Technology Stack Used
## 8. Code Implementation
## 9. Future Scope
## 10. Conclusion
## 11. References
```

## Section-by-Section Writing Guide

Each section must meet these quality standards:

### 1. Introduction (150–250 words)
- Open with a compelling hook: a surprising stat, a relatable pain point, or a bold claim
- Introduce the topic and why it matters right now
- State clearly what the reader will learn
- End with a transition sentence into the next section

### 2. Challenges Faced Currently (200–300 words)
- List 3–5 specific, concrete problems with the current/old approach
- Use bullet points with a bold label + explanation for each challenge
- Be specific — cite real bottlenecks, not vague complaints
- Example format:
  - **Scalability ceiling**: Traditional approaches break at X scale because…
  - **Operational overhead**: Maintaining Y requires Z manual steps…

### 3. Solution (200–300 words)
- Introduce the solution/technology being discussed
- Explain the core idea in one clear paragraph
- Describe the key insight that makes this approach work
- Keep it accessible — no assumed knowledge beyond what was set up in the Introduction

### 4. Advantages (150–250 words)
- List 4–6 clear advantages using a numbered or bulleted list
- For each: bold label + one-sentence benefit + one-sentence explanation of WHY
- Include both technical advantages (performance, scalability) and practical ones (DX, cost)

### 5. Comparison with Old Approach (150–200 words + table)
- Write 2–3 sentences framing the comparison
- Include a Markdown comparison table with columns:
  | Feature | Old Approach | New Approach |
  |---------|-------------|-------------|
- Cover at least 5 dimensions: performance, scalability, complexity, cost, maintainability

### 6. Architecture Flow (200–300 words)
- Write a prose description of the system architecture (2–3 paragraphs)
- Include a clear ASCII diagram OR a numbered component list that describes data flow:
  ```
  [Component A] → [Component B] → [Component C]
                         ↓
                  [Component D]
  ```
- Label every component and explain what it does

### 7. Technology Stack Used (100–150 words + table)
- Brief intro sentence
- Table with columns: | Component | Technology | Version | Purpose |
- Cover: language, framework, database/storage, infra/cloud, monitoring, testing

### 8. Code Implementation (300–500 words)
- Provide 2–3 real, runnable code snippets in the correct language
- Each snippet must be preceded by: **What this does:** one sentence
- Use proper fenced code blocks with language tag: ```python / ```javascript / etc.
- Walk through the code after each snippet in 2–3 sentences
- Show a complete mini-example if possible (input → processing → output)

### 9. Future Scope (150–200 words)
- List 4–5 specific, credible next steps or enhancements
- Each item: bold label + 1–2 sentences on how/why it would improve things
- Ground in real trends: mention actual emerging tools or research directions

### 10. Conclusion (100–150 words)
- Summarise the 3 key takeaways in a tight paragraph
- Reiterate the core value proposition of the solution
- End with a forward-looking or motivating closing sentence
- Optional: "If you found this useful, follow me for more content on [domain]."

### 11. References (8–12 items)
- Format each reference as a numbered Markdown link:
  1. [Title — Author/Org](https://real-url.com)
- Include: official docs, GitHub repos, research papers, influential blog posts
- All URLs must be plausible and real (no made-up links)
- Cover: the primary technology's docs, related tools, academic background if relevant

## Usage Patterns

### Pattern 1: Topic Only
**User**: "Write a Medium blog post about LangGraph"
**Action**: Infer audience=intermediate, code_language=python, call tool with topic="LangGraph"

### Pattern 2: Topic with Audience
**User**: "Write a beginner Medium blog post about Docker"
**Action**: Set audience=beginner, code_language=bash/yaml, generate with simpler code examples

### Pattern 3: Topic with Context
**User**: "Write a blog post about using FastAPI with PostgreSQL for building REST APIs"
**Action**: Extract topic="FastAPI with PostgreSQL REST APIs", code_language=python, generate

### Pattern 4: Framework/Tool Comparison
**User**: "Write a Medium article comparing LangChain vs LlamaIndex"
**Action**: Topic="LangChain vs LlamaIndex comparison", generate with extra emphasis on section 5

## Error Handling

| Error | Cause | What to Tell the User |
|-------|-------|----------------------|
| Topic too vague | User said "write a blog" with no topic | Ask: "What topic should the blog post cover?" |
| Unknown technology | Topic is very niche or brand-new | Generate based on general principles, note limitations |
| Generation too short | LLM produced <1500 words | Expand the shortest sections; retry Code Implementation |

## Output Formatting

### Standard Output
Return the complete blog post as a single Markdown document, starting with the title as `# Title`.
Do NOT include any preamble like "Here is your blog post:" — start directly with the `#` heading.

### After the Blog
Append a brief metadata block:
```
---
**Estimated read time**: X minutes
**Word count**: ~XXXX words
**Tags**: tag1, tag2, tag3, tag4, tag5
**Best posted**: [suggested day/time for Medium]
```

## Best Practices

1. Never use filler phrases like "In today's fast-paced world" or "In conclusion, we have seen"
2. Every section must contain original analysis — not just definitions
3. Code examples must be self-contained and actually run (no `# TODO` placeholders)
4. The comparison table must have real, specific numbers or characteristics — not "better" vs "worse"
5. References must link to real, existing resources — verify the URL pattern is correct
6. Match the blog's technical depth to the audience level set in Step 1
7. Use active voice and short paragraphs (3–4 sentences max) for Medium readability
