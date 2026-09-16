"""PEA One Agent definition; live transport is deliberately elsewhere."""

from pathlib import Path

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.genai import Client

from app.tools.adk_tools import WscTools


def create_adk_agent(*, model: str, client: Client, tools: WscTools) -> Agent:
    return Agent(
        name="pea_one_agent",
        model=Gemini(model=model, client=client),
        instruction=Path(__file__).resolve().parents[1].joinpath(
            "prompts/adk_voice.md"
        ).read_text(encoding="utf-8"),
        tools=tools.definitions(),
    )
