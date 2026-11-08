"""Prepare pinned official sources, apply local adaptations, build, and package.

Run inside an activated ESP-IDF 5.5.4 terminal. No board is flashed by this tool.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile

from adapt_console import adapt

ROOT = Path(__file__).resolve().parent


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, help='Existing esp-csi clone; reads the pinned commit, not working files')
    p.add_argument('--prepare-only', action='store_true')
    args = p.parse_args()
    spec = json.loads((ROOT/'upstream.json').read_text())
    source = args.source.resolve() if args.source else ROOT/'.cache/esp-csi'
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run('git', 'clone', '--no-checkout', spec['repository'], str(source))
    run('git', '-C', str(source), 'cat-file', '-e', spec['commit']+'^{commit}')
    archive = subprocess.check_output(['git','-C',str(source),'archive', spec['commit'], spec['example']])
    project = ROOT/'.work/project'
    project.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for entry in tar:
            if not entry.isfile():
                continue
            path = PurePosixPath(entry.name)
            rel = path.relative_to(PurePosixPath(spec['example']))
            if not entry.isfile() or '..' in rel.parts or not rel.parts:
                continue
            if rel.parts[0] not in ('main','components','CMakeLists.txt','sdkconfig.defaults','partitions.csv'):
                continue
            dest = project / str(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(tar.extractfile(entry).read())
    adapt(project)
    print('Prepared pinned sources and English-described adaptations:', project, flush=True)
    if args.prepare_only:
        return
    idf = Path(os.environ['IDF_PATH'])
    idf_py = idf/'tools/idf.py'
    version = subprocess.check_output([sys.executable,str(idf_py),'--version'], text=True)
    if spec['esp_idf'] not in version:
        raise SystemExit('Activate ESP-IDF '+spec['esp_idf']+' before building.')
    run(sys.executable, str(idf_py), '-C', str(project), 'set-target', spec['target'])
    run(sys.executable, str(idf_py), '-C', str(project), 'build')
    build = project/'build'
    artifact = ROOT/'.artifacts'
    artifact.mkdir(exist_ok=True)
    flash = json.loads((build/'flasher_args.json').read_text())
    images = []
    for address, relative in flash['flash_files'].items():
        filename = relative.replace('/', '_').replace('\\', '_')
        dest = artifact/filename
        shutil.copyfile(build/relative, dest)
        images.append({'address': address, 'file': filename, 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()})
    manifest = {**spec, 'images':images, 'flash_mode':'dio', 'flash_freq':'80m', 'flash_size':'4MB'}
    (artifact/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    shutil.copyfile(project/'dependencies.lock', artifact/'dependencies.lock')
    print('Firmware package ready:', artifact/'manifest.json')


if __name__ == '__main__':
    main()
