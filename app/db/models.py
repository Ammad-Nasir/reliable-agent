import time
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Integer, Float, Text, JSON, Boolean, Index
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class AgentRunRecord(Base):
    __tablename__ = "agent_runs"

    run_id = Column(String(64), primary_key=True, index=True)
    user_query = Column(Text, nullable=False)
    status = Column(String(32), default="RUNNING", index=True)
    current_step_index = Column(Integer, default=0)
    total_steps = Column(Integer, default=0)
    total_input_tokens = Column(Integer, default=0)
    total_output_tokens = Column(Integer, default=0)
    total_cost_usd = Column(Float, default=0.0)
    checkpoint_state = Column(JSON, nullable=True) # Full LangGraph state checkpoint
    final_response = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)

class StepTraceRecord(Base):
    __tablename__ = "step_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), index=True, nullable=False)
    step_number = Column(Integer, nullable=False)
    node_name = Column(String(32), nullable=False) # plan, act, reflect
    thought = Column(Text, nullable=True)
    tool_name = Column(String(64), nullable=True)
    tool_input = Column(JSON, nullable=True)
    tool_output = Column(JSON, nullable=True)
    status = Column(String(32), default="SUCCESS")
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    timestamp = Column(Float, default=time.time)

    __table_args__ = (
        Index("idx_run_step", "run_id", "step_number"),
    )

class ApprovalRequestRecord(Base):
    __tablename__ = "approval_requests"

    approval_id = Column(String(64), primary_key=True, index=True)
    run_id = Column(String(64), index=True, nullable=False)
    tool_name = Column(String(64), nullable=False)
    tool_input = Column(JSON, nullable=False)
    risk_reason = Column(Text, nullable=False)
    status = Column(String(32), default="PENDING", index=True) # PENDING, APPROVED, REJECTED
    decision_reason = Column(Text, nullable=True)
    reviewer = Column(String(64), nullable=True)
    created_at = Column(Float, default=time.time)
    resolved_at = Column(Float, nullable=True)
