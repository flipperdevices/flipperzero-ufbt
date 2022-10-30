@echo off

if not exist "%~dp0\.ufbt" (
    echo "Bootstrapping ubt...""    
    python "%~dp0\bootstrap.py" --branch hedger/fbt-mfbt-pt2
)

call "%~dp0\.ufbt\current\scripts\toolchain\fbtenv.cmd" env

set SCONS_EP=python -m SCons

set "SCONS_DEFAULT_FLAGS=-Q --warn=target-not-built"
%SCONS_EP% %SCONS_DEFAULT_FLAGS% %*
