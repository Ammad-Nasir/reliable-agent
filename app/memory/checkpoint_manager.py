import time
import json
from typing import Optional, Dict, Any, Tuple
from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.db.models import AgentRunRecord, StepTraceRecord, ApprovalRequestRecord
from app.memory.redis_client import short_term_memory
from app.agent.state import AgentState

class CheckpointManager:
    """Orchestrates dual-layer persistence: fast Redis scratchpad + durable Postgres/SQLite checkpointing."""

    @staticmethod
    def _sanitize_for_json(obj: Any) -> Any:
        """Ensure all fields in state are JSON-serializable."""
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        if isinstance(obj, dict):
            return {k: CheckpointManager._sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [CheckpointManager._sanitize_for_json(v) for v in obj]
        return str(obj)

    @classmethod
    async def save_checkpoint(cls, state: AgentState):
        """Persist state to both short-term memory (Redis) and durable store (Postgres/SQLite)."""
        run_id = state.get("run_id")
        if not run_id:
            return

        sanitized_state = cls._sanitize_for_json(dict(state))

        # 1. Update fast short-term Redis scratchpad
        short_term_memory.save_scratchpad(run_id, sanitized_state)

        # 2. Persist to durable database
        async with AsyncSessionLocal() as session:
            # Query existing run
            stmt = select(AgentRunRecord).where(AgentRunRecord.run_id == run_id)
            result = await session.execute(stmt)
            run_record = result.scalars().first()

            status = state.get("status", "RUNNING")
            total_steps = state.get("total_steps", 0)
            in_tokens = state.get("total_input_tokens", 0)
            out_tokens = state.get("total_output_tokens", 0)
            cost = state.get("total_cost_usd", 0.0)
            final_resp = state.get("final_response")
            err = state.get("error")

            if not run_record:
                run_record = AgentRunRecord(
                    run_id=run_id,
                    user_query=state.get("user_query", ""),
                    status=status,
                    current_step_index=total_steps,
                    total_steps=total_steps,
                    total_input_tokens=in_tokens,
                    total_output_tokens=out_tokens,
                    total_cost_usd=cost,
                    checkpoint_state=sanitized_state,
                    final_response=final_resp,
                    error=err,
                    created_at=state.get("start_time", time.time()),
                    updated_at=time.time()
                )
                session.add(run_record)
            else:
                run_record.status = status
                run_record.current_step_index = total_steps
                run_record.total_steps = total_steps
                run_record.total_input_tokens = in_tokens
                run_record.total_output_tokens = out_tokens
                run_record.total_cost_usd = cost
                run_record.checkpoint_state = sanitized_state
                run_record.final_response = final_resp
                run_record.error = err
                run_record.updated_at = time.time()

            # Save any new step traces
            history = state.get("steps_history", [])
            # Find which step numbers already exist in DB
            existing_steps_stmt = select(StepTraceRecord.step_number).where(StepTraceRecord.run_id == run_id)
            existing_steps = set((await session.execute(existing_steps_stmt)).scalars().all())

            for step in history:
                step_num = step.get("step_number", 0)
                if step_num not in existing_steps:
                    trace = StepTraceRecord(
                        run_id=run_id,
                        step_number=step_num,
                        node_name=step.get("node", "unknown"),
                        thought=step.get("thought"),
                        tool_name=step.get("tool_name"),
                        tool_input=cls._sanitize_for_json(step.get("tool_input")),
                        tool_output=cls._sanitize_for_json(step.get("tool_output")),
                        status=step.get("status", "SUCCESS"),
                        input_tokens=step.get("input_tokens", 0),
                        output_tokens=step.get("output_tokens", 0),
                        latency_ms=step.get("latency_ms", 0),
                        timestamp=step.get("timestamp", time.time())
                    )
                    session.add(trace)
                    existing_steps.add(step_num)

            # If there is a pending approval request, save it
            pending = state.get("pending_approval")
            if pending:
                app_id = pending.get("approval_id")
                if app_id:
                    app_stmt = select(ApprovalRequestRecord).where(ApprovalRequestRecord.approval_id == app_id)
                    existing_app = (await session.execute(app_stmt)).scalars().first()
                    if not existing_app:
                        app_rec = ApprovalRequestRecord(
                            approval_id=app_id,
                            run_id=run_id,
                            tool_name=pending.get("tool_name", "unknown"),
                            tool_input=cls._sanitize_for_json(pending.get("args", {})),
                            risk_reason=pending.get("risk_reason", "High-risk operation"),
                            status="PENDING",
                            created_at=time.time()
                        )
                        session.add(app_rec)

            await session.commit()

    @classmethod
    async def load_checkpoint(cls, run_id: str) -> Optional[AgentState]:
        """Load state checkpoint from Redis scratchpad or fallback to Postgres/SQLite."""
        # 1. Try Redis
        cached = short_term_memory.get_scratchpad(run_id)
        if cached and isinstance(cached, dict) and "run_id" in cached:
            return cached

        # 2. Durable Database
        async with AsyncSessionLocal() as session:
            stmt = select(AgentRunRecord).where(AgentRunRecord.run_id == run_id)
            res = await session.execute(stmt)
            record = res.scalars().first()
            if record and record.checkpoint_state:
                return record.checkpoint_state

        return None
