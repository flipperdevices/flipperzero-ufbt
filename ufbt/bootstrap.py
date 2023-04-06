###
# Bootstrap script for uFBT. Deploys SDK and metadata.
###

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
from typing import ClassVar, Dict, Optional
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from zipfile import ZipFile

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d [%(levelname).1s] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

##############################################################################


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
    def args_namespace_to_metadata(
        cls, namespace: argparse.Namespace
    ) -> Dict[str, str]:
        raise NotImplementedError()

    @classmethod
    def add_args_to_mode_group(cls, mode_group):
        raise NotImplementedError()


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
    def args_namespace_to_metadata(
        cls, namespace: argparse.Namespace
    ) -> Dict[str, str]:
        return {
            "branch": namespace.branch,
            "branch_root": namespace.index_url,
        }

    @classmethod
    def add_args_to_mode_group(cls, mode_group):
        mode_group.add_argument(
            "--branch",
            "-b",
            type=str,
            help="Branch to load SDK from",
        )


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
        self, download_dir: str, channel: UpdateChannel, index_html_url: str = None
    ):
        super().__init__(download_dir)
        self.channel = channel
        self.index_html_url = index_html_url or self.OFFICIAL_INDEX_URL
        self.version_info = self._fetch_version(self.channel)

    def _fetch_version(self, channel: UpdateChannel) -> dict:
        log.info(f"Fetching version info for {channel} from {self.index_html_url}")
        try:
            data = json.loads(
                self._open_url(self.index_html_url).read().decode("utf-8")
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
            raise ValueError(f"Empty files list")

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
            raise ValueError(f"Invalid file url")

        return self._fetch_file(file_url)

    def get_metadata(self) -> Dict[str, str]:
        return {
            "mode": self.LOADER_MODE_KEY,
            "channel": self.channel.name.lower(),
            "index_html": self.index_html_url,
            "version": self.version_info["version"],
        }

    @classmethod
    def metadata_to_init_kwargs(cls, metadata: dict) -> Dict[str, str]:
        return {
            "channel": UpdateChannelSdkLoader.UpdateChannel[
                metadata["channel"].upper()
            ],
            "index_html_url": metadata.get("index_html", None),
        }

    @classmethod
    def args_namespace_to_metadata(
        cls, namespace: argparse.Namespace
    ) -> Dict[str, str]:
        return {
            "channel": namespace.channel,
            "index_html": namespace.index_url,
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
    def args_namespace_to_metadata(
        cls, namespace: argparse.Namespace
    ) -> Dict[str, str]:
        return {"url": namespace.url}

    @classmethod
    def add_args_to_mode_group(cls, mode_group):
        mode_group.add_argument(
            "--url",
            "-u",
            type=str,
            help="Direct URL to load SDK from",
        )


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
        return {"file_path": args.local}

    @classmethod
    def add_args_to_mode_group(cls, mode_group):
        mode_group.add_argument(
            f"--local",
            f"-l",
            type=str,
            help="Path to local SDK zip file",
        )


all_boostrap_loader_cls = (
    BranchSdkLoader,
    UpdateChannelSdkLoader,
    UrlSdkLoader,
    LocalSdkLoader,
)


##############################################################################


@dataclass
class SdkDeployTask:
    """
    Wrapper for SDK deploy task parameters.
    """

    hw_target: str = None
    force: bool = False
    mode: str = None
    all_params: Dict[str, str] = field(default_factory=dict)

    DEFAULT_HW_TARGET: ClassVar[str] = "f7"

    def update_from(self, other: "SdkDeployTask") -> None:
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
    def default() -> "SdkDeployTask":
        task = SdkDeployTask()
        task.hw_target = SdkDeployTask.DEFAULT_HW_TARGET
        task.mode = "channel"
        task.all_params["channel"] = UpdateChannelSdkLoader.UpdateChannel.RELEASE.value
        return task

    @staticmethod
    def from_args(args: argparse.Namespace) -> "SdkDeployTask":
        task = SdkDeployTask()
        task.hw_target = args.hw_target or SdkDeployTask.DEFAULT_HW_TARGET
        task.force = args.force
        for loader_cls in all_boostrap_loader_cls:
            task.all_params.update(loader_cls.args_namespace_to_metadata(args))
            if getattr(args, loader_cls.LOADER_MODE_KEY):
                task.mode = loader_cls.LOADER_MODE_KEY
                break
        log.debug(f"deploy task from args: {task=}")
        return task

    @staticmethod
    def from_dict(data: Dict[str, str]) -> "SdkDeployTask":
        task = SdkDeployTask()
        task.hw_target = data.get("hw_target")
        task.force = False
        task.mode = data.get("mode")
        task.all_params = data
        return task


class SdkLoaderFactory:
    @staticmethod
    def create_for_task(task: SdkDeployTask, download_dir: str) -> BaseSdkLoader:
        log.debug(f"SdkLoaderFactory::create_for_task {task=}")
        loader_cls = None
        for loader_cls in all_boostrap_loader_cls:
            if loader_cls.LOADER_MODE_KEY == task.mode:
                break
        if loader_cls is None:
            raise ValueError(f"Invalid mode: {task.mode}")

        ctor_kwargs = loader_cls.metadata_to_init_kwargs(task.all_params)
        log.debug(f"SdkLoaderFactory::create_for_task {loader_cls=}, {ctor_kwargs=}")
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

    def deploy(self, task: SdkDeployTask) -> bool:
        log.info(f"Deploying SDK for {task.hw_target}")
        sdk_loader = SdkLoaderFactory.create_for_task(task, self.download_dir)

        sdk_target_dir = self.current_sdk_dir.absolute()
        log.info(f"uFBT SDK dir: {sdk_target_dir}")
        if not task.force and os.path.exists(sdk_target_dir):
            # Read existing state
            with open(self.state_file, "r") as f:
                ufbt_state = json.load(f)
            # Check if we need to update
            if ufbt_state.get("version") in sdk_loader.ALWAYS_UPDATE_VERSIONS:
                log.info("Cannot determine SDK version, updating")
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


###############################################################################


class CliSubcommand:
    def __init__(self, name: str, help: str):
        self.name = name
        self.help = help

    def add_to_parser(self, parser: argparse.ArgumentParser):
        subparser = parser.add_parser(self.name, help=self.help)
        subparser.set_defaults(func=self._func)
        self._add_arguments(subparser)

    def _func(args) -> int:
        raise NotImplementedError

    def _add_arguments(self, parser: argparse.ArgumentParser) -> None:
        raise NotImplementedError


class UpdateSubcommand(CliSubcommand):
    COMMAND = "update"

    def __init__(self):
        super().__init__(self.COMMAND, "Update uFBT SDK")

    def _add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--hw-target",
            "-t",
            help="Hardware target",
        )
        parser.add_argument(
            "--index-url",
            help="URL to use for SDK discovery",
        )
        mode_group = parser.add_mutually_exclusive_group(required=False)
        for loader_cls in all_boostrap_loader_cls:
            loader_cls.add_args_to_mode_group(mode_group)

    def _func(self, args) -> int:
        sdk_deployer = UfbtSdkDeployer(args.ufbt_home)
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
                task_to_deploy = SdkDeployTask.default()

        if not sdk_deployer.deploy(task_to_deploy):
            return 1
        return 0


class CleanSubcommand(CliSubcommand):
    COMMAND = "clean"

    def __init__(self):
        super().__init__(self.COMMAND, "Clean uFBT SDK state")

    def _add_arguments(self, parser: argparse.ArgumentParser):
        parser.add_argument(
            "--downloads",
            help="Clean downloads",
            action="store_true",
            default=False,
        )
        parser.add_argument(
            "--purge",
            help="Purge whole ufbt state",
            action="store_true",
            default=False,
        )

    def _func(self, args) -> int:
        sdk_deployer = UfbtSdkDeployer(args.ufbt_home)
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
        return 0


class StatusSubcommand(CliSubcommand):
    COMMAND = "status"

    def __init__(self):
        super().__init__(self.COMMAND, "Show uFBT SDK status")

    def _add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def _func(self, args) -> int:
        sdk_deployer = UfbtSdkDeployer(args.ufbt_home)
        log.info(f"State dir     {sdk_deployer.ufbt_state_dir}")
        log.info(f"Download dir  {sdk_deployer.download_dir}")
        log.info(f"SDK dir       {sdk_deployer.current_sdk_dir}")
        if previous_task := sdk_deployer.get_previous_task():
            log.info(f"Target        {previous_task.hw_target}")
            log.info(f"Mode          {previous_task.mode}")
            log.info(
                f"Version       {previous_task.all_params.get('version', BaseSdkLoader.VERSION_UNKNOWN)}"
            )
            log.info(f"Details       {previous_task.all_params}")
            return 0
        else:
            log.error("SDK is not deployed")
            return 1


bootstrap_subcommand_classes = (UpdateSubcommand, CleanSubcommand, StatusSubcommand)

bootstrap_subcommands = (
    subcommand_cls.COMMAND for subcommand_cls in bootstrap_subcommand_classes
)


def bootstrap_cli() -> Optional[int]:
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
        default=os.environ.get("UFBT_HOME", os.path.expanduser("~/.ufbt")),
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
    for subcommand_cls in bootstrap_subcommand_classes:
        subcommand_cls().add_to_parser(parsers)

    args = root_parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

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
        log.error(f"Failed to run operation: {e}. See --verbose for details")
        if args.verbose:
            raise
        return 2


if __name__ == "__main__":
    sys.exit(bootstrap_cli() or 0)
