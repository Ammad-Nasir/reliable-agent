from typing import Literal
from langgraph.graph import StateGraph, START, END
from app.agent.state import AgentState
from app.agent.nodes.plan import plan_node
from app.agent.nodes.act import act_node
from app.agent.nodes.reflect import reflect_node

def route_after_plan(state: AgentState) -> Literal["act", "__end__"]:
    """Conditional router after planning."""
    # Check if run reached terminal state or completed
    if state.get("status") in ("COMPLETED", "STEP_LIMIT_EXCEEDED", "LOOP_DETECTED", "FAILED", "REJECTED"):
        return END
    # If a tool call was decided, transition to act node
    if state.get("current_tool_call"):
        return "act"
    return END

def route_after_act(state: AgentState) -> Literal["reflect", "__end__"]:
    """Conditional router after action execution."""
    # If high-risk action paused for human approval, exit graph loop to wait for API callback
    if state.get("status") == "PENDING_APPROVAL":
        return END
    return "reflect"

def route_after_reflect(state: AgentState) -> Literal["plan", "__end__"]:
    """Conditional router after reflection."""
    if state.get("status") in ("COMPLETED", "STEP_LIMIT_EXCEEDED", "LOOP_DETECTED", "FAILED", "REJECTED"):
        return END
    return "plan"

def build_agent_graph():
    """Constructs and compiles the multi-step StateGraph with planning, tool act, and reflect cycles."""
    builder = StateGraph(AgentState)

    # Register graph nodes
    builder.add_node("plan", plan_node)
    builder.add_node("act", act_node)
    builder.add_node("reflect", reflect_node)

    # Configure graph flow and conditional edges
    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", route_after_plan, {"act": "act", END: END})
    builder.add_conditional_edges("act", route_after_act, {"reflect": "reflect", END: END})
    builder.add_conditional_edges("reflect", route_after_reflect, {"plan": "plan", END: END})

    return builder.compile()

# Global compiled agent graph instance
agent_graph = build_agent_graph()
