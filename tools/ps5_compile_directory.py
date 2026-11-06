#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile the opaque directory boundary with the platform provider's SDK."""
import argparse
import json
import sys
from pathlib import Path
from ps5_compile_host import ROOT, compile_record, digest

PINNED_HEADERS = {
    'ps5platform/libc.h': '7bc041c0252bba75ca7578aaf46f080ef5539855a01f5c29b59f31a35b6b14e8',
    'dirent.h': '438f1342a822bdab93d51b9fd18dca73c9416b9be090323088f58cabf099dfe8',
    'sys/dirent.h': '8e43c428f51c19e6b32b23ea2460ab5774f52e7e0cdb04e4b51aa0c555e3b93b',
}

def validate_provider(platform):
    if (platform / '.ps5-sdk-revision').read_text().strip() != 'b83202be73e930050e00de0f1b4d9ec46c0391bf':
        raise ValueError('directory provider SDK revision mismatch')
    for name, expected in PINNED_HEADERS.items():
        if digest(platform / 'target/include' / name) != expected:
            raise ValueError('directory provider header mismatch: ' + name)

def bridge_command(platform, llvm):
    source = ROOT / 'runtime/sc2_native_directory.c'
    obj = ROOT / 'private/ps5-host-objects/sc2_native_directory.o'
    compiler = llvm / ('clang.exe' if sys.platform == 'win32' else 'clang')
    return [str(compiler), '--target=x86_64-sie-ps5', '-isysroot', str(platform),
            '-isystem', str(platform / 'target/include'), '-O2', '-std=c11',
            '-DSC2_PS5=1', '-fPIC', '-fno-stack-protector', '-femulated-tls',
            '-c', str(source), '-o', str(obj)]

def validate_bridge(row, llvm):
    command = row['command']
    platform = Path(command[command.index('-isysroot') + 1]).resolve()
    validate_provider(platform)
    if command != bridge_command(platform, llvm.resolve()):
        raise ValueError('directory bridge command differs from the reviewed ABI boundary')
    dependencies = {str(Path(d['path']).resolve()): d['sha256'] for d in row['dependencies']}
    for name, expected in PINNED_HEADERS.items():
        if dependencies.get(str((platform / 'target/include' / name).resolve())) != expected:
            raise ValueError('directory bridge receipt lacks pinned header: ' + name)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path, help='game SDK receipt identity')
    parser.add_argument('--platform-sdk', required=True, type=Path, help='SDK matching pinned libps5platform.a')
    parser.add_argument('--llvm', required=True, type=Path)
    args = parser.parse_args()
    sdk, platform, llvm = args.sdk.resolve(), args.platform_sdk.resolve(), args.llvm.resolve()
    header = platform / 'target/include/ps5platform/libc.h'
    if not header.is_file(): parser.error('platform SDK lacks directory provider header')
    source = ROOT / 'runtime/sc2_native_directory.c'
    out = ROOT / 'private/ps5-host-objects'
    out.mkdir(parents=True, exist_ok=True)
    obj = out / 'sc2_native_directory.o'
    validate_provider(platform)
    command = bridge_command(platform, llvm)
    # The game SDK remains the link admission identity. Actual provider SDK,
    # command and compiler-discovered headers are independently recorded.
    row = compile_record(source, obj, command, sdk, out / 'sc2_native_directory.log')
    report = dict(schema='sc2.ps5-directory-bridge.v1', platform_sdk=str(platform),
                  sdk=str(sdk), units=[row], executed=False)
    (out / 'receipt-directory.json').write_text(json.dumps(report, indent=2) + '\n')
    print('compiled directory bridge' if row['object'] else 'FAILED directory bridge')
    return row['exit_code']

if __name__ == '__main__':
    sys.exit(main())
