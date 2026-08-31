from datetime import datetime
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from tools.hotels import (
    book_hotel,
    cancel_hotel,
    search_hotels,
    update_hotel,
)
from .common import (
    create_sensitive_tools_middleware, 
    format_prompt_middleware,
    complete_or_escalate
)

model = init_chat_model(model="openai:gpt-4o", temperature=0)

hotel_tools = [search_hotels, book_hotel, update_hotel, cancel_hotel]
sensitive_tools_names = ["book_hotel", "update_hotel", "cancel_hotel"]

# Handoff Schema & Escalation Tool
class ToHotelBookingAssistant(BaseModel):
    """Transfers work to a specialized assistant to handle hotel bookings."""

    location: str = Field(
        description="The location where the user wants to book a hotel."
    )
    checkin_date: str = Field(description="The check-in date for the hotel.")
    checkout_date: str = Field(description="The check-out date for the hotel.")
    request: str = Field(
        description="Any additional information or requests from the user regarding the hotel booking."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "location": "Zurich",
                "checkin_date": "2023-08-15",
                "checkout_date": "2023-08-20",
                "request": "I prefer a hotel near the city center with a room that has a view.",
            }
        }

HOTEL_PROMPT = """
You are a specialized assistant for handling hotel bookings. "
            "The primary assistant delegates work to you whenever the user needs help booking a hotel. "
            "Search for available hotels based on the user's preferences and confirm the booking details with the customer. "
            "When searching, be persistent. Expand your query bounds if the first search returns no results. "
            "If you need more information or the customer changes their mind, escalate the task back to the main assistant. "
            "Remember that a booking isn't completed until after the relevant tool has successfully been used."
            "\nCurrent time: {time}."
            '\n\nIf the user needs help, and none of your tools are appropriate for it, then "CompleteOrEscalate" the dialog to the host assistant. '
            "Do not waste the user's time. Do not make up invalid tools or functions."
            "\n\nSome examples for which you should CompleteOrEscalate:\n"
            " - 'what's the weather like this time of year?'\n"
            " - 'nevermind i think I'll book separately'\n"
            " - 'i need to figure out transportation while i'm there'\n"
            " - 'Oh wait i haven't booked my flight yet i'll do that first'\n"
            " - 'Hotel booking confirmed'"
"""

hotel_agent = create_agent(
    model = model.bind(parallel_tool_calls=False),
    tools = hotel_tools + [complete_or_escalate],
    system_prompt = HOTEL_PROMPT.format(time=datetime.now),
    middleware = [
        create_sensitive_tools_middleware(sensitive_tools_names),
        format_prompt_middleware(HOTEL_PROMPT)]
)