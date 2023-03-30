import argparse
import enum
import json
import logging
import os
import re
import shutil
import tarfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse
from urllib.request import urlopen
from zipfile import ZipFile

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

_ssl_context = None


class FileType(enum.Enum):
    SDK_ZIP = "sdk_zip"
    LIB_ZIP = "lib_zip"
    CORE2_FIRMWARE_TGZ = "core2_firmware_tgz"
    RESOURCES_TGZ = "resources_tgz"
    SCRIPTS_TGZ = "scripts_tgz"
    UPDATE_TGZ = "update_tgz"
    FIRMWARE_ELF = "firmware_elf"
    FULL_BIN = "full_bin"
    FULL_DFU = "full_dfu"
    FULL_JSON = "full_json"
    UPDATER_BIN = "updater_bin"
    UPDATER_DFU = "updater_dfu"
    UPDATER_ELF = "updater_elf"
    UPDATER_JSON = "updater_json"


class BaseSdkLoader:
    def __init__(self, download_dir: str):
        self._download_dir = download_dir

    # Returns local FS path. Downloads file if necessary
    def get_sdk_component(self, target: str):
        raise NotImplementedError()

    def get_metadata(self):
        raise NotImplementedError()

    def _fetch_file(self, url: str):
        log.debug(f"Fetching {url}")
        file_name = PurePosixPath(unquote(urlparse(url).path)).parts[-1]
        file_path = os.path.join(self._download_dir, file_name)

        os.makedirs(self._download_dir, exist_ok=True)

        with urlopen(url, context=_ssl_context) as response, open(
            file_path, "wb"
        ) as out_file:
            data = response.read()
            out_file.write(data)

        return file_path


class BranchSdkLoader(BaseSdkLoader):
    class LinkExtractor(HTMLParser):
        FILE_NAME_RE = re.compile(r"flipper-z-(\w+)-(\w+)-(.+)\.(\w+)")

        def reset(self):
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

    def __init__(self, branch: str, download_dir: str):
        super().__init__(download_dir)
        self._branch = branch
        self._branch_url = f"https://update.flipperzero.one/builds/firmware/{branch}/"
        self._branch_files = {}
        self._version = None
        self._fetch_branch()

    def _fetch_branch(self):
        # Fetch html index page with links to files
        log.info(f"Fetching branch index {self._branch_url}")
        with urlopen(self._branch_url, context=_ssl_context) as response:
            html = response.read().decode("utf-8")
            extractor = BranchSdkLoader.LinkExtractor()
            extractor.feed(html)
            self._branch_files = extractor.files
            self._version = extractor.version
        log.info(f"Found version {self._version}")

    def get_metadata(self):
        return {
            "mode": "branch",
            "branch": self._branch,
            "version": self._version,
        }

    def get_sdk_component(self, target: str):
        if not (file_name := self._branch_files.get((FileType.SDK_ZIP, target), None)):
            raise ValueError(f"SDK bundle not found for {target}")

        return self._fetch_file(self._branch_url + file_name)


class UpdateChannelSdkLoader(BaseSdkLoader):
    class UpdateChannel(enum.Enum):
        DEV = "development"
        RC = "release-candidate"
        RELEASE = "release"

    def __init__(self, channel: UpdateChannel, download_dir: str):
        super().__init__(download_dir)
        self.channel = channel
        self.version_info = self._fetch_version(self.channel)

    def get_sdk_component(self, target: str):
        file_info = self._get_file_info(self.version_info, FileType.SDK_ZIP, target)
        if not (file_url := file_info.get("url", None)):
            raise ValueError(f"Invalid file url")

        return self._fetch_file(file_url)

    def get_metadata(self):
        return {
            "mode": "channel",
            "channel": self.channel.name.lower(),
            "version": self.version_info["version"],
        }

    @staticmethod
    def _fetch_version(channel: UpdateChannel):
        log.info(f"Fetching version info for {channel}")
        url = "https://update.flipperzero.one/firmware/directory.json"
        data = json.loads(urlopen(url, context=_ssl_context).read().decode("utf-8"))

        channels = data.get("channels", [])
        if not channels:
            raise ValueError(f"Invalid channel: {channel}")

        channel_data = next((c for c in channels if c["id"] == channel.value), None)
        if not channel_data:
            raise ValueError(f"Invalid channel: {channel}")

        versions = channel_data.get("versions", [])
        if not versions:
            raise ValueError(f"Empty channel: {channel}")

        log.info(f"Using version: {versions[0]['version']}")
        return versions[0]

    @staticmethod
    def _get_file_info(version_data: dict, file_type: FileType, file_target: str):
        files = version_data.get("files", [])
        if not files:
            raise ValueError(f"Empty files list")

        file_info = next(
            (
                f
                for f in files
                if f["type"] == file_type.value and f["target"] == file_target
            ),
            None,
        )
        if not file_info:
            raise ValueError(f"Invalid file type: {file_type}")

        return file_info


def deploy_sdk(
    sdk_target_dir: str, sdk_loader: BaseSdkLoader, hw_target: str, force: bool
):
    UFBT_STATE_FILE_NAME = "ufbt_state.json"

    log.info(f"uFBT SDK dir: {sdk_target_dir}")
    if not force and os.path.exists(sdk_target_dir):
        # Read existing state
        with open(os.path.join(sdk_target_dir, UFBT_STATE_FILE_NAME), "r") as f:
            ufbt_state = json.load(f)
        # Check if we need to update
        if (
            ufbt_state.get("version") == sdk_loader.get_metadata().get("version")
            and ufbt_state.get("hw_target") == hw_target
        ):
            log.info("SDK is up-to-date")
            return

    shutil.rmtree(sdk_target_dir, ignore_errors=True)

    ufbt_state = {
        "hw_target": hw_target,
        **sdk_loader.get_metadata(),
    }

    log.info(f"Deploying SDK")
    sdk_component_path = sdk_loader.get_sdk_component(hw_target)
    with ZipFile(sdk_component_path, "r") as zip_file:
        zip_file.extractall(sdk_target_dir)

    with open(
        os.path.join(sdk_target_dir, UFBT_STATE_FILE_NAME),
        "w",
    ) as f:
        json.dump(ufbt_state, f, indent=4)
    log.info("SDK deployed.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--branch",
        "-b",
        help="Branch to use",
    )
    parser.add_argument(
        "--channel",
        "-c",
        help="Update channel to use",
        choices=list(
            map(
                lambda s: s.lower(),
                UpdateChannelSdkLoader.UpdateChannel.__members__.keys(),
            )
        ),
    )
    parser.add_argument(
        "--hw-target",
        "-t",
        help="Hardware target",
        default="f7",
    )
    parser.add_argument(
        "--ufbt-dir",
        "-d",
        help="uFBT state directory",
        default=".ufbt",
    )
    # Force flag
    parser.add_argument(
        "--force",
        "-f",
        help="Force download",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--no-check-certificate",
        help="Disable SSL certificate verification",
        action="store_true",
        default=False,
    )

    args = parser.parse_args()
    if args.no_check_certificate:
        # Temporary fix for SSL negotiation failure on Mac
        import ssl

        _ssl_context = ssl.create_default_context()
        _ssl_context.check_hostname = False
        _ssl_context.verify_mode = ssl.CERT_NONE

    ufbt_state_dir = Path(args.ufbt_dir)
    ufbt_download_dir = ufbt_state_dir / "download"
    ufbt_current_sdk_dir = ufbt_state_dir / "current"

    if args.branch and args.channel:
        parser.error("Only one of --branch and --channel can be specified")

    if args.branch:
        sdk_loader = BranchSdkLoader(args.branch, ufbt_download_dir)
    elif args.channel:
        sdk_loader = UpdateChannelSdkLoader(
            UpdateChannelSdkLoader.UpdateChannel[args.channel.upper()],
            ufbt_download_dir,
        )
    else:
        parser.error("One of --branch or --channel must be specified")

    deploy_sdk(ufbt_current_sdk_dir.absolute(), sdk_loader, args.hw_target, args.force)


if __name__ == "__main__":
    main()
