from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from tools.excursions import (
    book_excursion,
    cancel_excursion,
    search_trip_recommendations,
    update_excursion,
)
from .common import (
    sensitive_tools_middleware, 
    complete_or_escalate,
    format_prompt_middleware
)

model = init_chat_model(model="openai:gpt-4o", temperature=0)

excursion_tools = [book_excursion, cancel_excursion, search_trip_recommendations, update_excursion]
sensitive_tools_names = ["book_excursion", "cancel_excursion", "update_excursion"]

# Handoff tool, used for transfer from prime assistant to specialized assistant
class ToBookExcursion(BaseModel):
    """Transfers work to a specialized assistant to handle trip recommendations
    and other excursion bookings."""

    location: str = Field(
        description="The location where the user wants to book a recommended trip."
    )
    request: str = Field(
        description="Any additional information or requests from the user regarding the trip recommendation."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "location": "Lucerne",
                "request": "The user is interested in outdoor activities and scenic views.",
            }
        }


# ---------------------------------------------------------------------------
# Prompt & runnable
# ---------------------------------------------------------------------------
EXCURSION_PROMPT = """
    You are a specialized assistant for handling trip recommendations.
    The primary assistant delegates work to you whenever the user needs help booking a recommended trip.
    Search for available trip recommendations based on the user's preferences and confirm the booking details with the customer.

    Remember: a booking isn't completed until after the relevant tool has successfully been used.

    If the user needs help, and none of your tools are appropriate for it, then call "complete_or_escalate" 
        to hand control back to the primary assistant with a short reason.
        Do not waste the user's time. Do not make up invalid tools or functions.

    
    Some examples for which you should CompleteOrEscalate:
    - 'nevermind i think I'll book separately.'
    - 'i need to figure out transportation while i'm there.'
    - 'Oh wait i haven't booked my flight yet i'll do that first.'
    - 'Excursion booking confirmed!'

    Current time: {time}.
"""

excursion = create_agent(
    model = model.bind(parallel_tool_calls=False),
    tools = excursion_tools + [complete_or_escalate],
    middleware = [
        sensitive_tools_middleware(sensitive_tools_names),
        format_prompt_middleware(EXCURSION_PROMPT)
        ]
)