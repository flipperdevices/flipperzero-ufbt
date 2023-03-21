@echo off

if not defined UFBT_STATE_DIR (
    set UFBT_STATE_DIR=%userprofile%\.ufbt
)

if not exist "%UFBT_STATE_DIR%\current" (
    echo Bootstrapping ufbt...
    python "%~dp0\bootstrap.py" "--ufbt-dir=%UFBT_STATE_DIR%" --channel dev
)

set "FBT_TOOLCHAIN_ROOT=%UFBT_STATE_DIR%\toolchain\x86_64-windows"

call "%UFBT_STATE_DIR%\current\scripts\toolchain\fbtenv.cmd" env

set SCONS_EP=python -m SCons
set UFBT_ROOT_DIR="%~dp0."

set "SCONS_DEFAULT_FLAGS=-Q --warn=target-not-built -C %UFBT_ROOT_DIR%"
%SCONS_EP% %SCONS_DEFAULT_FLAGS% UFBT_APP_DIR="%cd%" %*
