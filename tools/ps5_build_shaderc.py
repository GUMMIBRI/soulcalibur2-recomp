#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build pinned public shaderc sources as PS5 static libraries; never run target code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'platform/ps5/shaderc/sources.json'
PRIVATE = ROOT / 'private/ps5-shaderc'

def fetch(item):
    target = PRIVATE / 'source' / item['path']
    archive = PRIVATE / (item['name'] + '.tar.gz')
    url = 'https://codeload.github.com/' + item['repo'] + '/tar.gz/' + item['revision']
    if not archive.exists():
        # Partial downloads never acquire the final, trusted archive name.
        temporary = archive.with_suffix('.download')
        try:
            with urllib.request.urlopen(url, timeout=90) as response, temporary.open('wb') as output:
                while block := response.read(1024 * 1024): output.write(block)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('archive hash mismatch: ' + item['name'])
            os.replace(temporary, archive)
        finally:
            temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != item['sha256']: raise ValueError('archive hash mismatch: ' + item['name'])
    marker = target / '.sc2-verified-source.json'
    expected = dict(revision=item['revision'], archive_sha256=digest)
    if marker.is_file():
        if json.loads(marker.read_text()) != expected:
            raise ValueError('source tree belongs to another compiler revision: ' + str(target))
    else:
        target.mkdir(parents=True, exist_ok=True)
        # Resume safely after interruption: check every existing file against its
        # archived bytes, extract only missing files, and stamp only on completion.
        with tarfile.open(archive) as bundle:
            if sum(m.size for m in bundle.getmembers()) > 512 * 1024 * 1024:
                raise ValueError('compiler source archive exceeds extraction limit')
            for member in bundle.getmembers():
                parts = Path(member.name).parts
                if len(parts) < 2: continue
                relative = Path(*parts[1:])
                if relative.is_absolute() or '..' in relative.parts or not (member.isfile() or member.isdir()):
                    raise ValueError('unsafe source archive member')
                destination = target / relative
                if destination.resolve() != destination.absolute():
                    raise ValueError('source extraction traverses a symlink or junction')
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                data = bundle.extractfile(member).read()
                if destination.exists():
                    if not destination.is_file() or destination.read_bytes() != data:
                        raise ValueError('incomplete or modified compiler source: ' + str(destination))
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open('xb') as output: output.write(data)
        marker.write_text(json.dumps(expected, indent=2) + '\n')
    return dict(name=item['name'], revision=item['revision'], archive_sha256=digest, url=url)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--llvm', required=True, type=Path)
    parser.add_argument('--cmake', required=True, type=Path)
    parser.add_argument('--ninja', required=True, type=Path)
    parser.add_argument('--fetch', action='store_true', help='allow official pinned compiler source downloads')
    parser.add_argument('--jobs', type=int, default=4)
    args=parser.parse_args()
    if not 1 <= args.jobs <= 8: parser.error('--jobs must be 1..8')
    PRIVATE.mkdir(parents=True, exist_ok=True)
    lock=json.loads(LOCK.read_text())
    sources=[]
    for item in lock['sources']:
        if not args.fetch and not (PRIVATE / (item['name'] + '.tar.gz')).is_file():
            parser.error('sources missing; explicit --fetch is required')
        sources.append(fetch(item))
    sdk,llvm=args.sdk.resolve(),args.llvm.resolve()
    for path in [sdk/'target/include/c++/v1/string',llvm/'clang++.exe',llvm/'llvm-ar.exe',args.cmake,args.ninja]:
        if not path.is_file(): parser.error('missing tool/input: '+str(path))
    build=PRIVATE/'build'
    environment=dict(os.environ)
    command=[str(args.cmake.resolve()),'-G','Ninja','-S',str(PRIVATE/'source'),'-B',str(build),
             '-DCMAKE_TOOLCHAIN_FILE='+str(ROOT/'platform/ps5/shaderc/toolchain.cmake'),
             '-DSC2_SHADERC_SDK='+sdk.as_posix(),'-DSC2_SHADERC_LLVM='+llvm.as_posix(),
             '-DCMAKE_MAKE_PROGRAM='+args.ninja.resolve().as_posix(),'-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_SKIP_INSTALL_RULES=ON',
             '-DSHADERC_SKIP_TESTS=ON','-DSHADERC_SKIP_EXAMPLES=ON','-DSHADERC_SKIP_EXECUTABLES=ON',
             '-DSHADERC_SKIP_COPYRIGHT_CHECK=ON','-DSHADERC_SKIP_INSTALL=ON','-DSHADERC_ENABLE_WERROR_COMPILE=OFF',
             '-DSPIRV_SKIP_TESTS=ON','-DSPIRV_SKIP_EXECUTABLES=ON','-DENABLE_GLSLANG_BINARIES=OFF',
             '-DENABLE_SPVREMAPPER=OFF','-DGLSLANG_TESTS=OFF','-DBUILD_TESTING=OFF']
    receipt=dict(sources=sources,configure_command=command,executed=False,
                 target='x86_64-sie-ps5',sdk=str(sdk),llvm=str(llvm),
                 header_directory=str(PRIVATE/'source/libshaderc/include'),
                 toolchain_sha256=hashlib.sha256((ROOT/'platform/ps5/shaderc/toolchain.cmake').read_bytes()).hexdigest())
    try:
        for label,cmd in [('configure',command),('build',[str(args.cmake.resolve()),'--build',str(build),'--parallel',str(args.jobs),'--target','shaderc_combined'])]:
            with (PRIVATE/(label+'.log')).open('w',encoding='utf-8') as log:
                result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=environment)
            receipt[label+'_exit_code']=result.returncode
            if result.returncode: raise RuntimeError(label+' failed; see '+str(PRIVATE/(label+'.log')))
        receipt['libraries']=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in build.rglob('*.a')]
        print('Built target static libraries; not linked into the game or executed.')
    finally:
        (PRIVATE/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__': main()
