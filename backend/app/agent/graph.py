"""
GeordieDaz — LangGraph Agent Graph
Implements the agent workflow from PRD Figure 12 (Agent Graph Workflow).

Graph flow:
  LoadSession → RetrieveMemory → LoadPersona → AssembleContext
     ↓
  [Context ready — Realtime API handles STT→LLM→TTS streaming]
     ↓
  WriteMemory → UpdateSession
  
  HandleInterrupt ← (barge-in detected in WebSocket layer)

Note: InvokeLLM and StreamResponse are handled directly by the
WebSocket handler via OpenAI Realtime API. The graph is responsible
for context preparation (pre-turn) and memory persistence (post-turn).
"""
import logging
from functools import partial

from langgraph.graph import END, StateGraph

from app.agent.state import AgentState
from app.agent.nodes import (
    assemble_context,
    handle_interrupt,
    load_persona,
    load_session,
    retrieve_memory,
    update_session,
    write_memory,
)

logger = logging.getLogger(__name__)


def build_pre_turn_graph() -> StateGraph:
    """
    Build the PRE-TURN context preparation graph.
    Runs before each conversation turn to prepare the assembled system prompt.

    Flow: LoadSession → RetrieveMemory → LoadPersona → AssembleContext → END
    """
    graph = StateGraph(AgentState)

    graph.add_node("load_session", load_session)
    graph.add_node("retrieve_memory", retrieve_memory)
    graph.add_node("load_persona", load_persona)
    graph.add_node("assemble_context", assemble_context)

    graph.set_entry_point("load_session")
    graph.add_edge("load_session", "retrieve_memory")
    graph.add_edge("retrieve_memory", "load_persona")
    graph.add_edge("load_persona", "assemble_context")
    graph.add_edge("assemble_context", END)

    return graph.compile()


def build_post_turn_graph() -> StateGraph:
    """
    Build the POST-TURN memory + session persistence graph.
    Runs after each conversation turn completes.

    Flow: route_entry → write_memory → update_session → END
          route_entry → handle_interrupt → END  (on barge-in)
    """
    graph = StateGraph(AgentState)

    async def route_entry(state: AgentState) -> AgentState:
        """Passthrough node used purely as the routing decision point."""
        return state

    graph.add_node("route_entry", route_entry)
    graph.add_node("write_memory", write_memory)
    graph.add_node("update_session", update_session)
    graph.add_node("handle_interrupt", handle_interrupt)

    graph.set_entry_point("route_entry")

    def decide_path(state: AgentState) -> str:
        if state.get("interrupted"):
            return "handle_interrupt"
        return "write_memory"

    graph.add_conditional_edges(
        "route_entry",
        decide_path,
        {"write_memory": "write_memory", "handle_interrupt": "handle_interrupt"},
    )
    graph.add_edge("write_memory", "update_session")
    graph.add_edge("update_session", END)
    graph.add_edge("handle_interrupt", END)

    return graph.compile()


# Compiled graph instances — created once at import time
pre_turn_graph = build_pre_turn_graph()
post_turn_graph = build_post_turn_graph()


async def run_pre_turn(
    user_id: str,
    session_id: str,
    user_input: str,
    persona_id: str,
    db,
) -> AgentState:
    """
    Execute the pre-turn context preparation pipeline.
    Returns the assembled AgentState with system prompt and memories ready.
    """
    initial_state: AgentState = {
        "user_id": user_id,
        "session_id": session_id,
        "persona_id": persona_id,
        "persona_config": None,
        "user_input": user_input,
        "retrieved_memories": [],
        "working_memory": [],
        "assembled_system_prompt": "",
        "conversation_history": [],
        "response_text": "",
        "audio_chunks": [],
        "interrupted": False,
        "error": None,
        "turn_index": 0,
    }

    # Inject db into nodes that need it
    config = {"configurable": {"db": db}}
    result = await pre_turn_graph.ainvoke(initial_state, config=config)
    return result


async def run_post_turn(state: AgentState, db) -> AgentState:
    """
    Execute the post-turn memory write + session update pipeline.
    """
    config = {"configurable": {"db": db}}
    result = await post_turn_graph.ainvoke(state, config=config)
    return result
