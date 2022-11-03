from SCons.Platform import TempFileMunge

import os
import multiprocessing

DefaultEnvironment(tools=[])

EnsurePythonVersion(3, 8)

SetOption("num_jobs", multiprocessing.cpu_count())
SetOption("max_drift", 1)


ufbt_variables = SConscript("site_scons/commandline.scons")

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

if proxy_env := GetOption("proxy_env"):
    variables_to_forward.extend(proxy_env.split(","))

for env_value_name in variables_to_forward:
    if environ_value := os.environ.get(env_value_name, None):
        forward_os_env[env_value_name] = environ_value

# Core environment init - loads SDK state, sets up paths, etc.
core_env = Environment(
    variables=ufbt_variables,
    ENV=forward_os_env,
    tools=[
        "ufbt_state",
        ("ufbt_help", {"vars": ufbt_variables}),
    ],
)

# Now we can import stuff bundled with SDK - it was added to sys.path by ufbt_state

from fbt.util import (
    tempfile_arg_esc_func,
    single_quote,
    extract_abs_dir_path,
    wrap_tempfile,
)
from fbt.appmanifest import FlipperAppType

# Base environment with all tools loaded from SDK
env = core_env.Clone(
    toolpath=[core_env["FBT_SCRIPT_DIR"].Dir("fbt_tools")],
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
        "sconsrecursiveglob",
        "sconsmodular",
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
    TEMPFILE=TempFileMunge,
    MAXLINELENGTH=2048,
    PROGSUFFIX=".elf",
    TEMPFILEARGESCFUNC=tempfile_arg_esc_func,
    SINGLEQUOTEFUNC=single_quote,
    ABSPATHGETTERFUNC=extract_abs_dir_path,
    APPS=[],
)

wrap_tempfile(env, "LINKCOM")
wrap_tempfile(env, "ARCOM")

# print(env.Dump())

# Dist env

dist_env = env.Clone(
    tools=[
        "fbt_dist",
        "fbt_debugopts",
        "openocd",
        "blackmagic",
        "jflash",
    ],
    ENV=os.environ,
    OPENOCD_OPTS=[
        "-f",
        "interface/stlink.cfg",
        "-c",
        "transport select hla_swd",
        "-f",
        "${FBT_DEBUG_DIR}/stm32wbx.cfg",
        "-c",
        "stm32wbx.cpu configure -rtos auto",
    ],
)

openocd_target = dist_env.OpenOCDFlash(
    dist_env["UFBT_STATE_DIR"].File("flash"),
    dist_env["FW_BIN"],
    OPENOCD_COMMAND=[
        "-c",
        "program ${SOURCE.posix} reset exit 0x08000000",
    ],
)
dist_env.Alias("firmware_flash", openocd_target)
if env["FORCE"]:
    env.AlwaysBuild(openocd_target)

firmware_debug = dist_env.PhonyTarget(
    "debug",
    "${GDBPYCOM}",
    source=dist_env["FW_ELF"],
    GDBOPTS="${GDBOPTS_BASE}",
    GDBREMOTE="${OPENOCD_GDB_PIPE}",
)

flash_usb_full = dist_env.UsbInstall(
    dist_env["UFBT_STATE_DIR"].File("usbinstall"),
    [],
)
dist_env.AlwaysBuild(flash_usb_full)
dist_env.Alias("flash_usb", flash_usb_full)
dist_env.Alias("flash_usb_full", flash_usb_full)

# App build environment

appenv = env.Clone(
    CCCOM=env["CCCOM"].replace("$CFLAGS", "$CFLAGS_APP $CFLAGS"),
    CXXCOM=env["CXXCOM"].replace("$CXXFLAGS", "$CXXFLAGS_APP $CXXFLAGS"),
    LINKCOM=env["LINKCOM"].replace("$LINKFLAGS", "$LINKFLAGS_APP $LINKFLAGS"),
)


app_mount_point = Dir("#/app/")
app_mount_point.addRepository(Dir(appenv.subst("$UFBT_APP_DIR")))

appenv.LoadAppManifest(app_mount_point)
appenv.PrepareApplicationsBuild()

# print(appenv["APPMGR"].known_apps)

#######################


extapps = appenv["_extapps"] = {
    "compact": {},
    "debug": {},
    "validators": {},
    "dist": {},
    "installers": {},
    "resources_dist": None,
}


def build_app_as_external(env, appdef):
    compact_elf, debug_elf, validator = env.BuildAppElf(appdef)
    extapps["compact"][appdef.appid] = compact_elf
    extapps["debug"][appdef.appid] = debug_elf
    extapps["validators"][appdef.appid] = validator
    extapps["dist"][appdef.appid] = (appdef.fap_category, compact_elf)
    extapps["installers"][appdef.appid] = Install(
        env.subst("$UFBT_APP_DIR/dist/"), compact_elf
    )


apps_to_build_as_faps = [
    FlipperAppType.PLUGIN,
    FlipperAppType.EXTERNAL,
]

for apptype in apps_to_build_as_faps:
    for app in appenv["APPBUILD"].get_apps_of_type(apptype, True):
        build_app_as_external(appenv, app)


if appenv["FORCE"]:
    appenv.AlwaysBuild(extapps["compact"].values())


# Final steps - target aliases

Alias("faps", extapps["compact"].values())
Alias("faps", extapps["validators"].values())
Alias("faps", extapps["installers"].values())

Default(extapps["installers"].values())


# if appsrc := appenv.subst("$APPSRC"):
#     app_manifest, fap_file, app_validator = appenv.GetExtAppFromPath(appsrc)
#     appenv.PhonyTarget(
#         "launch_app",
#         '${PYTHON3} scripts/runfap.py ${SOURCE} --fap_dst_dir "/ext/apps/${FAP_CATEGORY}"',
#         source=fap_file,
#         FAP_CATEGORY=app_manifest.fap_category,
#     )
#     appenv.Alias("launch_app", app_validator)
