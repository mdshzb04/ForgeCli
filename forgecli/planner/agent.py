"""Executes a :class:`Plan` step-by-step using registered tools."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from forgecli.core.service import Service
from forgecli.planner.plan import Plan, Step
from forgecli.planner.planner import Planner

ToolFn = Callable[[Step], Awaitable[Any]]


class Agent(Service):
    """Drives a plan through a registry of tool callables.

    Tools are registered as async callables taking a :class:`Step` and
    returning an arbitrary result. This keeps the agent implementation
    small and lets us add tools (read_file, edit_file, run_shell, ...)
    without subclassing.
    """

    name = "planner.agent"

    def __init__(self, planner: Planner) -> None:
        super().__init__()
        self._planner = planner
        self._tools: dict[str, ToolFn] = {}

    @property
    def planner(self) -> Planner:
        return self._planner

    def register_tool(self, name: str, fn: ToolFn) -> None:
        """Register ``fn`` as a callable for steps tagged with ``name``."""
        self._tools[name] = fn

    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    async def run(self, goal: str, *, context: dict | None = None) -> Plan:
        """Plan and execute ``goal``; returns the executed :class:`Plan`."""
        plan = await self._planner.make_plan(goal, context=context)
        for step in plan.steps:
            await self._execute_step(step)
        return plan

    async def _execute_step(self, step: Step) -> None:
        if step.tool is None:
            step.mark_done()
            return
        tool = self._tools.get(step.tool)
        if tool is None:
            step.mark_done(error=f"Unknown tool: {step.tool}")
            return
        step.mark_running()
        try:
            step.mark_done(result=await tool(step))
        except Exception as exc:
            step.mark_done(error=str(exc))
