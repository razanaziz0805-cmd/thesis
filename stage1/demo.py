"""Deterministic artificial inputs; no real Cologne data or authority claims."""

import json
from pathlib import Path
from osgeo import gdal, osr
import numpy as np
from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsRectangle

from .catalogue import KOELN_POLICY as DEFAULT_POLICY, DESIGNS
from .engine import COMMON_RULES
from .gis import memory_layer, write_layer


def create_demo(directory):
    directory = Path(directory)
    if directory.exists():
        raise ValueError(f'Demo directory exists: {directory}; choose a new directory to preserve previous runs')
    directory.mkdir(parents=True)
    inputs = directory / 'inputs'
    inputs.mkdir()
    crs = QgsCoordinateReferenceSystem('EPSG:25832')
    cols, rows, cell, origin_x, origin_y = 12, 10, 20, 360000, 5640000
    y, x = np.mgrid[:rows, :cols]
    depth = np.maximum(0, 42 * np.exp(-((x - 7) ** 2 / 11 + (y - 5) ** 2 / 7)) + 9 * np.sin(x / 2) - 3).astype('float32')
    depth[0, :4] = [-9999, 9, 10, 11]
    ds = gdal.GetDriverByName('GTiff').Create(str(inputs / 'flood_cm.tif'), cols, rows, 1, gdal.GDT_Float32, options=['COMPRESS=DEFLATE'])
    ds.SetGeoTransform((origin_x, cell, 0, origin_y, 0, -cell))
    sr = osr.SpatialReference()
    sr.ImportFromEPSG(25832)
    ds.SetProjection(sr.ExportToWkt())
    ds.GetRasterBand(1).SetNoDataValue(-9999)
    ds.GetRasterBand(1).WriteArray(depth)
    ds = None
    domain = QgsGeometry.fromRect(QgsRectangle(origin_x, origin_y - rows * cell, origin_x + cols * cell, origin_y))
    gpkg = inputs / 'synthetic.gpkg'
    write_layer(gpkg, memory_layer('study_area', [({'id': 'SYNTHETIC'}, domain)], crs), 'study_area', first=True)
    all_boolean = [key for key, _, _ in COMMON_RULES] + [
        'receiving_ground_clean', 'soil_infiltration_ok', 'runoff_quality_ok', 'aquifer_evidence_ok', 'mounding_assessed_ok',
        'groundwater_standard_confirmed', 'utilities_clearance_ok', 'excavation_contamination_ok', 'drainage_asset_access_ok',
        'lining_integrity_ok', 'no_deliberate_infiltration_ok', 'outlet_capacity_ok', 'groundwater_structural_risk_ok', 'roof_structure_ok', 'roof_waterproofing_ok',
        'roof_drainage_ok', 'roof_fire_safety_ok', 'roof_retention_design_ok', 'living_soil_treatment_ok', 'slope_erosion_ponding_ok',
        'media_vegetation_treatment_ok', 'rootable_soil_volume_ok', 'tree_root_utility_conflict_resolved', 'tree_and_drainage_maintenance_ok',
        'pavement_loading_ok', 'subbase_storage_ok', 'declogging_plan_ok', 'pretreatment_ok', 'inspection_cleaning_ok',
        'combined_system_layout_ok', 'shaft_hydrogeology_ok', 'normal_use_safety_ok', 'retention_function_protected',
        'route_rights_ok', 'downstream_receptors_ok',
    ]
    land_types = ['roof', 'roof', 'open_space', 'open_space', 'verge', 'verge', 'pavement', 'pavement', 'parking', 'footway', 'open_space', 'verge']
    evidence = []
    for row in range(rows):
        for col in range(cols):
            left, top = origin_x + col * cell, origin_y - row * cell
            geom = QgsGeometry.fromRect(QgsRectangle(left, top-cell, left+cell, top))
            a = {key: 1 for key in all_boolean}
            a.update(unit_id=f'r{row:07d}_c{col:07d}', land_type=land_types[col], evidence_ref=f'SYNTHETIC_SITE_R{row}_C{col}',
                     protection_zone='OUTSIDE', neighbour_distance_m=3., non_waterproof_basement_present=1, basement_distance_m=8.,
                     design_groundwater_elevation_m=97.5, groundwater_uncertainty_m=.2, vertical_datum='SYNTHETIC_DHHN2016',
                     groundwater_scenario_id='SYNTHETIC_HIGH_GW', permission_status='confirmed', pv_present=0, public_drainage_assets_present=0)
            for design, (_, _, infiltrates, _) in DESIGNS.items():
                if infiltrates:
                    a['module_base_elevation_m__' + design] = 99.
            if row == 2 and col >= 2:
                a['protection_zone'] = 'II'
            if row == 3 and col >= 2:
                for key in list(a):
                    if key.startswith('module_base_elevation_m__'):
                        a[key] = 98.1  # robust 0.4 m → FAIL, never automatic lining.
            if row == 4:
                a['design_groundwater_elevation_m'] = None
                a['permission_status'] = 'pending'
            if row == 5 and col >= 2:
                a['basement_distance_m'] = 4.  # recommendation → conditional.
            if row == 6 and col >= 2:
                a['receiving_ground_clean'] = 0
            if row == 7 and col >= 2:
                a['protection_zone'] = 'IIIA'
                a['outer_zone_authority_ok'] = None
            if row == 8:
                a['maintenance_assigned'] = None
            evidence.append((a, geom))
    write_layer(gpkg, memory_layer('evidence', evidence, crs), 'evidence')
    owner_records = [
        ({'owner': 'CITY'}, QgsGeometry.fromRect(QgsRectangle(origin_x, origin_y - 200, origin_x + 110, origin_y))),
        ({'owner': 'PRIVATE'}, QgsGeometry.fromRect(QgsRectangle(origin_x+110, origin_y-180, origin_x+240, origin_y))),
        ({'owner': 'OTHER_PUBLIC'}, QgsGeometry.fromRect(QgsRectangle(origin_x+160, origin_y-200, origin_x+240, origin_y-180))),
        # Deliberate 10x20 m contradictory parcel in the last-but-one row.
        ({'owner': 'PRIVATE'}, QgsGeometry.fromRect(QgsRectangle(origin_x+10, origin_y-180, origin_x+30, origin_y-160))),
    ]
    write_layer(gpkg, memory_layer('ownership', owner_records, crs), 'ownership')
    checked = {k: True for k in ['layout_verified', 'hydraulic_link_verified', 'shared_source_accounting_verified', 'shared_storage_accounting_verified', 'outlet_capacity_verified', 'ownership_operation_verified']}
    def module(row, col, design, ident, fraction):
        return {'unit_id': f'r{row:07d}_c{col:07d}', 'design': design, 'module_id': ident,
                'footprint_id': ident + '_footprint', 'allocated_area_m2': 150, 'source_id': 'SYNTHETIC_ROOF_SOURCE', 'source_fraction': fraction}
    good = {'id': 'roof_to_lined_tree', 'evidence_ref': 'SYNTHETIC_LINK_AND_LAYOUT', **checked,
            'modules': [module(0, 1, 'green_roof', 'roof', 1), module(0, 4, 'tree_trench_lined', 'tree', 0)],
            'links': [{'from': 'roof', 'to': 'tree', 'evidence_ref': 'SYNTHETIC_GRADED_PIPE_ROUTE'}]}
    missing = {**good, 'id': 'unverified_route', 'hydraulic_link_verified': None, 'outlet_capacity_verified': None}
    double = {**good, 'id': 'source_double_counted', 'modules': [good['modules'][0], {**good['modules'][1], 'source_fraction': 1}]}
    failed = {**good, 'id': 'prohibited_infiltration_member', 'modules': [good['modules'][0], module(2, 4, 'tree_trench_infiltration', 'tree', 0)]}
    meta = {'provider': 'Stage 1 deterministic software fixture', 'version': 'v1', 'date': 'synthetic', 'license': 'Test data generated by this workflow', 'evidence_class': 'assumed / synthetic', 'limitations': 'Not measurements or real site data'}
    config = {
        'demo': True, 'run_id': 'DEMO_SRI5_CM_10CM', 'area_label': 'Synthetic test domain · not actual Köln-Kalk',
        'scenario_id': 'SYNTHETIC_SRI5', 'scenario_description': 'Synthetic demonstration using user-requested SRI5 configuration; no real rainfall model',
        'stated_return_period_years': 30, 'return_period_source': 'User statement; not an independently verified SRI-to-return-period conversion',
        'groundwater_scenario_id': 'SYNTHETIC_HIGH_GW', 'crs': 'EPSG:25832', 'jurisdiction':'Koeln', 'vertical_datum': 'SYNTHETIC_DHHN2016',
        'flood_threshold_m': .1, 'max_units': 250000,
        'flood': {'path': 'inputs/flood_cm.tif', 'type': 'raster', 'band': 1, 'units': 'cm', 'metadata': meta},
        'study_area': {'path': 'inputs/synthetic.gpkg', 'layer': 'study_area', 'metadata': meta},
        'evidence': [{'path': 'inputs/synthetic.gpkg', 'layer': 'evidence', 'join': 'id', 'id_field': 'unit_id', 'metadata': meta}],
        'ownership': {'path': 'inputs/synthetic.gpkg', 'layer': 'ownership', 'class_field': 'owner',
                      'mapping': {'CITY': 'municipal', 'PRIVATE': 'private', 'OTHER_PUBLIC': 'other_public'}, 'metadata': meta},
        'policy': {**DEFAULT_POLICY, 'profile_reviewed': True, 'profile_review_ref': 'SYNTHETIC_REVIEW_FOR_SOFTWARE_TESTS_ONLY'},
        'designs': list(DESIGNS), 'combinations': [good, missing, double, failed], 'output_dir': 'results',
    }
    path = directory / 'demo.json'
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    return path


def create_muriel_demo(directory):
    """Separate controlled case study; all geometry and evidence are artificial."""
    from qgis.core import QgsPointXY
    from .muriel import flood_hotspots, union
    path = create_demo(directory)
    config = json.loads(path.read_text())
    directory = path.parent
    crs = QgsCoordinateReferenceSystem('EPSG:25832')
    ox, oy = 360000, 5639000
    def box(x, y, width, height):
        return QgsGeometry.fromRect(QgsRectangle(ox+x, oy+y, ox+x+width, oy+y+height))
    domain = box(0, 0, 1200, 800)
    records = []
    # Connected 20x40 m source strips demonstrate dissolution before area testing.
    for i, depth in enumerate([35., 38., 40., 45.]):
        records.append(({'unit_id': f'protect_{i}', 'depth_cm': depth, 'case_name': 'Existing retention'}, box(100+i*20,100,20,40)))
    records.append(({'unit_id': 'shallow_apron', 'depth_cm': 10., 'case_name': 'Shallow apron; outside default MURIEL mask'}, box(80,100,20,40)))
    cases = [('retrofit',400,100,80,40,50), ('investigate',800,100,80,40,55),
             ('no_destination',100,400,80,40,45), ('no_receptor',400,400,80,40,45),
             ('area_exact',800,400,50,40,50), ('depth_exact',100,650,80,40,30),
             ('unsafe_route',400,650,80,40,50)]
    for ident,x,y,w,h,depth in cases:
        records.append(({'unit_id': ident, 'depth_cm': depth, 'case_name': ident}, box(x,y,w,h)))
    unknown = box(1100,700,20,20)
    records.append(({'unit_id':'nodata','depth_cm':None,'case_name':'NoData'},unknown))
    dry = domain.difference(union(g for _,g in records))
    records.append(({'unit_id':'dry_domain','depth_cm':0.,'case_name':'Known dry background'},dry))
    gpkg = directory/'inputs/muriel_synthetic.gpkg'
    write_layer(gpkg,memory_layer('study_area',[({'id':'SYNTHETIC_MURIEL'},domain)],crs),'study_area',first=True)
    write_layer(gpkg,memory_layer('flood',records,crs),'flood')
    spaces = [({'destination_id':'S_PROTECT','usable':1},box(100,100,60,40)),
              ({'destination_id':'S_RETROFIT','usable':1},box(490,100,60,40)),
              ({'destination_id':'S_INVESTIGATE','usable':1},box(900,100,60,40)),
              ({'destination_id':'S_OUTSIDE','usable':1},box(490,400,60,40)),
              ({'destination_id':'S_UNSAFE','usable':1},box(490,650,60,40))]
    # Municipal but unusable land near the no-destination hotspot.
    municipal = [(a,g) for a,g in spaces] + [({'destination_id':'LAND_ONLY'},box(190,400,20,40))]
    receptors = [({'id': 'B_'+ident},box(x-5.5,y+10,5,10)) for ident,x,y,w,h,depth in cases if ident != 'no_receptor']
    receptors.append(({'id':'B_PROTECT'},box(94.5,110,5,10)))
    roads = [({'id':'R1'},box(0,300,1200,15)),({'id':'R2'},box(0,600,1200,15))]
    for layer, items in [('usable_space',spaces),('municipal_land',municipal),('receptors',receptors),('roads',roads)]:
        write_layer(gpkg,memory_layer(layer,items,crs),layer)
    units=[{'attrs':{'unit_id':a['unit_id'],'flood_depth_m':None if a['depth_cm'] is None else a['depth_cm']*.01},'geometry':g} for a,g in records]
    hs=flood_hotspots(units,domain)
    ids={uid:h['hotspot_id'] for h in hs for uid in h['source_unit_ids']}
    routes=[]
    for uid,sy,dest,ok in [('retrofit',120,'S_RETROFIT',True),('unsafe_route',670,'S_UNSAFE',False)]:
        line=QgsGeometry.fromPolylineXY([QgsPointXY(ox+470,oy+sy),QgsPointXY(ox+500,oy+sy)])
        a={'hotspot_id':ids[uid],'destination_id':dest,'topography_compatible':int(ok),
           'flow_routing_safe':int(ok),'downstream_receptors_safe':1,'route_land_control_ok':1,
           'evidence_ref':'SYNTHETIC_SURVEY_AND_ROUTE_ASSESSMENT_'+uid}
        routes.append((a,line))
    write_layer(gpkg,memory_layer('routes',routes,crs,geometry_type='MultiLineString'),'routes')
    meta={'provider':'Deterministic artificial MURIEL test case','version':'v1','date':'synthetic','license':'Generated test geometry','evidence_class':'synthetic','limitations':'No actual Köln-Kalk observations or authority decisions'}
    def spec(layer,**kwargs):
        return {'path':'inputs/muriel_synthetic.gpkg','layer':layer,'coverage_complete':True,
                'evidence_ref':'SYNTHETIC_'+layer.upper(),'metadata':meta,**kwargs}
    config.update(run_id='DEMO_MURIEL_SRI5_V1',area_label='Synthetic MURIEL test district · not Köln-Kalk',
                  flood={**spec('flood'),'type':'vector','id_field':'unit_id','depth_field':'depth_cm','units':'cm'},
                  study_area=spec('study_area'),evidence=[],ownership=None,combinations=[])
    config['muriel']={'enabled':True,'thresholds':{'footprint_mode':'depth_mask'},'receptors':[spec('receptors')],
                      'criteria_adoption_ref':'SYNTHETIC_LOCAL_SCREEN_ADOPTION_FOR_SOFTWARE_TEST_ONLY', 'criteria_scope':'Koeln',
                      'municipal_land':spec('municipal_land',municipal_verified=True),'roads':spec('roads'),
                      'usable_space':spec('usable_space',id_field='destination_id',usable_field='usable'),
                      'routes':spec('routes')}
    path.write_text(json.dumps(config,indent=2,ensure_ascii=False))
    return path


def create_planning_demo(directory):
    """Planning example with simple categorical layers, never real city evidence."""
    path = create_demo(directory)
    config = json.loads(path.read_text())
    from .gis import load_vector
    crs = QgsCoordinateReferenceSystem('EPSG:25832')
    gpkg = path.parent/'inputs/synthetic.gpkg'
    original = load_vector({'path':str(gpkg), 'layer':'evidence'}, crs)
    surface_records = [({'surface':a['land_type'] if i != 15 else 'UNMAPPED'},g) for i,(g,a) in enumerate(original)]
    write_layer(gpkg, memory_layer('surfaces', surface_records, crs), 'surfaces')
    constraints = [({'protection_zone':a['protection_zone'], 'receiving_ground_clean':a['receiving_ground_clean'],
                     'evidence_ref':'SYNTHETIC_PLANNING_CONSTRAINT'},g) for g,a in original]
    write_layer(gpkg, memory_layer('planning_constraints', constraints, crs), 'planning_constraints')
    heat = [({'heat':'HOT' if i % 12 >= 5 else 'OTHER'},g) for i,(g,a) in enumerate(original)]
    write_layer(gpkg, memory_layer('heat', heat, crs), 'heat')
    meta = config['study_area']['metadata']
    config.update(mode='planning', run_id='DEMO_PLANNING_SRI5_V05', combinations=[],
                  groundwater_scenario_id='UNKNOWN_DESIGN_GROUNDWATER', vertical_datum=None,
                  policy={**DEFAULT_POLICY}, muriel={'enabled':False},
                  evidence=[{'path':'inputs/synthetic.gpkg', 'layer':'planning_constraints', 'join':'spatial',
                             'fields':{k:k for k in ('protection_zone','receiving_ground_clean','evidence_ref')}, 'metadata':meta}],
                  planning={'surfaces':{'path':'inputs/synthetic.gpkg','layer':'surfaces','class_field':'surface',
                                        'mapping':{k:k for k in ('roof','open_space','verge','pavement','parking','footway')}, 'metadata':meta},
                            'heat':{'path':'inputs/synthetic.gpkg','layer':'heat','class_field':'heat',
                                    'mapping':{'HOT':'priority','OTHER':'other'},'metadata':meta}})
    path.write_text(json.dumps(config,indent=2,ensure_ascii=False))
    return path


def create_area_demo(directory, crs='EPSG:32631', depth_units='cm'):
    """Neutral artificial project in any specified projected metre-based CRS.

    This generates new test geometry; it never re-labels real source data.
    No local standards, recurrence interval or engineering clearance is assumed.
    """
    from qgis.core import Qgis
    from .configuration import planning_config
    directory=Path(directory)
    if directory.exists():
        raise ValueError('Choose a new example directory; earlier outputs are preserved.')
    reference=QgsCoordinateReferenceSystem(crs)
    if not reference.isValid() or reference.isGeographic() or reference.mapUnits()!=Qgis.DistanceUnit.Meters:
        raise ValueError('The synthetic example needs a projected CRS in metres.')
    if depth_units not in ('cm','m'):
        raise ValueError('Example depth units must be cm or m.')
    inputs=directory/'inputs';inputs.mkdir(parents=True)
    left,top,cell,cols,rows=360000.,5640000.,10.,8,6
    values=np.array([[0,0,5,9,0,0,0,0], [0,10,20,40,0,0,15,20], [0,20,35,60,0,0,20,30],
                     [0,10,30,40,0,0,0,0], [0,0,0,0,0,5,0,0], [0,0,0,0,0,0,0,-9999]],dtype='float32')
    if depth_units=='m':values=np.where(values==-9999,-9999,values/100).astype('float32')
    raster=inputs/'flood_depth.tif';ds=gdal.GetDriverByName('GTiff').Create(str(raster),cols,rows,1,gdal.GDT_Float32,options=['COMPRESS=DEFLATE'])
    ds.SetGeoTransform((left,cell,0,top,0,-cell));ds.SetProjection(reference.toWkt())
    ds.GetRasterBand(1).SetNoDataValue(-9999);ds.GetRasterBand(1).SetUnitType(depth_units);ds.GetRasterBand(1).WriteArray(values);ds=None
    gpkg=inputs/'synthetic_area.gpkg'
    def rect(x,y,w,h):return QgsGeometry.fromRect(QgsRectangle(left+x,top-y-h,left+x+w,top-y))
    write_layer(gpkg,memory_layer('study_area',[({'id':'SYNTHETIC_AREA'},rect(0,0,80,60))],reference),'study_area',first=True)
    surfaces=[]
    types=['roof','roof','open_space','open_space','verge','footway','parking','pavement']
    for row in range(rows):
        for col in range(cols):surfaces.append(({'surface':types[col]},rect(col*10,row*10,10,10)))
    write_layer(gpkg,memory_layer('surfaces',surfaces,reference),'surfaces')
    write_layer(gpkg,memory_layer('ownership',[({'owner':'CITY'},rect(0,0,40,60)),({'owner':'PRIVATE'},rect(40,0,40,60))],reference),'ownership')
    write_layer(gpkg,memory_layer('heat',[({'class':'HIGH'},rect(0,0,40,60)),({'class':'OTHER'},rect(40,0,40,60))],reference),'heat')
    metadata={'provider':'Generated software fixture','date':'synthetic','version':'v0.6','license':'Generated test data',
              'evidence_class':'synthetic','limitations':'No actual study area, local law, storm or ownership is represented.'}
    def spec(layer):return {'path':'inputs/synthetic_area.gpkg','layer':layer,'metadata':metadata}
    config=planning_config(flood={'path':'inputs/flood_depth.tif','type':'raster','band':1,'units':depth_units,'metadata':metadata},
                           study_area=spec('study_area'),crs=crs,scenario='SYNTHETIC_EVENT',area_label='Synthetic study area',jurisdiction='Synthetic authority')
    config.update(demo=True,run_id='DEMO_TRANSFERABLE_PLANNING',scenario_description='Artificial depth field; no return-period inference.',
                  planning={'surfaces':{**spec('surfaces'),'class_field':'surface','mapping':{key:key for key in types}},
                            'heat':{**spec('heat'),'class_field':'class','mapping':{'HIGH':'priority','OTHER':'other'}}},
                  ownership={**spec('ownership'),'class_field':'owner','mapping':{'CITY':'municipal','PRIVATE':'private'}})
    path=directory/'demo.json';path.write_text(json.dumps(config,indent=2,ensure_ascii=False));return path
