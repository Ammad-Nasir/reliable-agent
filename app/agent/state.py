from typing import TypedDict, List, Dict, Any, Optional

class AgentState(TypedDict, total=False):
    run_id: str
    user_query: str
    plan: List[str]
    current_step_index: int
    current_thought: str
    
    # Tool execution fields
    current_tool_call: Optional[Dict[str, Any]] # {"name": "...", "args": {...}}
    latest_tool_result: Optional[Dict[str, Any]]
    
    # Full execution trace history
    steps_history: List[Dict[str, Any]]
    
    # Human-In-The-Loop Approval fields
    pending_approval: Optional[Dict[str, Any]] # {"approval_id": "...", "tool_name": "...", "args": {...}, "risk_reason": "..."}
    approval_status: Optional[str] # "PENDING", "APPROVED", "REJECTED"
    approval_decision_reason: Optional[str]
    approval_reviewer: Optional[str]
    
    # State flags and termination
    status: str # "RUNNING", "PENDING_APPROVAL", "COMPLETED", "FAILED", "STEP_LIMIT_EXCEEDED", "LOOP_DETECTED", "REJECTED"
    final_response: Optional[str]
    error: Optional[str]
    
    # Reliability & Guardrails metrics
    total_steps: int
    loop_counter: Dict[str, int] # hash of tool_name + args -> count
    loop_detected: bool
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    start_time: float
