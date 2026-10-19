"""Reproducible small synthetic benchmark; not a city-scale capacity claim."""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeat',type=int,default=3)
    args=parser.parse_args()
    if args.repeat<1: parser.error('--repeat must be positive')
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from qgis.core import QgsApplication,QgsGeometry,QgsRectangle,Qgis
    app=QgsApplication.instance() or QgsApplication([],False);app.initQgis()
    from stage1.gis import indexed,join_evidence,run
    from stage1.demo import create_demo
    from stage1 import __version__
    unit=QgsGeometry.fromRect(QgsRectangle(0,0,10,10))
    pieces=[(QgsGeometry.fromRect(QgsRectangle(i,0,i+1,10)),{f'v{j}':True for j in range(40)}) for i in range(10)]
    index,records=indexed(pieces);fields={f'v{j}':f'v{j}' for j in range(40)}
    overlay,workflow=[],[]
    for repeat in range(args.repeat):
        start=time.perf_counter()
        for i in range(250): result=join_evidence(unit,index,records,fields)
        overlay.append(time.perf_counter()-start)
        assert all(result.values())
        with tempfile.TemporaryDirectory(prefix='nbs-benchmark-') as tmp:
            source=create_demo(Path(tmp)/'demo');start=time.perf_counter();run(source,False);workflow.append(time.perf_counter()-start)
    print(json.dumps({'version':__version__,'qgis':Qgis.QGIS_VERSION,'repeat':args.repeat,
                      'overlay_250_units_40_fields_seconds':overlay,'overlay_median_seconds':statistics.median(overlay),
                      'workflow_120_cells_15_designs_no_printing_seconds':workflow,'workflow_median_seconds':statistics.median(workflow),
                      'limitations':'Synthetic small inputs. Times depend on hardware, cache and profiling; no NRW city-scale capacity assertion.'},indent=2))


if __name__=='__main__':main()
