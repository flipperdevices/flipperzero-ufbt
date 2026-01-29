import argparse
import logging
import os
from typing import Optional


##############################################################################

log = logging.getLogger(__name__)


def entry_point(cmdline_args=None) -> Optional[int]:
    from .command import ALL
    from .paths import DEFAULT_UFBT_HOME
    from .sdk_loader import BaseSdkLoader

    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d [%(levelname).1s] %(message)s",
        level=logging.INFO,
        datefmt="%H:%M:%S",
    )

    root_parser = argparse.ArgumentParser()
    root_parser.add_argument(
        "--no-check-certificate",
        help="Disable SSL certificate verification",
        action="store_true",
        default=False,
    )
    root_parser.add_argument(
        "--ufbt-home",
        "-d",
        help="uFBT state directory",
        default=os.environ.get("UFBT_HOME", DEFAULT_UFBT_HOME),
    )
    root_parser.add_argument(
        "--force",
        "-f",
        help="Force operation",
        action="store_true",
        default=False,
    )
    root_parser.add_argument(
        "--verbose",
        help="Enable extra logging",
        action="store_true",
        default=False,
    )

    parsers = root_parser.add_subparsers()
    for subcommand_cls in ALL:
        subcommand_cls().add_to_parser(parsers)

    args = root_parser.parse_args(cmdline_args)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.no_check_certificate:
        # Temporary fix for SSL negotiation failure on Mac
        import ssl

        _ssl_context = ssl.create_default_context()
        _ssl_context.check_hostname = False
        _ssl_context.verify_mode = ssl.CERT_NONE
        BaseSdkLoader._SSL_CONTEXT = _ssl_context

    if "func" not in args:
        root_parser.print_help()
        return 1

    try:
        return args.func(args)

    except Exception as e:
        log.error(f"Failed to run operation: {e}. See --verbose for details")
        if args.verbose:
            raise
        return 2
