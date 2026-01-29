import argparse
import logging
import re
from html.parser import HTMLParser
from typing import Dict

from ..util import FileType
from .base import BaseSdkLoader

log = logging.getLogger(__name__)


class BranchSdkLoader(BaseSdkLoader):
    """
    Loads SDK from a branch on update server.
    Uses HTML parsing of index page to find all files in the branch.
    """

    LOADER_MODE_KEY = "branch"
    UPDATE_SERVER_BRANCH_ROOT = "https://update.flipperzero.one/builds/firmware"

    class LinkExtractor(HTMLParser):
        FILE_NAME_RE = re.compile(r"flipper-z-(\w+)-(\w+)-(.+)\.(\w+)")

        def reset(self) -> None:
            super().reset()
            self.files = {}
            self.version = None

        def handle_starttag(self, tag, attrs):
            if tag == "a" and (href := dict(attrs).get("href", None)):
                # .map files have special naming and we don't need them
                if ".map" in href:
                    return
                if match := self.FILE_NAME_RE.match(href):
                    target, file_type, version, ext = match.groups()
                    file_type_str = f"{file_type}_{ext}".upper()
                    if file_type := FileType._member_map_.get(file_type_str, None):
                        self.files[(file_type, target)] = href
                    if not self.version:
                        self.version = version
                    elif not version.startswith(self.version):
                        raise RuntimeError(
                            f"Found multiple versions: {self.version} and {version}"
                        )

    def __init__(self, download_dir: str, branch: str, branch_root_url: str = None):
        super().__init__(download_dir)
        self._branch = branch
        self._branch_root = branch_root_url or self.UPDATE_SERVER_BRANCH_ROOT
        self._branch_url = f"{self._branch_root}/{branch}/"
        self._branch_files = {}
        self._version = None
        self._fetch_branch()

    def _fetch_branch(self) -> None:
        # Fetch html index page with links to files
        log.info(f"Fetching branch index {self._branch_url}")
        with self._open_url(self._branch_url) as response:
            html = response.read().decode("utf-8")
            extractor = BranchSdkLoader.LinkExtractor()
            extractor.feed(html)
            self._branch_files = extractor.files
            self._version = extractor.version
        log.info(f"Found version {self._version}")

    def get_sdk_component(self, target: str) -> str:
        if not (file_name := self._branch_files.get((FileType.SDK_ZIP, target), None)):
            raise ValueError(f"SDK bundle not found for {target}")

        return self._fetch_file(self._branch_url + file_name)

    def get_metadata(self) -> Dict[str, str]:
        return {
            "mode": self.LOADER_MODE_KEY,
            "branch": self._branch,
            "version": self._version,
            "branch_root": self._branch_root,
        }

    @classmethod
    def metadata_to_init_kwargs(cls, metadata: dict) -> Dict[str, str]:
        return {
            "branch": metadata["branch"],
            "branch_root_url": metadata.get(
                "branch_root", BranchSdkLoader.UPDATE_SERVER_BRANCH_ROOT
            ),
        }

    @classmethod
    def args_namespace_to_metadata(cls, args: argparse.Namespace) -> Dict[str, str]:
        return {
            "branch": args.branch,
            "branch_root": args.index_url,
        }

    @classmethod
    def add_args_to_mode_group(cls, mode_group):
        mode_group.add_argument(
            "--branch",
            "-b",
            type=str,
            help="Branch to load SDK from",
        )
