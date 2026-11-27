import time
import uuid
import asyncio
from typing import Dict, Any, Optional
from app.agent.state import AgentState
from app.agent.graph import agent_graph
from app.memory.checkpoint_manager import CheckpointManager
from app.memory.redis_client import short_term_memory

async def run_agent(
    user_query: str,
    run_id: Optional[str] = None,
    initial_plan: Optional[list] = None
) -> AgentState:
    """Execute a new agent workflow from start to pause/finish with per-step checkpointing."""
    run_id = run_id or f"RUN-{uuid.uuid4().hex[:8].upper()}"
    
    # Acquire run lock
    if not short_term_memory.acquire_run_lock(run_id):
        raise RuntimeError(f"Run {run_id} is currently locked by another worker process.")

    try:
        # Initialize state
        state: AgentState = {
            "run_id": run_id,
            "user_query": user_query,
            "plan": initial_plan or [
                "1. Gather necessary customer & order facts",
                "2. Evaluate policy requirements and calculate remedies",
                "3. Execute remediation and communicate outcome"
            ],
            "current_step_index": 0,
            "current_thought": "Initiating investigation of customer request.",
            "current_tool_call": None,
            "latest_tool_result": None,
            "steps_history": [],
            "pending_approval": None,
            "approval_status": None,
            "approval_decision_reason": None,
            "approval_reviewer": None,
            "status": "RUNNING",
            "final_response": None,
            "error": None,
            "total_steps": 0,
            "loop_counter": {},
            "loop_detected": False,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "start_time": time.time()
        }

        # Initial checkpoint
        await CheckpointManager.save_checkpoint(state)

        # Execute graph node transitions
        while state.get("status") == "RUNNING":
            # Run one graph invocation turn
            result_state = agent_graph.invoke(state)
            state.update(result_state)
            
            # Save checkpoint after each node turn
            await CheckpointManager.save_checkpoint(state)

            # Check if paused for human approval or finished
            if state.get("status") != "RUNNING":
                break

        return state

    finally:
        short_term_memory.release_run_lock(run_id)

async def resume_agent(
    run_id: str,
    approval_decision: Optional[bool] = None,
    decision_reason: Optional[str] = None,
    reviewer: Optional[str] = None
) -> AgentState:
    """Resume an existing agent run after human approval decision or crash recovery."""
    if not short_term_memory.acquire_run_lock(run_id):
        raise RuntimeError(f"Run {run_id} is currently locked by another worker process.")

    try:
        state = await CheckpointManager.load_checkpoint(run_id)
        if not state:
            raise ValueError(f"Run checkpoint '{run_id}' not found.")

        # Handle human approval input
        if approval_decision is not None:
            if approval_decision is True:
                state["approval_status"] = "APPROVED"
                state["approval_decision_reason"] = decision_reason or "Approved by supervisor"
                state["approval_reviewer"] = reviewer or "supervisor"
                state["status"] = "RUNNING"
                # Restore approved tool call to current_tool_call so act_node can execute it
                if state.get("pending_approval"):
                    state["current_tool_call"] = {
                        "name": state["pending_approval"]["tool_name"],
                        "args": state["pending_approval"]["args"]
                    }
            else:
                state["approval_status"] = "REJECTED"
                state["approval_decision_reason"] = decision_reason or "Rejected by supervisor"
                state["approval_reviewer"] = reviewer or "supervisor"
                state["status"] = "RUNNING"
                state["current_tool_call"] = None # Clear rejected tool call
                state["pending_approval"] = None

        elif state.get("status") in ("PENDING_APPROVAL", "COMPLETED", "STEP_LIMIT_EXCEEDED", "LOOP_DETECTED", "REJECTED"):
            # If not approving/rejecting and already in terminal/paused state, just return
            return state
        else:
            # Crash recovery resume
            state["status"] = "RUNNING"

        await CheckpointManager.save_checkpoint(state)

        # Resume graph execution loop
        while state.get("status") == "RUNNING":
            result_state = agent_graph.invoke(state)
            state.update(result_state)
            await CheckpointManager.save_checkpoint(state)

            if state.get("status") != "RUNNING":
                break

        return state

    finally:
        short_term_memory.release_run_lock(run_id)
