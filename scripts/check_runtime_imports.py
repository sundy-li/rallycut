#!/usr/bin/env python3
"""Fail packaging when a local Python import is absent from the runtime bundle."""
import argparse
import ast
from pathlib import Path


def check(source, installed, files=None):
    source,installed=Path(source),Path(installed)
    paths=[Path(path) for path in files] if files is not None else [path.relative_to(installed) for path in installed.rglob('*.py')]
    for relative in paths:
        if relative.suffix!='.py':continue
        path=installed/relative
        if not path.is_file():raise ValueError(f'missing runtime file: {relative}')
        tree=ast.parse(path.read_text(encoding='utf-8'),filename=str(relative))
        modules=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom) and node.module:modules.append(node.module)
            elif isinstance(node,ast.Import):modules.extend(alias.name for alias in node.names)
        for module in modules:
            dependency=Path(*module.split('.')).with_suffix('.py')
            if (source/dependency).is_file() and not (installed/dependency).is_file():
                raise ValueError(f'{relative} imports local {dependency}, missing from packaged runtime')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--installed',type=Path,required=True)
    args=parser.parse_args();check(args.source,args.installed);print('PASS local runtime import closure')


if __name__=='__main__':main()
