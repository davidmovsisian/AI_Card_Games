from typing_extensions import NotRequired
from langchain.agents import AgentState
from langchain.agents.middleware import wrap_tool_call, before_model
from langchain.messages import ToolMessage, AIMessage
from typing import Any, Callable, Optional, Literal
from langgraph.types import interrupt, Command
from langchain.tools import tool, ToolRuntime
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse
from dataclasses import dataclass, field
from threading import Lock
from contextvars import ContextVar


class TravelState(AgentState):
    active_agent: Optional[
            Literal[
                "primary_agent",
                "flight_agent",
                "car_rental_agent",
                "hotel_agent",
                "excursion_agent",
            ]
        ]
    user_info: NotRequired[str]
    handoff_data: NotRequired[dict]


def sensitive_tools_middleware(sensitive_tools_names: list[str]):
    @wrap_tool_call
    def _(request: Any, handler: Any) -> Any:
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
                    content=f"User rejected execution of tool '{tool_name}'. Please ask how else you can assist.",
                    tool_call_id=tool_call_id,
                )

        return handler(request)

    return _


def format_prompt_middleware(prompt: str):
    @wrap_model_call
    def _(
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        user_info = request.runtime.state.get(
            "user_info", "No user information available."
        )

        from datetime import datetime
        formatted_prompt = prompt.format(
            user_info=user_info,
            time=datetime.now(),
        )

        request = request.override(system_prompt=formatted_prompt)
        return handler(request)

    return _


# ---------------------------------------------------------------------------
# Budget middleware
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BudgetPolicy:
    """Policy for one agent/node."""

    budget_fraction: float
    primary_model: str
    primary_max_tokens: int #maximal output tokens for primary model
    fallback_model: str
    fallback_max_tokens: int #maximal output tokens for fallback model


@dataclass
class LLMInvocationCost:
    node_name: str
    model: str
    expected_cost: float
    actual_cost: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None #actual output tokens, from model response
    max_tokens: int | None = None #maximal output tokens for llm invocation, selected from primary and fallback models


@dataclass
class GraphBudget:
    total_budget: float
    actual_spend: float = 0.0
    records: list[LLMInvocationCost] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    @property
    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self.total_budget - self.actual_spend)

    def add_actual_cost(self, cost: float) -> None:
        with self._lock:
            self.actual_spend += cost

    def add_record(self, record: LLMInvocationCost) -> None:
        with self._lock:
            self.records.append(record)

    def report(self) -> None:
        print("\nLLM budget report")
        print("-" * 70)
        for i, r in enumerate(self.records, 1):
            actual = "N/A" if r.actual_cost is None else f"${r.actual_cost:.6f}"
            print(
                f"{i}. {r.node_name}: model={r.model}, "
                f"expected=${r.expected_cost:.6f}, actual={actual}, "
                f"input={r.input_tokens}, output={r.output_tokens}"
            )
        print("-" * 70)
        print(f"Budget:   ${self.total_budget:.6f}")
        print(f"Actual:   ${self.actual_spend:.6f}")
        print(f"Remaining:${self.remaining:.6f}")


_current_graph_budget: ContextVar[GraphBudget | None] = ContextVar(
    "current_graph_budget", default=None
)


def set_graph_budget(budget: GraphBudget):
    return _current_graph_budget.set(budget)


def reset_graph_budget(token) -> None:
    _current_graph_budget.reset(token)


def _litellm_model_name(model: str) -> str:
    # LangChain commonly uses "openai:gpt-4o" while LiteLLM pricing
    # uses "openai/gpt-4o".
    return model.replace(":", "/", 1) if ":" in model else model


def _model_name(model: Any) -> str:
    name = getattr(model, "model_name", None) or getattr(model, "model", None)
    if not name:
        name = getattr(model, "_model_name", None)
    if not name:
        raise ValueError(
            f"Cannot determine model name from {type(model).__name__}"
        )
    return _litellm_model_name(str(name))


def _token_count(model_name: str, messages: list[Any], tools: list[Any] | None) -> int:
    """Use LiteLLM's tokenizer/pricing data for the pre-call estimate."""
    import litellm

    kwargs = {
        "model": model_name,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    return int(litellm.token_counter(**kwargs))


def _cost_for_tokens(model_name: str, input_tokens: int, output_tokens: int) -> float:
    import litellm

    prompt_cost, completion_cost = litellm.cost_per_token(
        model=model_name,
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
    )
    return float(prompt_cost + completion_cost)


def _max_tokens(model: Any) -> int | None:
    kwargs = getattr(model, "kwargs", None) or {}
    value = kwargs.get("max_tokens")
    return int(value) if value is not None else None


def _usage_from_response(response: ModelResponse):
    """Extract LangChain usage metadata from the returned AI message."""
    message = getattr(response, "result", None)
    if message is None:
        message = getattr(response, "response", None)

    # Current ModelResponse exposes .result as the model output in the
    # LangChain middleware API. Keep the fallback for minor API variations.
    usage = getattr(message, "usage_metadata", None) or {}
    if not usage:
        metadata = getattr(message, "response_metadata", None) or {}
        usage = metadata.get("token_usage") or metadata.get("usage") or {}

    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    return (
        int(input_tokens) if input_tokens is not None else None,
        int(output_tokens) if output_tokens is not None else None,
    )


def budget_middleware(policy: BudgetPolicy, node_name: str):
    """
    Estimate this model invocation before it runs. If the primary model is
    too expensive for the remaining budget, try the fallback model.

    Actual spend is recorded after the model returns.
    """
    from langchain.chat_models import init_chat_model

    primary = init_chat_model(
        model=policy.primary_model,
        temperature=0,
    ).bind(
        parallel_tool_calls=False,
        max_tokens=policy.primary_max_tokens,
    )

    fallback = init_chat_model(
        model=policy.fallback_model,
        temperature=0,
    ).bind(
        parallel_tool_calls=False,
        max_tokens=policy.fallback_max_tokens,
    )

    @wrap_model_call
    def _(
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        budget = _current_graph_budget.get()
        if budget is None:
            raise RuntimeError(
                "BudgetMiddleware requires a GraphBudget. "
                "Call set_graph_budget() before invoking the graph."
            )

        # format_prompt_middleware runs before this middleware, so the final
        # system prompt is already present in request.system_prompt.
        messages = list(request.messages)
        system_prompt = getattr(request, "system_prompt", None)
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        tools = getattr(request, "tools", None)

        def estimate(model_obj: Any, max_tokens: int):
            model_name = _model_name(model_obj)
            input_tokens = _token_count(model_name, messages, tools)
            expected = _cost_for_tokens(
                model_name,
                input_tokens,
                max_tokens,
            )
            return model_name, input_tokens, expected

        primary_name, primary_input_tokens, primary_expected = estimate(
            primary, policy.primary_max_tokens
        )

        # The fraction is a preferred allocation. We do not waste unused
        # allocation: remaining global budget can still be used.
        node_allocation = budget.total_budget * policy.budget_fraction
        node_spend = sum(
            r.actual_cost or 0.0
            for r in budget.records
            if r.node_name == node_name
        )
        node_remaining = max(0.0, node_allocation - node_spend)
        allowed = max(node_remaining, budget.remaining)

        selected = primary
        selected_name = primary_name
        selected_expected = primary_expected
        selected_input_tokens = primary_input_tokens
        selected_max_tokens = policy.primary_max_tokens

        if primary_expected > allowed:
            fallback_name, fallback_input_tokens, fallback_expected = estimate(
                fallback, policy.fallback_max_tokens
            )

            if fallback_expected <= budget.remaining:
                selected = fallback
                selected_name = fallback_name
                selected_expected = fallback_expected
                selected_input_tokens = fallback_input_tokens
                selected_max_tokens = policy.fallback_max_tokens
            else:
                raise RuntimeError(
                    f"Budget exceeded for {node_name}: "
                    f"estimated primary=${primary_expected:.6f}, "
                    f"estimated fallback=${fallback_expected:.6f}, "
                    f"remaining=${budget.remaining:.6f}"
                )

        request_for_call = request.override(model=selected)

        record = LLMInvocationCost(
            node_name=node_name,
            model=selected_name,
            expected_cost=selected_expected,
            max_tokens=selected_max_tokens,
            input_tokens=selected_input_tokens,
        )

        response = handler(request_for_call)

        input_tokens, output_tokens = _usage_from_response(response)
        actual_cost = None

        if input_tokens is not None and output_tokens is not None:
            actual_cost = _cost_for_tokens(
                selected_name,
                input_tokens,
                output_tokens,
            )
            budget.add_actual_cost(actual_cost)

        record.input_tokens = input_tokens
        record.output_tokens = output_tokens
        record.actual_cost = actual_cost
        budget.add_record(record)

        return response

    return _


@tool
def complete_or_escalate(
    reason: str,
    runtime: ToolRuntime[None, TravelState],
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
        None,
    )

    transfer_message = ToolMessage(
        content=f"Resuming dialog with the host assistant. Reason: {reason}",
        tool_call_id=runtime.tool_call_id,
    )

    messages = [transfer_message]
    if last_ai_message is not None:
        messages.insert(0, last_ai_message)

    return Command(
        goto="primary_agent",
        update={
            "active_agent": "primary_agent",
            "messages": messages,
        },
        graph=Command.PARENT,
    )
