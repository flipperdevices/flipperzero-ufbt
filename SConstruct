import os

default_env = DefaultEnvironment(tools=[])

EnsurePythonVersion(3, 8)

ufbt_work_dir = Dir(os.environ.get("UFBT_WORK_DIR", "#.ufbt"))

ufbt_code_ep = ufbt_work_dir.File("current/scripts/ufbt/ufbt_impl.scons")

if not ufbt_code_ep.exists():
    print(
        f"UFBT code not found at {ufbt_code_ep}. Are you trying to use an old version of SDK?"
    )
    print(
        f"Try running `cd {Dir('#').abspath}; python3 bootstrap.py --force --channel=dev`"
    )
    Exit(1)

SConscript(
    ufbt_code_ep,
    exports="ufbt_work_dir",
    must_exist=True,
)
