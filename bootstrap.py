import os
import enum
import json
import re
import shutil
import tarfile
import argparse

from zipfile import ZipFile

from pathlib import PurePosixPath, Path
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import urlopen
from html.parser import HTMLParser

# Setup logging
import logging

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


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
    class SdkEntry(enum.Enum):
        SDK = "sdk"
        SCRIPTS = "scripts"
        LIB = "lib"
        FW_ELF = "fwelf"
        FW_BIN = "fwbin"
        FW_BUNDLE = "fwbundle"

    ANY_TARGET_FILE_TYPES = (
        FileType.CORE2_FIRMWARE_TGZ,
        FileType.SCRIPTS_TGZ,
        FileType.RESOURCES_TGZ,
    )

    ENTRY_TO_FILE_TYPE = {
        SdkEntry.SDK: FileType.SDK_ZIP,
        SdkEntry.SCRIPTS: FileType.SCRIPTS_TGZ,
        SdkEntry.LIB: FileType.LIB_ZIP,
        SdkEntry.FW_ELF: FileType.FIRMWARE_ELF,
        SdkEntry.FW_BIN: FileType.FULL_BIN,
        SdkEntry.FW_BUNDLE: FileType.UPDATE_TGZ,
    }

    def __init__(self, download_dir: str):
        self._download_dir = download_dir

    # Returns local FS path. Downloads file if necessary
    def get_sdk_component(self, entry: SdkEntry, target: str):
        raise NotImplementedError()

    def get_metadata(self):
        raise NotImplementedError()

    def _fixup_target_type(self, file_type: FileType, target: str) -> str:
        return "any" if file_type in self.ANY_TARGET_FILE_TYPES else target

    def _fetch_file(self, url: str):
        log.debug(f"Fetching {url}")
        file_name = PurePosixPath(unquote(urlparse(url).path)).parts[-1]
        file_path = os.path.join(self._download_dir, file_name)

        os.makedirs(self._download_dir, exist_ok=True)

        with urlopen(url) as response, open(file_path, "wb") as out_file:
            data = response.read()
            out_file.write(data)

        return file_path


class BranchSdkLoader(BaseSdkLoader):
    class LinkExtractor(HTMLParser):
        FILE_NAME_RE = re.compile(r"flipper-z-(\w+)-(\w+)-([^\.]+)\.(\w+)")

        def reset(self):
            super().reset()
            self.files = {}
            self.version = None

        def handle_starttag(self, tag, attrs):
            if tag == "a" and (href := dict(attrs).get("href", None)):
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
        with urlopen(self._branch_url) as response:
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

    def get_sdk_component(self, entry: BaseSdkLoader.SdkEntry, target: str):
        file_type = self.ENTRY_TO_FILE_TYPE[entry]
        target = self._fixup_target_type(self.ENTRY_TO_FILE_TYPE[entry], target)
        if not (file_name := self._branch_files.get((file_type, target), None)):
            raise ValueError(f"File not found for {entry} {target}")

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

    def get_sdk_component(self, entry: BaseSdkLoader.SdkEntry, target: str):
        file_type = self.ENTRY_TO_FILE_TYPE[entry]
        target = self._fixup_target_type(file_type, target)

        file_info = self._get_file_info(self.version_info, file_type, target)
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
        data = json.loads(urlopen(url).read().decode("utf-8"))

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


def deploy_sdk(target_dir: str, sdk_loader: BaseSdkLoader, hw_target: str):
    sdk_layout = {
        BaseSdkLoader.SdkEntry.SDK: ("sdk", None),
        BaseSdkLoader.SdkEntry.SCRIPTS: (".", None),
        BaseSdkLoader.SdkEntry.LIB: ("lib", None),
        BaseSdkLoader.SdkEntry.FW_ELF: ("firmware.elf", None),
        BaseSdkLoader.SdkEntry.FW_BIN: ("firmware.bin", None),
        BaseSdkLoader.SdkEntry.FW_BUNDLE: (
            ".",
            lambda s: os.path.splitext(os.path.basename(s))[0].replace(
                "flipper-z-", ""  # ugly
            ),
        ),
    }

    log.info(f"uFBT state dir: {target_dir}")
    shutil.rmtree(target_dir, ignore_errors=True)

    sdk_state = {
        "meta": {"hw_target": hw_target, **sdk_loader.get_metadata()},
        "components": {},
    }
    for entry, (entry_dir, entry_path_converter) in sdk_layout.items():
        log.info(f"Deploying {entry} to {entry_dir}")
        sdk_component_path = sdk_loader.get_sdk_component(entry, hw_target)
        component_dst_path = os.path.join(target_dir, entry_dir)
        if sdk_component_path.endswith(".zip"):
            with ZipFile(sdk_component_path, "r") as zip_file:
                zip_file.extractall(component_dst_path)
        elif sdk_component_path.endswith(".tgz"):
            with tarfile.open(sdk_component_path, "r:gz") as tar_file:
                tar_file.extractall(component_dst_path)
        else:
            shutil.copy2(sdk_component_path, component_dst_path)

        if entry_path_converter:
            component_meta_path = entry_path_converter(sdk_component_path)
        else:
            component_meta_path = os.path.relpath(component_dst_path, target_dir)

        sdk_state["components"][entry.value] = component_meta_path

    with open(os.path.join(target_dir, "sdk_state.json"), "w") as f:
        json.dump(sdk_state, f, indent=4)
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
    args = parser.parse_args()

    ufbt_work_dir = Path(args.ufbt_dir)
    ufbt_download_dir = ufbt_work_dir / "download"
    ufbt_state_dir = ufbt_work_dir / "current"

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

    deploy_sdk(ufbt_state_dir.absolute(), sdk_loader, args.hw_target)


if __name__ == "__main__":
    main()
