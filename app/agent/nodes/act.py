import time
import uuid
import json
from typing import Dict, Any
from app.agent.state import AgentState
from app.tools.registry import TOOL_REGISTRY
from app.config import settings

def act_node(state: AgentState) -> Dict[str, Any]:
    """Action node: executes tool calls with strict Pydantic validation and HITL risk guardrails."""
    start_time = time.time()
    tool_call = state.get("current_tool_call")
    
    if not tool_call:
        return {}

    tool_name = tool_call.get("name")
    tool_args = tool_call.get("args", {})
    tool_def = TOOL_REGISTRY.get(tool_name)

    if not tool_def:
        err_msg = f"Tool '{tool_name}' is not recognized in system registry."
        return {
            "latest_tool_result": {"success": False, "error": err_msg},
            "current_thought": f"Tool execution failed: {err_msg}",
            "current_tool_call": None
        }

    # 1. Typed Schema Validation with Pydantic
    try:
        validated_params = tool_def.schema(**tool_args)
    except Exception as e:
        err_msg = f"Input validation failure for tool '{tool_name}': {str(e)}"
        step_trace = {
            "step_number": state.get("total_steps", 0) + 1,
            "node": "act",
            "thought": f"Tool input validation failed for {tool_name}: {err_msg}",
            "tool_name": tool_name,
            "tool_input": tool_args,
            "tool_output": {"success": False, "error": err_msg, "code": "VALIDATION_ERROR"},
            "status": "VALIDATION_ERROR",
            "latency_ms": int((time.time() - start_time) * 1000),
            "timestamp": time.time()
        }
        updated_history = list(state.get("steps_history", []))
        updated_history.append(step_trace)
        return {
            "latest_tool_result": {"success": False, "error": err_msg, "code": "VALIDATION_ERROR"},
            "current_thought": f"Invalid arguments passed to {tool_name}. Need to correct schema.",
            "current_tool_call": None,
            "steps_history": updated_history
        }

    # 2. Human-In-The-Loop Risk Evaluation
    is_risky, risk_reason = tool_def.risk_evaluator(validated_params.model_dump())
    
    # Check if this exact action was already approved by a human
    is_pre_approved = (
        state.get("approval_status") == "APPROVED" and 
        state.get("pending_approval", {}).get("tool_name") == tool_name
    )

    if is_risky and not is_pre_approved:
        # Halt execution and require supervisor authorization
        approval_id = f"APP-{uuid.uuid4().hex[:8].upper()}"
        approval_payload = {
            "approval_id": approval_id,
            "tool_name": tool_name,
            "args": validated_params.model_dump(),
            "risk_reason": risk_reason,
            "created_at": time.time()
        }
        
        step_trace = {
            "step_number": state.get("total_steps", 0) + 1,
            "node": "act",
            "thought": f"Action '{tool_name}' flagged as HIGH-RISK: {risk_reason}. Pausing execution for human approval.",
            "tool_name": tool_name,
            "tool_input": validated_params.model_dump(),
            "status": "PENDING_APPROVAL",
            "latency_ms": int((time.time() - start_time) * 1000),
            "timestamp": time.time()
        }
        
        updated_history = list(state.get("steps_history", []))
        updated_history.append(step_trace)

        return {
            "status": "PENDING_APPROVAL",
            "pending_approval": approval_payload,
            "current_thought": f"Execution paused awaiting supervisor sign-off on: {risk_reason}",
            "steps_history": updated_history
        }

    # 3. Safe Tool Execution
    try:
        result = tool_def.func(validated_params)
        exec_status = "SUCCESS" if result.get("success", True) else "FAILED"
    except Exception as e:
        result = {"success": False, "error": f"Internal tool execution error: {str(e)}"}
        exec_status = "ERROR"

    latency_ms = int((time.time() - start_time) * 1000)
    
    step_trace = {
        "step_number": state.get("total_steps", 0) + 1,
        "node": "act",
        "thought": f"Executed tool '{tool_name}' in {latency_ms}ms.",
        "tool_name": tool_name,
        "tool_input": validated_params.model_dump(),
        "tool_output": result,
        "status": exec_status,
        "latency_ms": latency_ms,
        "timestamp": time.time()
    }

    updated_history = list(state.get("steps_history", []))
    updated_history.append(step_trace)

    return {
        "latest_tool_result": result,
        "steps_history": updated_history,
        "current_tool_call": None, # clear current tool call
        "approval_status": None, # reset approval latch after execution
        "pending_approval": None
    }
