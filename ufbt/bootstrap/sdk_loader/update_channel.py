import argparse
import enum
import json
import logging
from typing import Dict

from ..util import FileType
from .base import BaseSdkLoader

log = logging.getLogger(__name__)


class UpdateChannelSdkLoader(BaseSdkLoader):
    """
    Loads SDK from a release channel on update server.
    Uses JSON index to find all files in the channel.
    Supports official update server and unofficial servers following the same format.
    """

    LOADER_MODE_KEY = "channel"
    OFFICIAL_INDEX_URL = "https://update.flipperzero.one/firmware/directory.json"

    class UpdateChannel(enum.Enum):
        DEV = "development"
        RC = "release-candidate"
        RELEASE = "release"

    def __init__(
        self, download_dir: str, channel: UpdateChannel, json_index_url: str = None
    ):
        super().__init__(download_dir)
        self.channel = channel
        self.json_index_url = json_index_url or self.OFFICIAL_INDEX_URL
        self.version_info = self._fetch_version(self.channel)

    def _fetch_version(self, channel: UpdateChannel) -> dict:
        log.info(f"Fetching version info for {channel} from {self.json_index_url}")
        try:
            data = json.loads(
                self._open_url(self.json_index_url).read().decode("utf-8")
            )
        except json.decoder.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

        if not (channels := data.get("channels", [])):
            raise ValueError(f"Invalid channel: {channel}")

        channel_data = next((c for c in channels if c["id"] == channel.value), None)
        if not channel_data:
            raise ValueError(f"Invalid channel: {channel}")

        if not (versions := channel_data.get("versions", [])):
            raise ValueError(f"Empty channel: {channel}")

        log.info(f"Using version: {versions[0]['version']}")
        log.debug(f"Changelog: {versions[0].get('changelog', 'None')}")
        return versions[0]

    @staticmethod
    def _get_file_info(version_data: dict, file_type: FileType, file_target: str):
        if not (files := version_data.get("files", [])):
            raise ValueError("Empty files list")

        if not (
            file_info := next(
                (
                    f
                    for f in files
                    if f["type"] == file_type.value and f["target"] == file_target
                ),
                None,
            )
        ):
            raise ValueError(f"Invalid file type: {file_type}")

        return file_info

    def get_sdk_component(self, target: str) -> str:
        file_info = self._get_file_info(self.version_info, FileType.SDK_ZIP, target)
        if not (file_url := file_info.get("url", None)):
            raise ValueError("Invalid file url")

        return self._fetch_file(file_url)

    def get_metadata(self) -> Dict[str, str]:
        return {
            "mode": self.LOADER_MODE_KEY,
            "channel": self.channel.name.lower(),
            "json_index": self.json_index_url,
            "version": self.version_info["version"],
        }

    @classmethod
    def metadata_to_init_kwargs(cls, metadata: dict) -> Dict[str, str]:
        return {
            "channel": UpdateChannelSdkLoader.UpdateChannel[
                metadata["channel"].upper()
            ],
            "json_index_url": metadata.get("json_index", None),
        }

    @classmethod
    def args_namespace_to_metadata(cls, args: argparse.Namespace) -> Dict[str, str]:
        return {
            "channel": args.channel,
            "json_index": args.index_url,
        }

    @classmethod
    def add_args_to_mode_group(cls, mode_group):
        mode_group.add_argument(
            "--channel",
            "-c",
            type=str,
            help="Channel to load SDK from",
            choices=[c.name.lower() for c in cls.UpdateChannel],
        )
