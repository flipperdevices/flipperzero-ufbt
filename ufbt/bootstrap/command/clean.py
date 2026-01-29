import argparse
import logging
import shutil

from .subcommand import CliSubcommand

log = logging.getLogger(__name__)


class CleanSubcommand(CliSubcommand):
    COMMAND = "clean"

    def __init__(self):
        super().__init__(self.COMMAND, "Clean uFBT SDK state")

    def _add_arguments(self, parser: argparse.ArgumentParser):
        parser.description = """Clean up uFBT internal state. By default cleans current SDK state.
            For cleaning app build artifacts, use 'ufbt -c' instead."""
        parser.add_argument(
            "--downloads",
            help="Clean downloads",
            action="store_true",
            default=False,
        )
        parser.add_argument(
            "--purge",
            help="Purge whole ufbt state",
            action="store_true",
            default=False,
        )

    def _func(self, args) -> int:
        from ..deploy import UfbtSdkDeployer

        sdk_deployer = UfbtSdkDeployer(args.ufbt_home)
        log.warn("If you want to clean build artifacts, use 'ufbt -c', not 'clean'")
        if args.purge:
            log.info(f"Cleaning complete ufbt state in {sdk_deployer.ufbt_state_dir}")
            shutil.rmtree(sdk_deployer.ufbt_state_dir, ignore_errors=True)
            log.info("Done")
            return

        if args.downloads:
            log.info(f"Cleaning download dir {sdk_deployer.download_dir}")
            shutil.rmtree(sdk_deployer.download_dir, ignore_errors=True)
        else:
            log.info(f"Cleaning SDK state in {sdk_deployer.current_sdk_dir}")
            shutil.rmtree(sdk_deployer.current_sdk_dir, ignore_errors=True)
        log.info("Done")
        return 0
