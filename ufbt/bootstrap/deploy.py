import argparse
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Dict, Optional
from zipfile import ZipFile

from .paths import STATE_DIR_TOOLCHAIN_SUBDIR

from .sdk_loader import (
    SdkLoaderFactory,
    UpdateChannelSdkLoader,
    ALL,
)

log = logging.getLogger(__name__)


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
        task.hw_target = args.hw_target
        task.force = args.force
        for loader_cls in ALL:
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


class UfbtSdkDeployer:
    UFBT_STATE_FILE_NAME = "ufbt_state.json"

    def __init__(self, ufbt_state_dir: str, toolchain_dir: str = None):
        self.ufbt_state_dir = Path(ufbt_state_dir)
        self.download_dir = self.ufbt_state_dir / "download"
        self.current_sdk_dir = self.ufbt_state_dir / "current"
        if toolchain_dir:
            self.toolchain_dir = self.ufbt_state_dir / toolchain_dir
        else:
            self.toolchain_dir = (
                Path(
                    os.environ.get("FBT_TOOLCHAIN_PATH", self.ufbt_state_dir.absolute())
                )
                / STATE_DIR_TOOLCHAIN_SUBDIR
            )
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
                log.info("Cannot determine current SDK version, updating")
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

        log.info("Deploying SDK")

        with ZipFile(sdk_component_path, "r") as zip_file:
            zip_file.extractall(sdk_target_dir)

        with open(self.state_file, "w") as f:
            json.dump(ufbt_state, f, indent=4)

        log.info("SDK deployed.")
        return True
