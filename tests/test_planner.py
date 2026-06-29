"""Tests for the planner and agent."""

from __future__ import annotations

import asyncio

from forgecli.planner.agent import Agent
from forgecli.planner.plan import Plan, Step, StepStatus
from forgecli.planner.planner import Planner


class _StubPlanner(Planner):
    name = "stub"

    def __init__(self) -> None:
        self.last_goal: str | None = None

    async def make_plan(self, goal: str, *, context=None) -> Plan:  # type: ignore[override]
        self.last_goal = goal
        plan = Plan(name="stub", goal=goal)
        plan.add_step(Step(description="noop"))
        plan.add_step(Step(description="echo", tool="echo", inputs={"text": "hi"}))
        return plan


def test_agent_runs_tools() -> None:
    planner = _StubPlanner()
    agent = Agent(planner=planner)

    async def echo(step: Step) -> str:
        return str(step.inputs.get("text", ""))

    agent.register_tool("echo", echo)
    plan = asyncio.run(agent.run("goal"))
    assert planner.last_goal == "goal"
    assert all(s.status is StepStatus.SUCCEEDED for s in plan.steps)
    assert plan.steps[1].result == "hi"


def test_agent_marks_unknown_tool_as_failed() -> None:
    class _Planner(Planner):
        async def make_plan(self, goal: str, *, context=None) -> Plan:  # type: ignore[override]
            p = Plan(goal=goal)
            p.add_step(Step(description="x", tool="missing"))
            return p

    agent = Agent(planner=_Planner())
    plan = asyncio.run(agent.run("goal"))
    assert plan.steps[0].status is StepStatus.FAILED
    assert "missing" in (plan.steps[0].error or "")
