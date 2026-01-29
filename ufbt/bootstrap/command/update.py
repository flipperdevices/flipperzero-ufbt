import argparse

from .subcommand import CliSubcommand


class UpdateSubcommand(CliSubcommand):
    COMMAND = "update"

    def __init__(self):
        super().__init__(self.COMMAND, "Update uFBT SDK")

    def _add_arguments(self, parser: argparse.ArgumentParser) -> None:
        from ..sdk_loader import ALL

        parser.description = """Update uFBT SDK. By default uses the last used target and mode. 
        Otherwise deploys latest release."""

        parser.add_argument(
            "--hw-target",
            "-t",
            help="Hardware target",
        )
        parser.add_argument(
            "--index-url",
            help="URL to use for SDK discovery",
        )
        mode_group = parser.add_mutually_exclusive_group(required=False)
        for loader_cls in ALL:
            loader_cls.add_args_to_mode_group(mode_group)

    def _func(self, args) -> int:
        from ..deploy import SdkDeployTask, UfbtSdkDeployer

        sdk_deployer = UfbtSdkDeployer(args.ufbt_home)

        task_to_deploy = sdk_deployer.get_previous_task() or SdkDeployTask.default()
        task_to_deploy.update_from(SdkDeployTask.from_args(args))

        return 0 if sdk_deployer.deploy(task_to_deploy) else 1
