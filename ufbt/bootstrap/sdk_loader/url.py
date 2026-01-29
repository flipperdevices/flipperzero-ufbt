import argparse
import logging
from typing import Dict

from .base import BaseSdkLoader

log = logging.getLogger(__name__)


class UrlSdkLoader(BaseSdkLoader):
    """
    Loads SDK from a static URL. Does not extract version info.
    """

    LOADER_MODE_KEY = "url"

    def __init__(self, download_dir: str, url: str):
        super().__init__(download_dir)
        self.url = url

    def get_sdk_component(self, target: str) -> str:
        log.info(f"Fetching SDK from {self.url}")
        return self._fetch_file(self.url)

    def get_metadata(self) -> Dict[str, str]:
        return {
            "mode": self.LOADER_MODE_KEY,
            "url": self.url,
            "version": self.VERSION_UNKNOWN,
        }

    @classmethod
    def metadata_to_init_kwargs(cls, metadata: dict) -> Dict[str, str]:
        return {"url": metadata["url"]}

    @classmethod
    def args_namespace_to_metadata(cls, args: argparse.Namespace) -> Dict[str, str]:
        if args.url and not args.hw_target:
            raise ValueError("HW target must be specified when using direct SDK URL")
        return {"url": args.url}

    @classmethod
    def add_args_to_mode_group(cls, mode_group):
        mode_group.add_argument(
            "--url",
            "-u",
            type=str,
            help="Direct URL to load SDK from",
        )
