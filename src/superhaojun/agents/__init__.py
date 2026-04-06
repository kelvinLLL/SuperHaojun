"""Multi-Agent package — SubAgent, Coordinator, and AgentTool.

Patterns:
- SubAgent: Fork a child agent with its own MessageBus for isolated subtasks
- AgentTool: A Tool ABC that spawns a SubAgent (used by the main agent)
- Coordinator: Distributes tasks across multiple SubAgents in parallel
"""

from .agent_tool import AgentTool
from .coordinator import Coordinator, TaskSpec, TaskResult
from .sub_agent import SubAgent

__all__ = ["AgentTool", "Coordinator", "SubAgent", "TaskResult", "TaskSpec"]
