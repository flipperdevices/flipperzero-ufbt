import argparse
import json
import logging

from ..util import get_ufbt_package_version
from .subcommand import CliSubcommand

log = logging.getLogger(__name__)


class StatusSubcommand(CliSubcommand):
    COMMAND = "status"
    STATUS_FIELDS = {
        "ufbt_version": "uFBT version",
        "state_dir": "State dir",
        "download_dir": "Download dir",
        "toolchain_dir": "Toolchain dir",
        "sdk_dir": "SDK dir",
        "target": "Target",
        "mode": "Mode",
        "version": "Version",
        "details": "Details",
        "error": "Error",
    }

    def __init__(self):
        super().__init__(self.COMMAND, "Show uFBT SDK status")

    def _add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.description = """Show uFBT status - deployment paths and SDK version."""

        parser.add_argument(
            "--json",
            help="Print status in JSON format",
            action="store_true",
            default=False,
        )

        parser.add_argument(
            "status_key",
            help="Print only a single value for a specific status key",
            nargs="?",
            choices=self.STATUS_FIELDS.keys(),
        )

    def _func(self, args) -> int:
        from ..deploy import UfbtSdkDeployer
        from ..sdk_loader import BaseSdkLoader

        ufbt_version = get_ufbt_package_version()

        sdk_deployer = UfbtSdkDeployer(args.ufbt_home)
        state_data = {
            "ufbt_version": ufbt_version,
            "state_dir": str(sdk_deployer.ufbt_state_dir.absolute()),
            "download_dir": str(sdk_deployer.download_dir.absolute()),
            "sdk_dir": str(sdk_deployer.current_sdk_dir.absolute()),
            "toolchain_dir": str(sdk_deployer.toolchain_dir.absolute()),
        }

        if previous_task := sdk_deployer.get_previous_task():
            state_data.update(
                {
                    "target": previous_task.hw_target,
                    "mode": previous_task.mode,
                    "version": previous_task.all_params.get(
                        "version", BaseSdkLoader.VERSION_UNKNOWN
                    ),
                    "details": previous_task.all_params,
                }
            )
        else:
            state_data.update({"error": "SDK is not deployed"})

        skip_error_message = False
        if key := args.status_key:
            if key not in state_data:
                log.error(f"Unknown status key {key}")
                return 1
            if args.json:
                print(json.dumps(state_data[key]))
            else:
                print(state_data.get(key, ""))
        else:
            if args.json:
                print(json.dumps(state_data))
            else:
                skip_error_message = True
                for key, value in state_data.items():
                    log.info(f"{self.STATUS_FIELDS[key]:<15} {value}")

        if state_data.get("error"):
            if not skip_error_message:
                log.error("Status error: {}".format(state_data.get("error")))
            return 1
        return 0
