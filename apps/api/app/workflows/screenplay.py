from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError


@workflow.defn
class GenerateScreenplayWorkflow:
    @workflow.run
    async def run(self, args: list):
        try:
            await workflow.execute_activity(
                "generate_screenplay",
                args,
                start_to_close_timeout=timedelta(hours=2),
                heartbeat_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError:
            await workflow.execute_activity(
                "fail_screenplay",
                args,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
