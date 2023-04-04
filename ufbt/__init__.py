import os
import pathlib
import platform
import sys

from .bootstrap import bootstrap_subcommands
from .bootstrap import main as bootstrap_main


def ufbt_ep():
    if not os.environ.get("UFBT_STATE_DIR"):
        os.environ["UFBT_STATE_DIR"] = os.path.expanduser("~/.ufbt")
    if not os.environ.get("FBT_TOOLCHAIN_PATH"):
        os.environ["FBT_TOOLCHAIN_PATH"] = os.environ["UFBT_STATE_DIR"]

    ufbt_state_dir = pathlib.Path(os.environ["UFBT_STATE_DIR"])

    if any(
        map(sys.argv.__contains__, bootstrap_subcommands)
    ):  # if any of the subcommands are in the arguments
        return bootstrap_main()

    if not os.path.exists(ufbt_state_dir):
        bootstrap_main()

    if not (ufbt_state_dir / "current" / "scripts" / "ufbt").exists():
        print("SDK is missing scripts distribution.")
        print("You might be trying to use an SDK in an outdated format.")
        return 1

    UFBT_APP_DIR = os.getcwd()

    if platform.system() == "Windows":
        commandline = (
            'call "%UFBT_STATE_DIR%\current\scripts\toolchain\fbtenv.cmd" env'
            f'python3 -m SCons -Q --warn=target-not-built -C "%UFBT_STATE_DIR%/current/scripts/ufbt" "UFBT_APP_DIR={UFBT_APP_DIR}" '
            + " ".join(sys.argv[1:])
        )

    else:
        commandline = (
            '. "$UFBT_STATE_DIR/current/scripts/toolchain/fbtenv.sh" && '
            f'python3 -m SCons -Q --warn=target-not-built -C "$UFBT_STATE_DIR/current/scripts/ufbt" "UFBT_APP_DIR={UFBT_APP_DIR}" '
            + " ".join(sys.argv[1:])
        )

    # print(commandline)
    return os.system(commandline)


if __name__ == "__main__":
    sys.exit(ufbt_ep() or 0)
