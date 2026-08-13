"""Execution strategy for the analysis pipeline.

Today analysis runs inline in the request, but off the event loop. The runner
seam exists so it can move to a queue without touching the API: swap
ANALYSIS_RUNNER=queue and implement QueueRunner.submit/await_result. Endpoint
code only ever calls `get_runner().run(job)`.
"""

from __future__ import annotations

from typing import Protocol

import anyio

from ..config import settings
from .pipeline import AnalysisJob, AnalysisOutput, execute


class AnalysisRunner(Protocol):
    async def run(self, job: AnalysisJob) -> AnalysisOutput: ...


class InlineRunner:
    """Runs the CPU-bound pipeline in a worker thread so the event loop keeps
    serving other requests."""

    name = "inline"

    async def run(self, job: AnalysisJob) -> AnalysisOutput:
        return await anyio.to_thread.run_sync(execute, job)


class QueueRunner:
    """Celery/RQ + Redis implementation slot.

    Wire-up when analysis needs to scale beyond the API process:
      1. `celery_app.task(name="qadam.analyze")` wrapping `pipeline.execute`.
      2. `run()` enqueues the job and awaits the result with a timeout.
      3. For long jobs, return 202 + a poll URL from the endpoint -- the
         response schema already carries `status`, so clients do not change.
    """

    name = "queue"

    async def run(self, job: AnalysisJob) -> AnalysisOutput:  # pragma: no cover
        raise NotImplementedError(
            "ANALYSIS_RUNNER=queue is not wired up yet. Set ANALYSIS_RUNNER="
            "inline, or implement QueueRunner against Celery/RQ + Redis."
        )


_runner: AnalysisRunner | None = None


def get_runner() -> AnalysisRunner:
    global _runner
    if _runner is None:
        _runner = QueueRunner() if settings.analysis_runner == "queue" else InlineRunner()
    return _runner
