from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError


@workflow.defn
class ProcessMediaWorkflow:
    @workflow.run
    async def run(self, job_id: str) -> None:
        try:
            await workflow.execute_activity(
                "process_media",
                job_id,
                start_to_close_timeout=timedelta(minutes=45),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=5),
                    maximum_interval=timedelta(minutes=1),
                    maximum_attempts=3,
                ),
            )
        except ActivityError:
            await workflow.execute_activity(
                "mark_media_failed",
                job_id,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=10),
            )
