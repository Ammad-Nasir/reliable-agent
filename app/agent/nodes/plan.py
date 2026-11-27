import time
import json
from typing import Dict, Any
from app.config import settings
from app.agent.state import AgentState
from app.agent.llm import ClaudeClient
from app.tools.registry import get_claude_tools

llm_client = ClaudeClient()

def plan_node(state: AgentState) -> Dict[str, Any]:
    """Planning node: analyzes user query and current state to determine the next action or final response."""
    start_time = time.time()
    
    current_steps = state.get("total_steps", 0)
    # Check Step Limit Guardrail
    if current_steps >= settings.MAX_STEPS_LIMIT:
        state["status"] = "STEP_LIMIT_EXCEEDED"
        state["final_response"] = (
            f"Execution halted: Maximum step limit ({settings.MAX_STEPS_LIMIT}) exceeded. "
            "A human supervisor has been notified to manually complete this task."
        )
        return {
            "status": "STEP_LIMIT_EXCEEDED",
            "final_response": state["final_response"],
            "current_thought": "Safety limit reached: aborting execution to prevent infinite loop or token exhaustion."
        }

    # If a pre-approved tool call is queued from supervisor resumption, proceed directly to act
    if state.get("approval_status") == "APPROVED" and state.get("current_tool_call"):
        tool_name = state["current_tool_call"].get("name")
        return {
            "current_thought": f"Supervisor authorized high-risk action '{tool_name}'. Proceeding with execution."
        }

    user_query = state.get("user_query", "")
    plan = state.get("plan", [])
    history = state.get("steps_history", [])
    rejection_reason = state.get("approval_decision_reason") if state.get("approval_status") == "REJECTED" else None
    loop_warning = "Action loop suspected: please vary your tool choice or conclude." if state.get("loop_detected") else None

    available_tools = get_claude_tools()
    response = llm_client.plan_next_step(
        user_query=user_query,
        plan=plan,
        history=history,
        available_tools=available_tools,
        rejection_reason=rejection_reason,
        loop_warning=loop_warning
    )
    
    latency_ms = int((time.time() - start_time) * 1000)
    in_tokens = response.input_tokens
    out_tokens = response.output_tokens
    
    # Calculate incremental token cost
    step_cost = (in_tokens / 1_000_000 * settings.INPUT_TOKEN_COST_PER_M) + \
                (out_tokens / 1_000_000 * settings.OUTPUT_TOKEN_COST_PER_M)

    step_trace = {
        "step_number": current_steps + 1,
        "node": "plan",
        "thought": response.thought,
        "tool_call": response.tool_call,
        "final_answer": response.final_answer,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "latency_ms": latency_ms,
        "timestamp": time.time()
    }

    updated_history = list(state.get("steps_history", []))
    updated_history.append(step_trace)

    updates = {
        "current_thought": response.thought,
        "steps_history": updated_history,
        "total_input_tokens": state.get("total_input_tokens", 0) + in_tokens,
        "total_output_tokens": state.get("total_output_tokens", 0) + out_tokens,
        "total_cost_usd": round(state.get("total_cost_usd", 0.0) + step_cost, 6)
    }

    if response.tool_call:
        updates["current_tool_call"] = response.tool_call
    elif response.final_answer:
        updates["final_response"] = response.final_answer
        updates["status"] = "COMPLETED"
        updates["current_tool_call"] = None

    return updates
