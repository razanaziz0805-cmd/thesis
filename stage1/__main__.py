import argparse
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description='Stage 1 NbS opportunity mapping. Use gui for guided setup or validate before a run.')
    parser.add_argument('--debug', action='store_true', help='Show technical traceback on failure')
    sub = parser.add_subparsers(dest='command', required=True)
    demo = sub.add_parser('demo', help='Run clearly labelled synthetic demonstration')
    demo.add_argument('--directory', default='outputs/demo')
    demo.add_argument('--muriel', action='store_true')
    demo.add_argument('--planning', action='store_true', help='Show the simplified urban-planning workflow')
    run = sub.add_parser('run', help='Run a registered configuration')
    run.add_argument('config')
    for command in (demo, run):
        command.add_argument('--no-maps', action='store_true', help='Fast analysis: keep project and audit; skip PNG/PDF printing')
        command.add_argument('--quiet', action='store_true', help='Hide progress messages')
    validate = sub.add_parser('validate', help='Check inputs without producing results')
    validate.add_argument('config')
    validate.add_argument('--json', action='store_true', help='Machine-readable validation result')
    init = sub.add_parser('init', help='Create a starter configuration without overwriting a file')
    init.add_argument('config')
    inventory=sub.add_parser('inventory',help='Inspect GIS files and missing components without altering sources')
    inventory.add_argument('files',nargs='+');inventory.add_argument('--output',default=None)
    prep=sub.add_parser('prepare',help='Reproject, clip and align inputs using a documented preparation job')
    prep.add_argument('config')
    sub.add_parser('gui', help='Open guided desktop setup using the QGIS Python environment')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            from .configuration import planning_config
            with Path(args.config).open('x', encoding='utf-8') as f:
                json.dump(planning_config(), f, indent=2, ensure_ascii=False)
            print(f'Starter saved: {args.config}. Select input files before running; gui offers a form.')
            return 0
        if args.command != 'gui':
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/thesis-qgis-runtime')
        Path(os.environ['XDG_RUNTIME_DIR']).mkdir(mode=0o700, exist_ok=True)
        from qgis.core import QgsApplication
        app = QgsApplication.instance() or QgsApplication([], args.command == 'gui')
        app.initQgis()
        if args.command=='inventory':
            from .inventory import inspect_paths
            result=inspect_paths(args.files,args.output)
            print(json.dumps(result,indent=2,ensure_ascii=False))
            return 0 if all(r['status']=='READABLE' for r in result) else 2
        if args.command=='prepare':
            from .preparation import prepare
            print(prepare(args.config,progress=lambda p,m:print(f'[{p:.0f}%] {m}',file=sys.stderr,flush=True)))
            return 0
        if args.command == 'gui':
            from .planning_gui import PlanningDialog
            dialog = PlanningDialog()
            dialog.exec_()
            return 0
        from .preflight import inspect_config
        if args.command == 'validate':
            result = inspect_config(args.config)
            print(json.dumps(result.as_dict(), indent=2) if args.json else result.text())
            return 0 if result.ok else 2
        if args.command == 'demo':
            from .demo import create_demo, create_muriel_demo, create_planning_demo
            if args.planning and args.muriel:
                raise ValueError('Choose one demonstration: --planning or --muriel.')
            config = (create_planning_demo if args.planning else create_muriel_demo if args.muriel else create_demo)(Path(args.directory).resolve())
        else:
            config = Path(args.config).resolve()
        checked = inspect_config(config)
        if not checked.ok:
            print(checked.text(), file=sys.stderr)
            return 2
        for issue in checked.issues:
            if not args.quiet:
                print(f"[{issue['level']}] {issue['input']}: {issue['message']}", file=sys.stderr)
        from .gis import run as run_workflow
        def progress(percent, message):
            if not args.quiet:
                print(f'[{percent:5.1f}%] {message}', file=sys.stderr, flush=True)
        out = run_workflow(config, not args.no_maps, progress=progress)
        print(f'Completed: {out}\nOpen report.html for results or stage1.qgz in QGIS.')
        if args.command == 'demo':
            print('Synthetic demonstration only.')
        return 0
    except KeyboardInterrupt:
        print('Cancelled. Earlier results preserved.', file=sys.stderr)
        return 130
    except Exception as exc:
        from .runtime import RunCancelled
        if isinstance(exc, RunCancelled):
            print(str(exc), file=sys.stderr)
            return 130
        if args.debug:
            raise
        message = str(exc)
        if isinstance(exc, ModuleNotFoundError) and exc.name == 'qgis':
            message = 'Use the Python environment supplied with QGIS. In this cloud environment: /usr/bin/python3 -m stage1 ...'
        print('Cannot complete this run: ' + message, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
