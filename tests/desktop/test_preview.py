#!/usr/bin/env python3
"""Run real WKWebView playback/seek against isolated copies of saved projects.

No Accessibility permission or browser mocks; source media stays read-only.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO=Path(__file__).resolve().parents[2]


def main():
    if sys.platform!='darwin':
        print('SKIP: macOS native WebKit test')
        return
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',action='append',type=Path,help='saved project; repeat to test several sources')
    args=parser.parse_args()
    projects=args.project
    if not projects:
        recent=Path.home()/'Library/Application Support/RallyCut/last-project.json'
        projects=[Path(json.loads(recent.read_text())['path'])]
    with tempfile.TemporaryDirectory(prefix='rallycut-native-media-') as directory:
        root=Path(directory)
        binary=root/'preview-smoke'
        env=os.environ.copy()
        env['CGO_LDFLAGS']=env.get('CGO_LDFLAGS','')+' -framework UniformTypeIdentifiers'
        subprocess.run(['go','build','-tags','desktop,production','-o',str(binary),'./tests/desktop/preview_smoke'],cwd=REPO,env=env,check=True)
        results=[]
        for index,project in enumerate(projects):
            home=root/f'home-{index}'
            config=home/'Library/Application Support/RallyCut'
            config.mkdir(parents=True,mode=0o700)
            saved=config/'20261024-152433-rallycut.json'
            shutil.copyfile(project,saved)
            (config/'last-project.json').write_text(json.dumps({'path':str(saved)}))
            isolated=env.copy();isolated['HOME']=str(home)
            run=subprocess.run([str(binary)],cwd=REPO,env=isolated,capture_output=True,text=True,timeout=50)
            records=[json.loads(line) for line in run.stdout.splitlines() if line.startswith('{"ok":')]
            if run.returncode or not records or not records[-1].get('ok'):
                raise AssertionError(f'native preview failed: {run.returncode}\n{run.stdout}\n{run.stderr}')
            expected=json.loads(saved.read_text())['video']['path']
            assert records[-1]['source']==expected
            results.append(records[-1])
        print(json.dumps({'status':'passed','native_preview':results},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
