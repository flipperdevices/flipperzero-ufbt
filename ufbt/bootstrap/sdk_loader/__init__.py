import logging

from .base import BaseSdkLoader
from .branch import BranchSdkLoader
from .local import LocalSdkLoader
from .update_channel import UpdateChannelSdkLoader
from .url import UrlSdkLoader

log = logging.getLogger(__name__)

ALL = (
    BranchSdkLoader,
    UpdateChannelSdkLoader,
    UrlSdkLoader,
    LocalSdkLoader,
)


class SdkLoaderFactory:
    @staticmethod
    def create_for_task(task: "SdkDeployTask", download_dir: str) -> BaseSdkLoader:
        log.debug(f"SdkLoaderFactory::create_for_task {task=}")
        loader_cls = None
        for loader_cls in ALL:
            if loader_cls.LOADER_MODE_KEY == task.mode:
                break
        if loader_cls is None:
            raise ValueError(f"Invalid mode: {task.mode}")

        ctor_kwargs = loader_cls.metadata_to_init_kwargs(task.all_params)
        log.debug(f"SdkLoaderFactory::create_for_task {loader_cls=}, {ctor_kwargs=}")
        return loader_cls(download_dir, **ctor_kwargs)
