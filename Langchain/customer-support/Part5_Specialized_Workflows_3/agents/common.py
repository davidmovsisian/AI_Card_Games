from typing_extensions import NotRequired
from langchain.agents import AgentState
from langchain.agents.middleware import wrap_tool_call, before_model
from langchain.messages import SystemMessage, ToolMessage
from typing import Any
from langgraph.types import interrupt
from datetime import datetime

class TravelState(AgentState):
    active_agent: NotRequired[str]
    user_info: NotRequired[str]

def create_sensitive_tools_middleware(sensitive_tools_names: list[str]):
    @wrap_tool_call
    def sensitive_tools_middleware(request: Any, handler: Any) -> Any:
        tool_name = request.tool_call["name"]
        tool_args = request.tool_call["args"]

        if tool_name in sensitive_tools_names:
            human_response = interrupt({
                "question": f"Approval required to execute: '{tool_name}'",
                "action": tool_name,
                "args": tool_args,
            })

            if not human_response.get("approved", False):
                return (
                    ToolMessage(content= f"User rejected execution of tool '{tool_name}'. "
                    "Please ask how else you can assist.")
                )

        # Execute the tool
        return handler(request)

        
    return sensitive_tools_middleware


def formate_prompt_middleware(prompt: str):
    @before_model
    def prompt_middleware(state: TravelState, runtime):
        user_info = state.get("user_info", "User information available.")
        formated_prompt = prompt.format(
            user_info=user_info,
            time=datetime.now(),
        )

        messages = list(state["messages"])

        # Replace existing system message, or add one if none exists.
        if messages and isinstance(messages[0], SystemMessage):
            messages[0] = SystemMessage(content=formated_prompt)
        else:
            messages.insert(0, SystemMessage(content=formated_prompt))

        return {
            "messages": messages,
        }

    return prompt_middleware

# def handle_tool_error(state) -> dict:
#     error = state.get("error")
#     tool_calls = state["messages"][-1].tool_calls
#     return {
#         "messages": [
#             ToolMessage(
#                 content=f"Error: {repr(error)}\n please fix your mistakes.",
#                 tool_call_id=tc["id"],
#             )
#             for tc in tool_calls
#         ]
#     }

# def create_tool_node_with_fallback(tools: list) -> dict:
#     return ToolNode(tools).with_fallbacks(
#         [RunnableLambda(handle_tool_error)], exception_key="error"
#     )

# def update_dialog_stack(left: list[str], right: Optional[str]) -> list:
#     if right is None:
#         return left
#     if right == "pop":
#         return left[:-1]
#     return left +[right]

# class State(TypedDict):
#     messages: Annotated[list[AnyMessage], add_messages]
#     user_info: str
#     dialog_state: Annotated[
#         list[
#             Literal[
#                 "assistant",
#                 "update_flight",
#                 "book_car_rental",
#                 "book_hotel",
#                 "book_excursion",
#             ]
#         ], 
#         update_dialog_stack
#     ]

# @tool
# def complete_or_escalate(
#     reason: str,
#     runtime: ToolRuntime[None, State],
# ) -> Command:
#     """Mark the current task as complete or escalate back to the primary
#     assistant. Use when:
#     - The task is done (updated / cancelled successfully).
#     - The user changed their mind or needs help with something else.
#     - None of the available tools can satisfy the request.
 
#     Pass a short human-readable `reason` so the primary assistant has context.
#     """
#     last_ai = next(
#         msg for msg in reversed(runtime.state["messages"]) if isinstance(msg, AIMessage)
#     )
#     return Command(
#         goto="primary_assistant",
#         update={
#             "dialog_state": "pop",
#             "messages": [
#                 last_ai,
#                 ToolMessage(
#                     content=f"Returning to primary assistant. Reason: {reason}",
#                     tool_call_id=runtime.tool_call_id,
#                 ),
#             ],
#         },
#         graph=Command.PARENT,
#     )


   