#!/usr/bin/env python3
"""Portable skill launcher. Bootstrap only on explicit setup; no repo lookup.

analyze / doctor / from-project run the bundled Python runtime. plan / export /
brief run the bundled rallycut-cli binary (same timeline and FFmpeg export code
as the desktop app) and need only FFmpeg, not PyTorch or model weights.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'assets/runtime'


def emit(document, error=False):
    print(json.dumps(document,ensure_ascii=False),file=sys.stderr if error else sys.stdout)


def environment():
    manifest=RUNTIME/'runtime-manifest.json'
    if not manifest.is_file():
        raise ValueError('Missing bundled runtime. Install the packaged skill folder (build/skills/rallycut-video-json), not the source template; build with just skill.')
    data=json.loads(manifest.read_text(encoding='utf-8'))
    for relative,expected in data['files'].items():
        path=RUNTIME/relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError(f'Bundled runtime checksum mismatch: {relative}; reinstall skill')
    root=os.environ.get('RALLYCUT_SKILL_HOME')
    if root:
        home=Path(root).expanduser().resolve()
    elif sys.platform=='darwin':
        home=Path.home()/'Library/Caches/rallycut-video-json'
    else:
        home=Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'rallycut-video-json'
    venv=home/'runtimes'/data['digest'][:16]/'venv'
    python=Path(os.environ.get('RALLYCUT_SKILL_PYTHON',str(venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')))).expanduser().absolute()
    weights=Path(os.environ.get('RALLYCUT_MODEL_PATH',str(home/'models/blurball_best.pth'))).expanduser().absolute()
    return home,venv,python,weights,data['digest']


TOOL_COMMANDS=('plan','export','brief')


def tool():
    """Verified rallycut-cli for this OS / CPU."""
    manifest=RUNTIME/'runtime-manifest.json'
    if not manifest.is_file():
        raise ValueError('Missing bundled runtime. Install the packaged skill folder (build/skills/rallycut-video-json), not the source template; build with just skill.')
    tools=json.loads(manifest.read_text(encoding='utf-8')).get('tools',{})
    goos={'darwin':'darwin','win32':'windows'}.get(sys.platform,'linux' if sys.platform.startswith('linux') else sys.platform)
    machine=platform.machine().lower()
    goarch={'x86_64':'amd64','amd64':'amd64','arm64':'arm64','aarch64':'arm64'}.get(machine,machine)
    relative=f'bin/{goos}-{goarch}/rallycut-cli'+('.exe' if goos=='windows' else '')
    if relative not in tools:
        raise ValueError(f'No bundled rallycut-cli for {goos}-{goarch}; supported: {", ".join(sorted(tools))}')
    path=ROOT/'assets'/relative
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=tools[relative]:
        raise ValueError(f'Bundled tool checksum mismatch: {relative}; reinstall skill')
    if os.name!='nt' and not os.access(path,os.X_OK):
        path.chmod(0o755)  # some skill installers drop the executable bit
    return path


def main():
    parser=argparse.ArgumentParser(description='Self-contained RallyCut skill: setup / doctor / analyze / from-project / plan / export / brief')
    parser.add_argument('command',choices=['setup','doctor','analyze','from-project',*TOOL_COMMANDS])
    args=parser.parse_args(sys.argv[1:2])
    remaining=sys.argv[2:]
    try:
        if args.command in TOOL_COMMANDS:
            binary=tool()
            if '--help' in remaining or '-h' in remaining:
                return subprocess.call([str(binary),args.command,'-h'])
            # exec: cancellation / timeouts reach the FFmpeg-owning process.
            if os.name=='nt':
                return subprocess.call([str(binary),args.command,*remaining])
            os.execv(str(binary),[str(binary),args.command,*remaining])
        home,venv,python,weights,digest=environment()
        if args.command=='setup':
            setup=argparse.ArgumentParser(description='Explicit dependency preparation; video is never uploaded')
            setup.add_argument('--with-decoder',action='store_true',help='install optional experimental PyAV/VideoToolbox decoder; not enabled automatically')
            setup.add_argument('--download-model',action='store_true',help='explicitly download official weights; redistribution license remains unconfirmed')
            options=setup.parse_args(remaining)
            uv=shutil.which('uv')
            if not uv:
                raise ValueError('uv is required for setup (https://docs.astral.sh/uv/). Install uv and FFmpeg, then rerun setup. Go/Node/Wails are not required.')
            if not os.environ.get('RALLYCUT_SKILL_PYTHON'):
                subprocess.run([uv,'venv','--allow-existing','--python','3.12',str(venv)],check=True,stdout=sys.stderr)
            elif not python.is_file():
                raise ValueError(f'explicit RALLYCUT_SKILL_PYTHON does not exist: {python}')
            install=[uv,'pip','install','--python',str(python),'-r',str(RUNTIME/'requirements-model.txt')]
            if sys.platform in ('linux','win32'):
                install.extend(['--torch-backend','cpu'])  # Inference has no CUDA backend; avoid multi-GB CUDA wheels.
            subprocess.run(install,check=True,stdout=sys.stderr)
            if options.with_decoder:
                subprocess.run([uv,'pip','install','--python',str(python),'-r',str(RUNTIME/'requirements-decode.txt')],check=True,stdout=sys.stderr)
            if options.download_model:
                subprocess.run([str(python),str(RUNTIME/'download_model.py'),'--output',str(weights)],check=True,stdout=sys.stderr)
            emit({'status':'prepared','python':str(python),'weights':str(weights),'weights_present':weights.is_file(),
                  'runtime_digest':digest,'next':'doctor','weight_redistribution_license':'unconfirmed'})
            return 0
        if '--help' in remaining or '-h' in remaining:
            return subprocess.call([sys.executable,str(RUNTIME/'headless.py'),args.command,'--help'])
        if not python.is_file() and args.command=='from-project' and not os.environ.get('RALLYCUT_SKILL_PYTHON'):
            python=Path(sys.executable).absolute()  # Existing projects need only stdlib + FFprobe.
        if not python.is_file():
            if args.command=='doctor':
                emit({'ready':False,'missing':['skill Python runtime'],'setup_required':True,
                      'command':[sys.executable,str(Path(__file__).resolve()),'setup','--download-model'],
                      'note':'setup is only needed to analyze new videos; plan / export / brief work without it (FFmpeg required)'})
                return 1
            raise ValueError('Skill runtime not prepared. Run this launcher with setup --download-model first; no automatic downloads are performed during analysis.')
        env=os.environ.copy()
        env['RALLYCUT_MODEL_PATH']=str(weights)
        env['PYTHONNOUSERSITE']='1'
        env['RALLYCUT_SKILL_RUNTIME_DIGEST']=digest
        # Replace the bootstrap process so timeout/cancellation signals reach the
        # actual inference process; it owns and cleans temporary FFmpeg children.
        os.execve(str(python),[str(python),str(RUNTIME/'headless.py'),args.command,*remaining],env)
    except KeyboardInterrupt:
        emit({'status':'cancelled'},error=True)
        return 130
    except Exception as error:
        emit({'status':'failed','error':str(error)},error=True)
        return 1


if __name__=='__main__':
    sys.exit(main())
