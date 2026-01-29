import argparse
import logging
import os
from pathlib import PurePosixPath
from typing import Dict
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)


class BaseSdkLoader:
    """
    Base class for SDK loaders.
    """

    VERSION_UNKNOWN = "unknown"
    ALWAYS_UPDATE_VERSIONS = [VERSION_UNKNOWN, "local"]
    USER_AGENT = "uFBT SDKLoader/0.2"
    _SSL_CONTEXT = None

    def __init__(self, download_dir: str):
        self._download_dir = download_dir

    def _open_url(self, url: str):
        request = Request(url, headers={"User-Agent": self.USER_AGENT})
        return urlopen(request, context=self._SSL_CONTEXT)

    def _fetch_file(self, url: str) -> str:
        log.debug(f"Fetching {url}")
        file_name = PurePosixPath(unquote(urlparse(url).path)).parts[-1]
        file_path = os.path.join(self._download_dir, file_name)

        os.makedirs(self._download_dir, exist_ok=True)

        with self._open_url(url) as response, open(file_path, "wb") as out_file:
            data = response.read()
            out_file.write(data)

        return file_path

    # Returns local FS path. Downloads file if necessary
    def get_sdk_component(self, target: str) -> str:
        raise NotImplementedError()

    # Constructs metadata dict from loader-specific data
    def get_metadata(self) -> Dict[str, str]:
        raise NotImplementedError()

    # Reconstruction of loader-specific data from metadata dict
    @classmethod
    def metadata_to_init_kwargs(cls, metadata: dict) -> Dict[str, str]:
        raise NotImplementedError()

    # Conversion of argparse.Namespace to metadata dict
    @classmethod
    def args_namespace_to_metadata(cls, args: argparse.Namespace) -> Dict[str, str]:
        raise NotImplementedError()

    @classmethod
    def add_args_to_mode_group(cls, mode_group):
        raise NotImplementedError()
