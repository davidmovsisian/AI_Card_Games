from typing_extensions import NotRequired
from langchain.agents import AgentState
from langchain.agents.middleware import wrap_tool_call, before_model
from langchain.messages import SystemMessage, ToolMessage, AIMessage
from typing import Any
from langgraph.types import interrupt
from datetime import datetime
from langchain.tools import tool, ToolRuntime
from langgraph.types import Command

class TravelState(AgentState):
    active_agent: NotRequired[str]
    user_info: NotRequired[str]

def create_sensitive_tools_middleware(sensitive_tools_names: list[str]):
    @wrap_tool_call
    def sensitive_tools_middleware(request: Any, handler: Any) -> Any:
        tool_name = request.tool_call["name"]
        tool_args = request.tool_call["args"]
        tool_call_id = request.tool_call["id"]

        if tool_name in sensitive_tools_names:
            human_response = interrupt({
                "question": f"Approval required to execute: '{tool_name}'",
                "action": tool_name,
                "args": tool_args,
            })

            if not human_response.get("approved", False):
                return ToolMessage(
                    content= f"User rejected execution of tool '{tool_name}'. Please ask how else you can assist.",
                    tool_call_id = tool_call_id)
                
        # Execute the tool
        return handler(request)

    return sensitive_tools_middleware


def format_prompt_middleware(prompt: str):
    @before_model
    def prompt_middleware(state: TravelState, runtime):
        user_info = state.get(
            "user_info",
            "No user information available.",
        )

        formatted_prompt = prompt.format(
            user_info=user_info,
            time=datetime.now(),
        )

        messages = list(state["messages"])

        if messages and isinstance(messages[0], SystemMessage):
            messages[0] = SystemMessage(content=formatted_prompt)
        else:
            messages.insert(
                0,
                SystemMessage(content=formatted_prompt),
            )

        return {
            "messages": messages,
        }

    return prompt_middleware

@tool
def complete_or_escalate(
    reason: str,
    runtime: ToolRuntime[None, TravelState]
) -> Command:
    """Escalate back to primary assistant.
       Args:
         reason: Reason why the task is complete or why escalation is required.
    """
    last_ai_message = next(
        (
            msg for msg in reversed(runtime.state["messages"]) 
            if isinstance(msg, AIMessage)
            and any(
                tc["id"] == runtime.tool_call_id
                for tc in msg.tool_calls
            )
        ),
        None
    )

    transfer_message = ToolMessage(
        content=f"Resuming dialog with the host assistant. Reason: {reason}",
        tool_call_id=runtime.tool_call_id,
    )

    messages = [transfer_message]
    if last_ai_message is not None:
        messages.insert(0, last_ai_message)

    return Command(
        goto="primary_assistant",
        update={
            "active_agent": "primary_assistant",
            "messages": messages,
        },
        graph=Command.PARENT,
    )
   