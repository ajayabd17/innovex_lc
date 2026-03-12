"""Service adapter for pipeline execution."""
from __future__ import annotations

from main import OrchestrationPipeline, setup_langsmith


class PipelineService:
    def __init__(self):
        setup_langsmith()
        self.pipeline = OrchestrationPipeline(config_dir="config", max_retries=1)

    async def run(self, company_name: str, progress_callback=None) -> dict:
        return await self.pipeline.generate(company_name, verbose=True, progress_callback=progress_callback)
