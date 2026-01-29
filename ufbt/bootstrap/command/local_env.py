import argparse
import logging
import os
import platform

from ..paths import ENV_FILE_NAME, STATE_DIR_TOOLCHAIN_SUBDIR
from .subcommand import CliSubcommand

log = logging.getLogger(__name__)


class LocalEnvSubcommand(CliSubcommand):
    COMMAND = "dotenv_create"

    def __init__(self):
        super().__init__(self.COMMAND, "Create a local environment for uFBT")

    def _add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.description = f"""Create a dotenv ({ENV_FILE_NAME}) file in current directory with environment variables for uFBT.
        Designed for per-project SDK management.
        If {ENV_FILE_NAME} file already exists, this command will refuse to overwrite it.
        """
        parser.add_argument(
            "--state-dir",
            help="Directory to create the local environment in. Defaults to '.ufbt'.",
            default=".ufbt",
        )

        parser.add_argument(
            "--no-link-toolchain",
            help="Don't link toolchain directory to the local environment and create a local copy",
            action="store_true",
            default=False,
        )

    @staticmethod
    def _link_dir(target_path, source_path):
        log.info(f"Linking {target_path=} to {source_path=}")
        if os.path.lexists(target_path) or os.path.exists(target_path):
            os.unlink(target_path)
        if platform.system() == "Windows":
            # Crete junction - does not require admin rights
            import _winapi

            if not os.path.isdir(source_path):
                raise ValueError(f"Source path {source_path} is not a directory")

            if not os.path.exists(target_path):
                _winapi.CreateJunction(source_path, target_path)
        else:
            os.symlink(source_path, target_path)

    def _func(self, args) -> int:
        from ..deploy import UfbtSdkDeployer

        if os.path.exists(ENV_FILE_NAME):
            log.error(
                f"File {ENV_FILE_NAME} already exists, refusing to overwrite. Please remove or update it manually."
            )
            return 1

        env_sdk_deployer = UfbtSdkDeployer(args.state_dir, STATE_DIR_TOOLCHAIN_SUBDIR)
        # Will extract toolchain dir from env
        default_sdk_deployer = UfbtSdkDeployer(args.ufbt_home)

        env_sdk_deployer.ufbt_state_dir.mkdir(parents=True, exist_ok=True)
        if args.no_link_toolchain:
            log.info("Skipping toolchain directory linking")
        else:
            env_sdk_deployer.ufbt_state_dir.mkdir(parents=True, exist_ok=True)
            default_sdk_deployer.toolchain_dir.mkdir(parents=True, exist_ok=True)
            self._link_dir(
                str(env_sdk_deployer.toolchain_dir.absolute()),
                str(default_sdk_deployer.toolchain_dir.absolute()),
            )
            log.info("To use a local copy, specify --no-link-toolchain")

        env_vars = {
            "UFBT_HOME": args.state_dir,
            # "TOOLCHAIN_PATH": str(env_sdk_deployer.toolchain_dir.absolute()),
        }

        with open(ENV_FILE_NAME, "wt") as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")

        log.info(f"Created {ENV_FILE_NAME} file in {os.getcwd()}")
        return 0
