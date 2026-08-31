from datetime import datetime
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.messages import AIMessage, ToolMessage
from langchain.tools import tool, ToolRuntime
from langgraph.types import Command, interrupt
from langchain.agents.middleware import wrap_model_call
from typing import Any
 
from tools.flights import (
    cancel_ticket,
    search_flights,
    update_ticket_to_new_flight,
)
from .common import TravelState

model = init_chat_model(model="openai:gpt-4o", temperature=0)

#  Tools
all_tools = [search_flights, update_ticket_to_new_flight, cancel_ticket]
sensitive_tools_names = ["update_ticket_to_new_flight", "cancel_ticket"]

# System prompt
FLIGHT_ASSISTANT_PROMPT = (
    "You are a specialized assistant for handling flight updates and cancellations. "
    "The primary assistant delegates work to you whenever the user needs help updating "
    "their bookings. Confirm updated flight details with the customer and inform them "
    "of any additional fees. "
    "When searching, be persistent — expand your query bounds if the first search "
    "returns no results. "
    "If you need more information, the customer changes their mind, or no available "
    "tool can help, call complete_or_escalate to hand control back to the primary "
    "assistant with a short explanation. "
    "Remember: a booking is not complete until the relevant tool has been used "
    "successfully.\n\n"
    "Current user flight information:\n<Flights>\n{user_info}\n</Flights>\n"
    "Current time: {time}."
)

def build_agent(llm):
    """Return a compiled flight-booking agent bound to *llm*."""
    return create_agent(
        model=llm.bind(parallel_tool_calls=False),
        tools=all_tools,
        system_prompt=FLIGHT_ASSISTANT_PROMPT.format(time = datetime.now),
    )
