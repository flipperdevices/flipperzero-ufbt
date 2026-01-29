from .clean import CleanSubcommand
from .local_env import LocalEnvSubcommand
from .status import StatusSubcommand
from .update import UpdateSubcommand

ALL = (
    UpdateSubcommand,
    CleanSubcommand,
    StatusSubcommand,
    LocalEnvSubcommand,
)

ALL_NAMES = tuple(subcommand_cls.COMMAND for subcommand_cls in ALL)
