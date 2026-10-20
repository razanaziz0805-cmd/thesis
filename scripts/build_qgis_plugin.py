"""Build an installable QGIS plugin ZIP, bundling the exact current engine."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def build(target):
    root=Path(__file__).resolve().parents[1]
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(target,'w',compression=ZIP_DEFLATED) as archive:
        for path in sorted((root/'qgis_plugin/nbs_stage1').rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                archive.write(path,Path('nbs_stage1')/path.relative_to(root/'qgis_plugin/nbs_stage1'))
        for path in sorted((root/'stage1').glob('*.py')):
            archive.write(path,Path('nbs_stage1/stage1')/path.name)
        for path in sorted((root/'docs').iterdir()):
            if path.is_file() and path.suffix in ('.md','.json','.csv'):
                archive.write(path,Path('nbs_stage1/docs')/path.name)
        for path in sorted((root/'config').glob('*.json')):
            archive.write(path,Path('nbs_stage1/config')/path.name)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target',nargs='?',default='downloads/nbs-stage1-plugin-v0.4.zip')
    print(build(parser.parse_args().target))
