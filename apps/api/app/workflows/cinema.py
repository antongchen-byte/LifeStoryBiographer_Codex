from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError


@workflow.defn
class CinemaWorkflow:
    @workflow.run
    async def run(self, identifier: str):
        try:
            await workflow.execute_activity(
                "process_cinema",
                identifier,
                start_to_close_timeout=timedelta(hours=3),
                heartbeat_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except ActivityError:
            await workflow.execute_activity(
                "fail_cinema",
                identifier,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
