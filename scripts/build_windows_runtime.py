"""Build our own relocatable Windows x64 runtime; never distribute model weights.
Run only on a Windows release runner. Produces a pinned ZIP, a dependency lock,
source/license notices and the catalog embedded in that run's desktop binary.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/runtime-output'
STAGE = ROOT / 'build/runtime-stage'
VERSION = os.environ.get('VERSION', '0.1.0-alpha.3-windows.5')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def fetch(spec, dest):
    req=urllib.request.Request(spec['url'],headers={'User-Agent':'RallyCut-runtime-builder'})
    with urllib.request.urlopen(req,timeout=180) as r, dest.open('wb') as f:shutil.copyfileobj(r,f)
    if dest.stat().st_size!=spec['bytes'] or sha(dest)!=spec['sha256']:raise RuntimeError('Artifact checksum mismatch: '+spec['url'])


def run(args, **kwargs):
    print('RUN',*map(str,args),flush=True)
    subprocess.run(list(map(str,args)),check=True,env={**os.environ,'UV_NATIVE_TLS':'true','PYTHONNOUSERSITE':'1'},**kwargs)


def x64(path):
    with path.open('rb') as f:
        if f.read(2)!=b'MZ':return False
        f.seek(0x3c);offset=struct.unpack('<I',f.read(4))[0];f.seek(offset)
        return f.read(4)==b'PE\0\0' and struct.unpack('<H',f.read(2))[0]==0x8664


def main():
    if sys.platform!='win32':raise RuntimeError('Windows release runner required')
    if not VERSION.replace('-','').replace('.','').isalnum():raise RuntimeError('Invalid version')
    OUT.mkdir(parents=True,exist_ok=True)
    if STAGE.exists():shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    (STAGE/'bin').mkdir();(STAGE/'notices').mkdir()
    catalog=json.loads((ROOT/'backend/setup/artifacts.json').read_text())
    target=catalog['platforms']['windows/amd64']
    with tempfile.TemporaryDirectory(prefix='rallycut-builder-') as tmp:
        tmp=Path(tmp);uvzip=tmp/'uv.zip';fetch(target['uv'],uvzip)
        with zipfile.ZipFile(uvzip) as z:
            member=next(n for n in z.namelist() if Path(n).name=='uv.exe')
            uv=tmp/'uv.exe';uv.write_bytes(z.read(member))
        run([uv,'python','install',catalog['python_version'],'--install-dir',tmp/'python','--no-bin','--no-registry','--no-config'])
        installed=next((tmp/'python').glob('cpython-*/python.exe')).parent
        shutil.copytree(installed,STAGE/'python')
        python=STAGE/'python/python.exe'
        # CPU wheels avoid shipping a CUDA toolchain; this does not change the
        # detector, checkpoint, preprocessing or FP32 inference semantics.
        inputs=tmp/'runtime.in'
        inputs.write_text((ROOT/'vision/requirements.txt').read_text()+'\ntorch==2.8.0+cpu\n')
        lock=STAGE/'notices/requirements-windows.lock'
        run([uv,'pip','compile',inputs,'--python-version','3.12','--generate-hashes','--extra-index-url','https://download.pytorch.org/whl/cpu','--index-strategy','unsafe-best-match','--output-file',lock])
        run([uv,'pip','install','--python',python,'--target',STAGE/'python/Lib/site-packages','--require-hashes','--no-deps','--requirement',lock,'--extra-index-url','https://download.pytorch.org/whl/cpu','--index-strategy','unsafe-best-match'])
        for name in ['ffmpeg','ffprobe']:
            gz=tmp/(name+'.gz');fetch(target[name],gz)
            with gzip.open(gz,'rb') as src,(STAGE/'bin'/(name+'.exe')).open('wb') as dst:shutil.copyfileobj(src,dst)
        for name,spec in target['notices'].items():fetch(spec,STAGE/'notices'/name)
        # Use licensed app-local redistributables from the Visual Studio redist
        # directory, not arbitrary DLLs copied out of Windows System32.
        base=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Microsoft Visual Studio'
        candidates=list(base.glob('*/Enterprise/VC/Redist/MSVC/*/x64/Microsoft.VC*.CRT'))
        if not candidates:raise RuntimeError('Visual C++ x64 app-local redistributable not found')
        crt=sorted(candidates)[-1]
        dlls=list(crt.glob('*.dll'))
        if not {'vcruntime140_1.dll','msvcp140.dll'} <= {p.name.lower() for p in dlls}:raise RuntimeError('Missing x64 Visual C++ runtime DLLs')
        for dll in dlls:
            if not x64(dll):raise RuntimeError('Not an x64 redist DLL: '+str(dll))
            shutil.copy2(dll,STAGE/'python'/dll.name)
        licenses=list(crt.parents[3].glob('**/license*.txt'))+list(crt.parents[3].glob('**/License*.txt'))
        # The Visual Studio license URL is recorded too; do not claim that an
        # arbitrary OS DLL is redistributable merely because it can be copied.
        (STAGE/'notices/visual-cpp-redist.txt').write_text('App-local x64 Visual C++ CRT from licensed Visual Studio redistributables.\nhttps://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files\nSource directory: '+str(crt.relative_to(base))+'\n',encoding='utf-8')
        if licenses:shutil.copy2(licenses[0],STAGE/'notices/visual-cpp-license.txt')
        run([python,'-I','-c','import sys,torch,numpy,cv2; print(sys.version,torch.__version__); assert torch.from_numpy(numpy.zeros((1,),dtype=numpy.float32)).numpy().shape==(1,)'])
        for tool in ['ffmpeg','ffprobe']:run([STAGE/'bin'/(tool+'.exe'),'-version'])
    # C++ extension-build headers are not used by our fixed eager FP32 model.
    # Excluding them also avoids very long NSIS paths under Windows profiles.
    shutil.rmtree(STAGE/'python/Lib/site-packages/torch/include',ignore_errors=True)
    # Windows loads DLL/PYD files, not compiler import/static libraries or PDBs.
    # dnnl.lib in the full wheel is huge and can exceed 32-bit NSIS mmap limits.
    # Do not remove Python modules, DLLs, PYDs, license files or model code.
    removed=0
    for p in list((STAGE/'python').rglob('*')):
        if p.is_file() and p.suffix.lower() in {'.lib','.pdb','.exp'}:
            removed+=p.stat().st_size;p.unlink()
    print('Removed compiler-only libraries/debug symbols:',removed,'bytes',flush=True)
    for p in list(STAGE.rglob('__pycache__')):shutil.rmtree(p,ignore_errors=True)
    (STAGE/'notices/sources.json').write_text(json.dumps({'python_version':catalog['python_version'],'build_commit':os.environ.get('GITHUB_SHA','local'),'artifacts':target,'model_weights_included':False},indent=2),encoding='utf-8')
    files={p.relative_to(STAGE).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(STAGE.rglob('*')) if p.is_file()}
    for name,meta in sorted(files.items(),key=lambda item:item[1]['bytes'],reverse=True)[:12]:
        print('Runtime largest file:',meta['bytes'],name,flush=True)
    bundle_id='windows-x64-'+VERSION
    manifest=STAGE/'bundle-manifest.json'
    manifest.write_text(json.dumps({'id':bundle_id,'platform':'windows/amd64','files':files},sort_keys=True),encoding='utf-8')
    filename='RallyCut-runtime-windows-amd64.zip';archive=OUT/filename
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(STAGE.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(STAGE).as_posix())
    spec={'id':bundle_id,'filename':filename,'sha256':sha(archive),'manifest_sha256':sha(manifest),'bytes':archive.stat().st_size,'installed_bytes':sum(p.stat().st_size for p in STAGE.rglob('*') if p.is_file())}
    catalog={'platforms':{'windows/amd64':spec}}
    (OUT/'runtime-bundle.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
    (ROOT/'backend/setup/runtime-bundle.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
    # Installers expand the versioned tree during installation, before launch.
    # The ZIP remains an optional portable/offline artifact, not a second setup
    # step imposed on users of the complete installer.
    (ROOT/'backend/runtimeenv/bundled-id.txt').write_text(bundle_id+'\n',encoding='utf-8')
    (ROOT/'build/windows/installer/runtime-layout.nsh').write_text('!define RALLYCUT_RUNTIME_ID "'+bundle_id+'"\n',encoding='utf-8')
    print(json.dumps(spec,indent=2),flush=True)


if __name__=='__main__':main()
