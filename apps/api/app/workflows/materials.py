from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError


@workflow.defn
class AnalyzeMaterialWorkflow:
    @workflow.run
    async def run(self, args: list) -> None:
        try:
            await workflow.execute_activity(
                "analyze_interview_material",
                args,
                start_to_close_timeout=timedelta(hours=12),
                heartbeat_timeout=timedelta(minutes=15),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError:
            await workflow.execute_activity(
                "fail_interview_material",
                args,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
