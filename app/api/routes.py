import uuid
import time
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models import AgentRunRecord, StepTraceRecord, ApprovalRequestRecord
from app.agent.runner import run_agent, resume_agent
from app.tasks.celery_app import celery_app
from app.tasks.agent_tasks import execute_agent_task, resume_agent_task

router = APIRouter()

class CreateRunRequest(BaseModel):
    query: str = Field(..., min_length=2, description="User question or customer support instruction.")
    async_mode: bool = Field(default=False, description="Whether to dispatch via Celery or execute immediately.")

class ApprovalDecisionRequest(BaseModel):
    approved: bool = Field(..., description="Approval decision: True to authorize risky action, False to reject.")
    reason: Optional[str] = Field(default="Supervisor manual review", description="Audit reason for decision.")
    reviewer: Optional[str] = Field(default="supervisor@company.com", description="Identifier of the reviewer.")

@router.post("/runs")
async def create_run(
    req: CreateRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Trigger a new multi-step agent run."""
    run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"

    if req.async_mode:
        try:
            # Try dispatching to Celery
            task = execute_agent_task.delay(user_query=req.query, run_id=run_id)
            return {
                "run_id": run_id,
                "task_id": str(task.id),
                "status": "DISPATCHED_TO_CELERY",
                "message": "Agent execution dispatched to Celery background worker."
            }
        except Exception as e:
            # Fall back to FastAPI background task if Celery broker is unreachable
            background_tasks.add_task(run_agent, user_query=req.query, run_id=run_id)
            return {
                "run_id": run_id,
                "status": "BACKGROUND_TASK",
                "message": f"Celery unavailable ({e}); run dispatched to FastAPI background worker."
            }

    # Synchronous execution
    state = await run_agent(user_query=req.query, run_id=run_id)
    return {
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "final_response": state.get("final_response"),
        "pending_approval": state.get("pending_approval"),
        "total_steps": state.get("total_steps"),
        "total_tokens": state.get("total_input_tokens", 0) + state.get("total_output_tokens", 0),
        "total_cost_usd": state.get("total_cost_usd", 0.0)
    }

@router.get("/runs")
async def list_runs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """List recent agent execution runs with summary metrics."""
    stmt = select(AgentRunRecord).order_by(desc(AgentRunRecord.updated_at)).limit(limit)
    res = await db.execute(stmt)
    runs = res.scalars().all()
    return [
        {
            "run_id": r.run_id,
            "user_query": r.user_query,
            "status": r.status,
            "total_steps": r.total_steps,
            "total_tokens": r.total_input_tokens + r.total_output_tokens,
            "total_cost_usd": r.total_cost_usd,
            "final_response": r.final_response,
            "created_at": r.created_at,
            "updated_at": r.updated_at
        }
        for r in runs
    ]

@router.get("/runs/{run_id}")
async def get_run_status(run_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch status and details of a specific agent run."""
    stmt = select(AgentRunRecord).where(AgentRunRecord.run_id == run_id)
    res = await db.execute(stmt)
    run = res.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    
    return {
        "run_id": run.run_id,
        "user_query": run.user_query,
        "status": run.status,
        "total_steps": run.total_steps,
        "total_input_tokens": run.total_input_tokens,
        "total_output_tokens": run.total_output_tokens,
        "total_cost_usd": run.total_cost_usd,
        "final_response": run.final_response,
        "error": run.error,
        "checkpoint_state": run.checkpoint_state,
        "created_at": run.created_at,
        "updated_at": run.updated_at
    }

@router.get("/runs/{run_id}/steps")
async def get_run_steps(run_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch full chronological step traces for a run, including thoughts, tool inputs, outputs, and latencies."""
    stmt = select(StepTraceRecord).where(StepTraceRecord.run_id == run_id).order_by(StepTraceRecord.step_number)
    res = await db.execute(stmt)
    traces = res.scalars().all()
    return [
        {
            "step_number": t.step_number,
            "node_name": t.node_name,
            "thought": t.thought,
            "tool_name": t.tool_name,
            "tool_input": t.tool_input,
            "tool_output": t.tool_output,
            "status": t.status,
            "latency_ms": t.latency_ms,
            "input_tokens": t.input_tokens,
            "output_tokens": t.output_tokens,
            "timestamp": t.timestamp
        }
        for t in traces
    ]

@router.get("/approvals")
async def list_approvals(status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """List pending or historical human approval requests."""
    stmt = select(ApprovalRequestRecord).order_by(desc(ApprovalRequestRecord.created_at))
    if status:
        stmt = stmt.where(ApprovalRequestRecord.status == status.upper())
    res = await db.execute(stmt)
    records = res.scalars().all()
    return [
        {
            "approval_id": a.approval_id,
            "run_id": a.run_id,
            "tool_name": a.tool_name,
            "tool_input": a.tool_input,
            "risk_reason": a.risk_reason,
            "status": a.status,
            "decision_reason": a.decision_reason,
            "reviewer": a.reviewer,
            "created_at": a.created_at,
            "resolved_at": a.resolved_at
        }
        for a in records
    ]

@router.post("/approvals/{approval_id}/decision")
async def submit_approval_decision(
    approval_id: str,
    req: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db)
):
    """Approve or reject a high-risk action checkpoint, then resume agent execution."""
    stmt = select(ApprovalRequestRecord).where(ApprovalRequestRecord.approval_id == approval_id)
    res = await db.execute(stmt)
    approval = res.scalars().first()
    if not approval:
        raise HTTPException(status_code=404, detail=f"Approval request '{approval_id}' not found.")
    
    if approval.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"Approval request '{approval_id}' is already {approval.status}.")

    # Update approval record
    new_status = "APPROVED" if req.approved else "REJECTED"
    approval.status = new_status
    approval.decision_reason = req.reason
    approval.reviewer = req.reviewer
    approval.resolved_at = time.time()
    await db.commit()

    # Resume agent run with supervisor decision
    updated_state = await resume_agent(
        run_id=approval.run_id,
        approval_decision=req.approved,
        decision_reason=req.reason,
        reviewer=req.reviewer
    )

    return {
        "approval_id": approval_id,
        "run_id": approval.run_id,
        "decision": new_status,
        "run_status": updated_state.get("status"),
        "final_response": updated_state.get("final_response"),
        "total_steps": updated_state.get("total_steps")
    }

@router.post("/runs/{run_id}/resume")
async def resume_run_endpoint(run_id: str):
    """Manually resume a run from its latest persisted checkpoint (crash recovery / retry)."""
    try:
        updated_state = await resume_agent(run_id=run_id)
        return {
            "run_id": run_id,
            "status": updated_state.get("status"),
            "final_response": updated_state.get("final_response"),
            "total_steps": updated_state.get("total_steps")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume run: {str(e)}")
