import argparse
import enum
import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Optional
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from zipfile import ZipFile

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
    VERSION_UNKNOWN = "unknown"
    USER_AGENT = "UFBT Bootstrap"
    _SSL_CONTEXT = None

    def __init__(self, download_dir: str):
        self._download_dir = download_dir

    # Returns local FS path. Downloads file if necessary
    def get_sdk_component(self, target: str):
        raise NotImplementedError()

    def get_metadata(self):
        raise NotImplementedError()

    @staticmethod
    def metadata_to_init_kwargs(metadata: dict):
        raise NotImplementedError()

    def _open_url(self, url: str):
        request = Request(url, headers={"User-Agent": self.USER_AGENT})
        return urlopen(request, context=self._SSL_CONTEXT)

    def _fetch_file(self, url: str):
        log.debug(f"Fetching {url}")
        file_name = PurePosixPath(unquote(urlparse(url).path)).parts[-1]
        file_path = os.path.join(self._download_dir, file_name)

        os.makedirs(self._download_dir, exist_ok=True)

        with self._open_url(url) as response, open(file_path, "wb") as out_file:
            data = response.read()
            out_file.write(data)

        return file_path


class BranchSdkLoader(BaseSdkLoader):
    UPDATE_SERVER_BRANCH_ROOT = "https://update.flipperzero.one/builds/firmware"

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

    def __init__(self, download_dir: str, branch: str, branch_root_url: str = None):
        super().__init__(download_dir)
        self._branch = branch
        self._branch_root = branch_root_url or self.UPDATE_SERVER_BRANCH_ROOT
        self._branch_url = f"{self._branch_root}/{branch}/"
        self._branch_files = {}
        self._version = None
        self._fetch_branch()

    def _fetch_branch(self):
        # Fetch html index page with links to files
        log.info(f"Fetching branch index {self._branch_url}")
        with self._open_url(self._branch_url) as response:
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
            "branch_root_url": self._branch_root,
        }

    @staticmethod
    def metadata_to_init_kwargs(metadata: dict):
        return {
            "branch": metadata["branch"],
            "branch_root_url": metadata.get("branch_root_url", None),
        }

    def get_sdk_component(self, target: str):
        if not (file_name := self._branch_files.get((FileType.SDK_ZIP, target), None)):
            raise ValueError(f"SDK bundle not found for {target}")

        return self._fetch_file(self._branch_url + file_name)


class UpdateChannelSdkLoader(BaseSdkLoader):
    OFFICIAL_INDEX_URL = "https://update.flipperzero.one/firmware/directory.json"

    class UpdateChannel(enum.Enum):
        DEV = "development"
        RC = "release-candidate"
        RELEASE = "release"

    def __init__(
        self, download_dir: str, channel: UpdateChannel, index_url: str = None
    ):
        super().__init__(download_dir)
        self.channel = channel
        self.index_url = index_url or self.OFFICIAL_INDEX_URL
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
            "index_url": self.index_url,
            "version": self.version_info["version"],
        }

    @staticmethod
    def metadata_to_init_kwargs(metadata: dict):
        return {
            "channel": UpdateChannelSdkLoader.UpdateChannel[
                metadata["channel"].upper()
            ],
            "index_url": metadata.get("index_url", None),
        }

    def _fetch_version(self, channel: UpdateChannel):
        log.info(f"Fetching version info for {channel} from {self.index_url}")
        data = json.loads(self._open_url(self.index_url).read().decode("utf-8"))

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


class UrlSdkLoader(BaseSdkLoader):
    def __init__(self, download_dir: str, url: str):
        super().__init__(download_dir)
        self.url = url

    def get_sdk_component(self, target: str):
        return self._fetch_file(self.url)

    def get_metadata(self):
        return {"mode": "url", "url": self.url, "version": self.VERSION_UNKNOWN}

    @staticmethod
    def metadata_to_init_kwargs(metadata: dict):
        return {"url": metadata["url"]}


@dataclass
class SdkDeployTask:
    hw_target: str = None
    force: bool = False
    mode: str = None
    all_params: dict[str, str] = field(default_factory=dict)

    def update_from(self, other: "SdkDeployTask"):
        log.debug(f"deploy task update from {other=}")
        if other.hw_target:
            self.hw_target = other.hw_target

        if other.mode:
            self.mode = other.mode

        self.force = other.force
        for key, value in other.all_params.items():
            if value:
                self.all_params[key] = value
        log.debug(f"deploy task updated: {self=}")

    @staticmethod
    def default():
        task = SdkDeployTask()
        task.hw_target = "f7"
        task.mode = "channel"
        task.all_params["channel"] = UpdateChannelSdkLoader.UpdateChannel.RELEASE.value
        return task

    @staticmethod
    def from_args(args: argparse.Namespace):
        task = SdkDeployTask()
        task.hw_target = args.hw_target
        task.force = args.force
        if args.branch:
            task.mode = "branch"
            task.all_params["branch"] = args.branch
            if args.index_url:
                task.all_params["branch_root_url"] = args.index_url
        elif args.channel:
            task.mode = "channel"
            task.all_params["channel"] = args.channel
            if args.index_url:
                task.all_params["index_url"] = args.index_url
        elif args.url:
            task.mode = "url"
            task.all_params["url"] = args
        task.all_params = vars(args)
        return task

    @staticmethod
    def from_dict(data):
        task = SdkDeployTask()
        task.hw_target = data.get("hw_target")
        task.force = False
        task.mode = data.get("mode")
        task.all_params = data
        return task


class SdkLoaderFactory:
    @staticmethod
    def create_for_task(task: SdkDeployTask, download_dir: str):
        log.debug(f"SdkLoaderFactory::create_for_task {task=}")
        loader_cls = None
        if task.mode == "branch":
            loader_cls = BranchSdkLoader
        elif task.mode == "channel":
            loader_cls = UpdateChannelSdkLoader
        elif task.mode == "url":
            loader_cls = UrlSdkLoader
        else:
            raise ValueError(f"Invalid mode: {task.mode}")

        ctor_kwargs = loader_cls.metadata_to_init_kwargs(task.all_params)
        return loader_cls(download_dir, **ctor_kwargs)


class UfbtSdkDeployer:
    UFBT_STATE_FILE_NAME = "ufbt_state.json"

    def __init__(self, ufbt_state_dir: str):
        self.ufbt_state_dir = Path(ufbt_state_dir)
        self.download_dir = self.ufbt_state_dir / "download"
        self.current_sdk_dir = self.ufbt_state_dir / "current"
        self.state_file = self.current_sdk_dir / self.UFBT_STATE_FILE_NAME

    def get_previous_task(self) -> Optional[SdkDeployTask]:
        if not os.path.exists(self.state_file):
            return None
        with open(self.state_file, "r") as f:
            ufbt_state = json.load(f)
        log.debug(f"get_previous_task() loaded state: {ufbt_state=}")
        return SdkDeployTask.from_dict(ufbt_state)

    def deploy(self, task: SdkDeployTask):
        log.info(f"Deploying SDK for {task.hw_target}")
        sdk_loader = SdkLoaderFactory.create_for_task(task, self.download_dir)

        sdk_target_dir = self.current_sdk_dir.absolute()
        log.info(f"uFBT SDK dir: {sdk_target_dir}")
        if not task.force and os.path.exists(sdk_target_dir):
            # Read existing state
            with open(self.state_file, "r") as f:
                ufbt_state = json.load(f)
            # Check if we need to update
            if ufbt_state.get("version") == sdk_loader.VERSION_UNKNOWN:
                log.info("SDK is unversioned, updating")
            elif (
                ufbt_state.get("version") == sdk_loader.get_metadata().get("version")
                and ufbt_state.get("hw_target") == task.hw_target
            ):
                log.info("SDK is up-to-date")
                return True

        try:
            sdk_component_path = sdk_loader.get_sdk_component(task.hw_target)
        except Exception as e:
            log.error(f"Failed to fetch SDK for {task.hw_target}: {e}")
            return False

        shutil.rmtree(sdk_target_dir, ignore_errors=True)

        ufbt_state = {
            "hw_target": task.hw_target,
            **sdk_loader.get_metadata(),
        }

        log.info(f"Deploying SDK")

        with ZipFile(sdk_component_path, "r") as zip_file:
            zip_file.extractall(sdk_target_dir)

        with open(self.state_file, "w") as f:
            json.dump(ufbt_state, f, indent=4)
        log.info("SDK deployed.")
        return True


def _update(args):
    sdk_deployer = UfbtSdkDeployer(args.ufbt_dir)
    current_task = SdkDeployTask.from_args(args)
    task_to_deploy = None

    if previous_task := sdk_deployer.get_previous_task():
        previous_task.update_from(current_task)
        task_to_deploy = previous_task
    else:
        if current_task.mode:
            task_to_deploy = current_task
        else:
            log.error("No previous SDK state was found, fetching latest release")
            log.error("Please specify mode explicitly. See -h for details")
            task_to_deploy = SdkDeployTask.default()

    if not sdk_deployer.deploy(task_to_deploy):
        return 1


def _clean(args):
    sdk_deployer = UfbtSdkDeployer(args.ufbt_dir)
    if args.purge:
        log.info(f"Cleaning complete ufbt state in {sdk_deployer.ufbt_state_dir}")
        shutil.rmtree(sdk_deployer.ufbt_state_dir, ignore_errors=True)
        log.info("Done")
        return

    if args.downloads:
        log.info(f"Cleaning download dir {sdk_deployer.download_dir}")
        shutil.rmtree(sdk_deployer.download_dir, ignore_errors=True)
    else:
        log.info(f"Cleaning SDK state in {sdk_deployer.current_sdk_dir}")
        shutil.rmtree(sdk_deployer.current_sdk_dir, ignore_errors=True)
    log.info("Done")


def main():
    root_parser = argparse.ArgumentParser()
    root_parser.add_argument(
        "--no-check-certificate",
        help="Disable SSL certificate verification",
        action="store_true",
        default=False,
    )
    root_parser.add_argument(
        "--ufbt-dir",
        "-d",
        help="uFBT state directory",
        default=os.environ.get("UFBT_DIR", os.path.expanduser("~/.ufbt")),
    )
    root_parser.add_argument(
        "--force",
        "-f",
        help="Force download",
        action="store_true",
        default=False,
    )

    parsers = root_parser.add_subparsers()
    checkout_parser = parsers.add_parser("update")
    checkout_parser.set_defaults(func=_update)

    mode_group = checkout_parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument(
        "--url",
        "-u",
        help="URL to use",
    )
    mode_group.add_argument(
        "--branch",
        "-b",
        help="Branch to use",
    )
    mode_group.add_argument(
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
    checkout_parser.add_argument(
        "--hw-target",
        "-t",
        help="Hardware target",
    )
    checkout_parser.add_argument(
        "--index-url",
        help="URL to use for update channel",
    )

    clean_parser = parsers.add_parser("clean")
    clean_parser.add_argument(
        "--downloads",
        help="Clean downloads",
        action="store_true",
        default=False,
    )
    clean_parser.add_argument(
        "--purge",
        help="Purge whole ufbt state",
        action="store_true",
        default=False,
    )
    clean_parser.set_defaults(func=_clean)

    args = root_parser.parse_args()
    if args.no_check_certificate:
        # Temporary fix for SSL negotiation failure on Mac
        import ssl

        _ssl_context = ssl.create_default_context()
        _ssl_context.check_hostname = False
        _ssl_context.verify_mode = ssl.CERT_NONE
        BaseSdkLoader.SSL_CONTEXT = _ssl_context

    if "func" not in args:
        root_parser.print_help()
        return 1

    try:
        return args.func(args)

    except Exception as e:
        log.error(f"Failed to run operation: {e}")
        # raise
        return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
