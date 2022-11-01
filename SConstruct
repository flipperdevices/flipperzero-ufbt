from SCons.Platform import TempFileMunge
from fbt.util import (
    tempfile_arg_esc_func,
    single_quote,
    extract_abs_dir_path,
    wrap_tempfile,
)
from fbt.appmanifest import FlipperAppType

import os
import multiprocessing
import json
from functools import reduce

DefaultEnvironment(tools=[])

EnsurePythonVersion(3, 8)

SetOption("num_jobs", multiprocessing.cpu_count())
SetOption("max_drift", 1)


ufbt_variables = Variables("ufbt_options.py", ARGUMENTS)

ufbt_variables.AddVariables(
    PathVariable(
        "UFBT_APP_DIR",
        help="Application dir to work with",
        validator=PathVariable.PathIsDir,
        default="",
    )
)


sdk_root = Dir("#.ufbt/current/sdk")
sdk_data = {}
with open(".ufbt/current/sdk/sdk.opts") as f:
    sdk_json_data = json.load(f)
    replacements = {
        sdk_json_data["app_ep_subst"]: "${APP_ENTRY}",
        sdk_json_data["sdk_path_subst"]: sdk_root.path.replace("\\", "/"),
    }

    for key, value in sdk_json_data.items():
        if key in ("cc_args", "cpp_args", "linker_args", "linker_libs", "sdk_symbols"):
            sdk_data[key] = reduce(
                lambda a, kv: a.replace(*kv), replacements.items(), value
            ).split(" ")
        else:
            sdk_data[key] = value

forward_os_env = {
    # Import PATH from OS env - scons doesn't do that by default
    "PATH": os.environ["PATH"],
}

# Proxying environment to child processes & scripts
variables_to_forward = [
    # CI/CD variables
    "WORKFLOW_BRANCH_OR_TAG",
    "DIST_SUFFIX",
    # Python & other tools
    "HOME",
    "APPDATA",
    "PYTHONHOME",
    "PYTHONNOUSERSITE",
    "TMP",
    "TEMP",
    # Colors for tools
    "TERM",
]
# FIXME
# if proxy_env := GetOption("proxy_env"):
#     variables_to_forward.extend(proxy_env.split(","))

for env_value_name in variables_to_forward:
    if environ_value := os.environ.get(env_value_name, None):
        forward_os_env[env_value_name] = environ_value


env = Environment(
    variables=ufbt_variables,
    ENV=forward_os_env,
    toolpath=["#.ufbt/current/scripts/fbt_tools"],
    tools=[
        "fbt_tweaks",
        (
            "crosscc",
            {
                "toolchain_prefix": "arm-none-eabi-",
                "versions": (" 10.3",),
            },
        ),
        "fwbin",
        "python3",
        "sconsmodular",
        "sconsrecursiveglob",
        "ccache",
        "fbt_apps",
        (
            "fbt_extapps",
            {
                "EXT_APPS_WORK_DIR": "#.ufbt/build",
            },
        ),
        "fbt_assets",
    ],
    VERBOSE=False,
    # VERBOSE=True,
    FORCE=False,
    TEMPFILE=TempFileMunge,
    MAXLINELENGTH=2048,
    PROGSUFFIX=".elf",
    TEMPFILEARGESCFUNC=tempfile_arg_esc_func,
    SINGLEQUOTEFUNC=single_quote,
    ABSPATHGETTERFUNC=extract_abs_dir_path,
    FBT_SCRIPT_DIR=Dir("#.ufbt/current/scripts"),
    ROOT_DIR=Dir("#"),
    FIRMWARE_BUILD_CFG="firmware",
    SDK_DEFINITION=File(f"#{sdk_data['sdk_symbols'][0]}"),
    TARGET_HW=int(sdk_data["hardware"]),
    CFLAGS_APP=sdk_data["cc_args"],
    CXXFLAGS_APP=sdk_data["cpp_args"],
    LINKFLAGS_APP=sdk_data["linker_args"],
    LIBS=sdk_data["linker_libs"],
    LIBPATH=Dir("#.ufbt/current/lib"),
    APPS=[],
)

wrap_tempfile(env, "LINKCOM")
wrap_tempfile(env, "ARCOM")

env["CCCOM"] = env["CCCOM"].replace("$CFLAGS", "$CFLAGS_APP $CFLAGS")
env["CXXCOM"] = env["CXXCOM"].replace("$CXXFLAGS", "$CXXFLAGS_APP $CXXFLAGS")
env["LINKCOM"] = env["LINKCOM"].replace("$LINKFLAGS", "$LINKFLAGS_APP $LINKFLAGS")


# print(env.Dump())

app_mount_point = Dir("#/app/")
app_mount_point.addRepository(Dir(env.subst("$UFBT_APP_DIR")))

env.LoadAppManifest(app_mount_point)
env.PrepareApplicationsBuild()

# print(env["APPMGR"].known_apps)

#######################


appenv = env.Clone()


extapps = appenv["_extapps"] = {
    "compact": {},
    "debug": {},
    "validators": {},
    "dist": {},
    "resources_dist": None,
}


def build_app_as_external(env, appdef):
    compact_elf, debug_elf, validator = env.BuildAppElf(appdef)
    extapps["compact"][appdef.appid] = compact_elf
    extapps["debug"][appdef.appid] = debug_elf
    extapps["validators"][appdef.appid] = validator
    extapps["dist"][appdef.appid] = (appdef.fap_category, compact_elf)


apps_to_build_as_faps = [
    FlipperAppType.PLUGIN,
    FlipperAppType.EXTERNAL,
]

for apptype in apps_to_build_as_faps:
    for app in appenv["APPBUILD"].get_apps_of_type(apptype, True):
        build_app_as_external(appenv, app)


if appenv["FORCE"]:
    appenv.AlwaysBuild(extapps["compact"].values())

Alias("faps", extapps["compact"].values())
Alias("faps", extapps["validators"].values())

Default(extapps["validators"].values())


# if appsrc := appenv.subst("$APPSRC"):
#     app_manifest, fap_file, app_validator = appenv.GetExtAppFromPath(appsrc)
#     appenv.PhonyTarget(
#         "launch_app",
#         '${PYTHON3} scripts/runfap.py ${SOURCE} --fap_dst_dir "/ext/apps/${FAP_CATEGORY}"',
#         source=fap_file,
#         FAP_CATEGORY=app_manifest.fap_category,
#     )
#     appenv.Alias("launch_app", app_validator)
