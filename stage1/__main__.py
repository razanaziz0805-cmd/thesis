import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Stage 1 auditable QGIS opportunity mapping')
    sub = parser.add_subparsers(dest='command', required=True)
    demo = sub.add_parser('demo', help='Create synthetic inputs and a clearly labelled demonstration atlas')
    demo.add_argument('--directory', default='outputs/demo')
    demo.add_argument('--no-maps', action='store_true')
    demo.add_argument('--muriel', action='store_true', help='Use the dedicated multi-case MURIEL demonstration')
    run = sub.add_parser('run', help='Run on registered real inputs')
    run.add_argument('config')
    run.add_argument('--no-maps', action='store_true')
    args = parser.parse_args()
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/thesis-qgis-runtime')
    Path(os.environ['XDG_RUNTIME_DIR']).mkdir(mode=0o700, exist_ok=True)
    from qgis.core import QgsApplication
    app = QgsApplication([], False)
    app.initQgis()
    from .gis import run as run_workflow
    try:
        if args.command == 'demo':
            from .demo import create_demo, create_muriel_demo
            config = (create_muriel_demo if args.muriel else create_demo)(Path(args.directory).resolve())
        else:
            config = Path(args.config).resolve()
        out = run_workflow(config, not args.no_maps)
        print(f'Completed: {out}')
        print('Synthetic demonstration only' if args.command == 'demo' else 'Spatial screening only; inspect run_manifest.json')
    finally:
        # Keep providers / projects alive until interpreter shutdown. Explicit
        # exitQgis() while Python wrappers still own layers can crash GDAL/QGIS.
        from qgis.core import QgsProject
        QgsProject.instance().clear()


if __name__ == '__main__':
    main()
