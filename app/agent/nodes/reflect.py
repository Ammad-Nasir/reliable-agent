import time
import json
import hashlib
from typing import Dict, Any
from app.agent.state import AgentState
from app.config import settings
from app.agent.llm import ClaudeClient

llm_client = ClaudeClient()

def reflect_node(state: AgentState) -> Dict[str, Any]:
    """Reflection node: analyzes tool execution output, assesses goal progress, and enforces loop detection."""
    start_time = time.time()
    
    # If paused for approval or already terminated, skip reflection
    if state.get("status") in ("PENDING_APPROVAL", "COMPLETED", "FAILED", "STEP_LIMIT_EXCEEDED", "LOOP_DETECTED", "REJECTED"):
        return {}

    history = state.get("steps_history", [])
    last_act_step = None
    for s in reversed(history):
        if s.get("node") == "act":
            last_act_step = s
            break

    if not last_act_step:
        return {"total_steps": state.get("total_steps", 0) + 1}

    tool_name = last_act_step.get("tool_name", "")
    tool_input = last_act_step.get("tool_input", {})
    tool_output = last_act_step.get("tool_output", {})

    # 1. Loop Detection Logic
    tool_sig = f"{tool_name}:{json.dumps(tool_input, sort_keys=True)}"
    sig_hash = hashlib.md5(tool_sig.encode()).hexdigest()
    
    loop_counts = dict(state.get("loop_counter", {}))
    loop_counts[sig_hash] = loop_counts.get(sig_hash, 0) + 1
    
    loop_detected = state.get("loop_detected", False)
    status = state.get("status", "RUNNING")
    final_response = state.get("final_response")

    # If the same tool with identical arguments was invoked 3 or more times
    if loop_counts[sig_hash] >= settings.MAX_IDENTICAL_TOOL_CALLS:
        loop_detected = True
        status = "LOOP_DETECTED"
        final_response = (
            f"Execution halted: Repetitive tool loop detected on '{tool_name}' ({loop_counts[sig_hash]} identical calls). "
            "System intervened to prevent redundant operations and token waste."
        )

    # Also detect alternating oscillation (A -> B -> A -> B -> A)
    act_steps = [s for s in history if s.get("node") == "act" and s.get("tool_name")]
    if len(act_steps) >= 4:
        recent_tools = [s.get("tool_name") for s in act_steps[-4:]]
        if recent_tools[0] == recent_tools[2] and recent_tools[1] == recent_tools[3] and recent_tools[0] != recent_tools[1]:
            loop_detected = True
            status = "LOOP_DETECTED"
            final_response = (
                f"Execution halted: Alternating tool loop pattern detected ({recent_tools[0]} <-> {recent_tools[1]}). "
                "Agent is oscillating without converging on a resolution."
            )

    # 2. Reflect with LLM
    response = llm_client.reflect_on_tool_result(
        user_query=state.get("user_query", ""),
        current_step=f"Step {state.get('total_steps', 0) + 1}",
        tool_name=tool_name,
        tool_args=tool_input,
        tool_result=tool_output,
        history=history
    )

    latency_ms = int((time.time() - start_time) * 1000)
    in_tokens = response.input_tokens
    out_tokens = response.output_tokens
    step_cost = (in_tokens / 1_000_000 * settings.INPUT_TOKEN_COST_PER_M) + \
                (out_tokens / 1_000_000 * settings.OUTPUT_TOKEN_COST_PER_M)

    step_trace = {
        "step_number": state.get("total_steps", 0) + 1,
        "node": "reflect",
        "thought": response.thought,
        "loop_check": {
            "sig_hash": sig_hash,
            "call_count": loop_counts[sig_hash],
            "loop_detected": loop_detected
        },
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "latency_ms": latency_ms,
        "timestamp": time.time()
    }

    updated_history = list(history)
    updated_history.append(step_trace)

    return {
        "current_thought": response.thought,
        "loop_counter": loop_counts,
        "loop_detected": loop_detected,
        "status": status,
        "final_response": final_response,
        "total_steps": state.get("total_steps", 0) + 1,
        "total_input_tokens": state.get("total_input_tokens", 0) + in_tokens,
        "total_output_tokens": state.get("total_output_tokens", 0) + out_tokens,
        "total_cost_usd": round(state.get("total_cost_usd", 0.0) + step_cost, 6),
        "steps_history": updated_history
    }
