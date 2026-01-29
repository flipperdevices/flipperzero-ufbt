import argparse
import logging
from pathlib import Path
from typing import Dict

from .base import BaseSdkLoader

log = logging.getLogger(__name__)


class LocalSdkLoader(BaseSdkLoader):
    """
    Loads SDK from a file in filesystem. Does not extract version info.
    """

    LOADER_MODE_KEY = "local"

    def __init__(self, download_dir: str, file_path: str):
        super().__init__(download_dir)
        self.file_path = file_path

    def get_sdk_component(self, target: str) -> str:
        log.info(f"Loading SDK from {self.file_path}")
        return self.file_path

    def get_metadata(self) -> Dict[str, str]:
        return {
            "mode": self.LOADER_MODE_KEY,
            "file_path": self.file_path,
            "version": self.VERSION_UNKNOWN,
        }

    @classmethod
    def metadata_to_init_kwargs(cls, metadata: dict) -> Dict[str, str]:
        return {"file_path": metadata["file_path"]}

    @classmethod
    def args_namespace_to_metadata(cls, args: argparse.Namespace) -> Dict[str, str]:
        if args.local:
            if not args.hw_target:
                raise ValueError("HW target must be specified when using local SDK")
            return {"file_path": str(Path(args.local).absolute())}
        return {}

    @classmethod
    def add_args_to_mode_group(cls, mode_group):
        mode_group.add_argument(
            "--local",
            "-l",
            type=str,
            help="Path to local SDK zip file",
        )
