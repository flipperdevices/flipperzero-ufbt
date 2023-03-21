@echo off

if not defined UFBT_STATE_DIR (
    set UFBT_STATE_DIR=%userprofile%\.ufbt
)

set UFBT_SCRIPT_DIR=%~dp0.

rem Check if "purge" was passed in as an argument
for %%a in (%*) do (
    if "%%a"=="purge" (
        echo Cleaning up ufbt state dir: %UFBT_STATE_DIR%
        rmdir /s /q "%UFBT_STATE_DIR%"
        exit /b 0
    )
)

if not exist "%UFBT_STATE_DIR%\current" (
    echo Bootstrapping ufbt...
    python "%UFBT_SCRIPT_DIR%\bootstrap.py" --ufbt-dir="%UFBT_STATE_DIR%" --channel dev
)

if not exist "%UFBT_STATE_DIR%\current" (
    echo Failed to bootstrap ufbt.
    exit /b 1
)

if not exist "%UFBT_STATE_DIR%\current\scripts\ufbt" (
    echo Error: ufbt implementation not found in %UFBT_STATE_DIR%\current\scripts\ufbt
    echo You might be trying to use an SDK in an outdated format.
    echo You can try to bootstrap ufbt manually by running:
    echo     python "%UFBT_SCRIPT_DIR%\bootstrap.py" --ufbt-dir="%UFBT_STATE_DIR%" 
    exit /b 1
)

set "FBT_TOOLCHAIN_ROOT=%UFBT_STATE_DIR%\toolchain\x86_64-windows"

call "%UFBT_STATE_DIR%\current\scripts\toolchain\fbtenv.cmd" env

set SCONS_EP=python -m SCons


set "SCONS_DEFAULT_FLAGS=-Q --warn=target-not-built -C %UFBT_STATE_DIR%\current\scripts\ufbt"
%SCONS_EP% %SCONS_DEFAULT_FLAGS% UFBT_APP_DIR="%cd%" %*
