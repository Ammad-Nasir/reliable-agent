import asyncio
from typing import Dict, Any, Optional
from app.tasks.celery_app import celery_app
from app.agent.runner import run_agent, resume_agent

@celery_app.task(name="tasks.execute_agent_run", bind=True)
def execute_agent_task(self, user_query: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Background Celery task to execute agent graph asynchronously."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        final_state = loop.run_until_complete(run_agent(user_query=user_query, run_id=run_id))
        return {
            "run_id": final_state.get("run_id"),
            "status": final_state.get("status"),
            "final_response": final_state.get("final_response"),
            "total_steps": final_state.get("total_steps")
        }
    finally:
        loop.close()

@celery_app.task(name="tasks.resume_agent_run", bind=True)
def resume_agent_task(
    self,
    run_id: str,
    approval_decision: Optional[bool] = None,
    decision_reason: Optional[str] = None,
    reviewer: Optional[str] = None
) -> Dict[str, Any]:
    """Background Celery task to resume agent after approval or crash recovery."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        final_state = loop.run_until_complete(
            resume_agent(
                run_id=run_id,
                approval_decision=approval_decision,
                decision_reason=decision_reason,
                reviewer=reviewer
            )
        )
        return {
            "run_id": final_state.get("run_id"),
            "status": final_state.get("status"),
            "final_response": final_state.get("final_response"),
            "total_steps": final_state.get("total_steps")
        }
    finally:
        loop.close()
