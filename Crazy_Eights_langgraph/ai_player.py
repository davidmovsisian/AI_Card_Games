"""LLM move selection for AI players, built with LangChain.

The engine decides what is legal; the LLM only picks one of the legal card indices
(and a suit when it chooses an 8), plus an optional bit of banter.
"""
import os
from pathlib import Path
from typing import List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

PROMPTS_DIR = Path(__file__).parent/"prompts"
SYSTEM_TEMPLATE = (PROMPTS_DIR/"system_prompt.txt").read_text(encoding="utf-8")
USER_PROMPT = (PROMPTS_DIR/"user_prompt.txt").read_text(encoding="utf-8")
MODEL_NAME = os.environ.get("CRAZY8_MODEL", "gpt-4o")

class AIMoveDecision(BaseModel):
    