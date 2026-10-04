from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError


@workflow.defn
class ProcessStyleWorkflow:
    @workflow.run
    async def run(self, job_id: str):
        try:
            await workflow.execute_activity(
                "process_style",
                job_id,
                start_to_close_timeout=timedelta(hours=24),
                heartbeat_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=10),
                    maximum_interval=timedelta(minutes=1),
                ),
            )
        except ActivityError:
            await workflow.execute_activity(
                "mark_style_failed",
                job_id,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=10),
            )
