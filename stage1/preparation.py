"""Non-destructive, documented GIS preparation with explicit CRS and grid choices."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

from osgeo import gdal, ogr, osr

from .inventory import companions, file_hash, reference_info
from .runtime import RunControl


gdal.UseExceptions()


def _srs(value):
    srs=osr.SpatialReference()
    if not value or srs.SetFromUserInput(str(value))!=0:
        raise ValueError('A valid source/target CRS is required; coordinates alone do not establish the CRS.')
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return srs


def source_reference(declared, spec):
    original=declared.Clone() if declared else None
    if original:original.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    override=_srs(spec['source_crs']) if spec.get('source_crs') else None
    changed=override is not None and (original is None or not original.IsSame(override))
    if changed and not spec.get('crs_evidence_ref'):
        raise ValueError(f'{Path(spec["path"]).name}: assigning or replacing a CRS requires source_crs and a crs_evidence_ref. Do not guess from coordinate ranges.')
    actual=override or original
    if actual is None:
        raise ValueError(f'{Path(spec["path"]).name}: missing CRS. Supply the .prj or a confirmed source_crs with crs_evidence_ref.')
    return actual, {'declared':reference_info(original),'used':reference_info(actual),
                    'action':'assign_missing' if changed and original is None else 'replace_declared' if changed else 'use_declared',
                    'evidence_ref':spec.get('crs_evidence_ref')}


def _transform(source, target, spec):
    if source.IsSame(target):return None
    options=osr.CoordinateTransformationOptions()
    options.SetBallparkAllowed(False)
    if hasattr(options,'SetOnlyBest'):options.SetOnlyBest(True)
    if spec.get('coordinate_operation'):options.SetOperation(spec['coordinate_operation'])
    return osr.CreateCoordinateTransformation(source,target,options)


def _family(geom_type):
    flat=ogr.GT_Flatten(geom_type)
    for family,types in [('polygon',(ogr.wkbPolygon,ogr.wkbMultiPolygon)),('line',(ogr.wkbLineString,ogr.wkbMultiLineString)),('point',(ogr.wkbPoint,ogr.wkbMultiPoint))]:
        if flat in types:return family
    raise ValueError('Unsupported geometry type; explicitly prepare geometry collections/curves before screening.')


def _multi(geometry,family):
    if _family(geometry.GetGeometryType())!=family:
        raise ValueError('Repair/clipping changed geometry dimension; manual review is required.')
    return {'polygon':ogr.ForceToMultiPolygon,'line':ogr.ForceToMultiLineString,'point':ogr.ForceToMultiPoint}[family](geometry)


def _open_vector(spec, scratch):
    path=Path(spec['path'])
    if path.suffix.lower()=='.shp':
        parts=companions(path)
        if not parts['.dbf'] and not spec.get('allow_geometry_only'):
            raise ValueError(f'{path.name}: missing .dbf. Re-export as GeoPackage, or explicitly allow_geometry_only for a geometry-only/context use.')
        # Restore index only on an isolated copy, preserving every original byte.
        if not parts['.shx']:
            copy=scratch/(str(len(list(scratch.iterdir())))+'_'+path.stem)
            copy.mkdir()
            for source in parts.values():
                if source:shutil.copyfile(source,copy/source.name)
            path=copy/path.name
            previous=gdal.GetConfigOption('SHAPE_RESTORE_SHX')
            gdal.SetConfigOption('SHAPE_RESTORE_SHX','YES')
            try:ds=ogr.Open(str(path),0)
            finally:gdal.SetConfigOption('SHAPE_RESTORE_SHX',previous)
        else:ds=ogr.Open(str(path),0)
    else:ds=ogr.Open(str(path),0)
    if not ds:raise ValueError(f'Cannot read vector: {path}')
    if spec.get('layer'):
        layer=ds.GetLayerByName(spec['layer'])
    elif ds.GetLayerCount()==1:layer=ds.GetLayer(0)
    else:raise ValueError(f'{path.name}: select one layer explicitly from the multi-layer file.')
    if layer is None:raise ValueError(f'Layer not found: {spec.get("layer")}')
    return ds,layer


def _geometries(spec,target,scratch,control,repairs):
    ds,layer=_open_vector(spec,scratch)
    source,crs_record=source_reference(layer.GetSpatialRef(),spec)
    transform=_transform(source,target,spec)
    family=_family(layer.GetGeomType())
    record={'source':str(Path(spec['path']).resolve()),'layer':layer.GetName(),'crs':crs_record,
            'operation':spec.get('coordinate_operation') or ('identity' if transform is None else 'GDAL/PROJ horizontal transformation; ballpark disabled'),
            'vertical_operation':'None requested; Z values are not certified groundwater elevations.',
            'source_geometry':ogr.GeometryTypeToName(layer.GetGeomType()),'source_count':layer.GetFeatureCount()}
    if Path(spec['path']).suffix.lower()=='.shp':
        parts=companions(spec['path'])
        record['missing_components']=[k for k in ('.shx','.dbf','.prj') if not parts[k]]
        record['geometry_only']=not bool(parts['.dbf'])
    def generate():
        for index,feature in enumerate(layer):
            if index%128==0:control.check()
            raw=feature.GetGeometryRef()
            if raw is None or raw.IsEmpty():raise ValueError(f'{record["layer"]}, feature {feature.GetFID()}: empty geometry requires review.')
            geom=raw.Clone()
            if source.IsGeographic():
                x0,x1,y0,y1=geom.GetEnvelope()
                if x0 < -180 or x1 > 180 or y0 < -90 or y1 > 90:
                    raise ValueError('Coordinates are inconsistent with the declared geographic CRS; supply an evidenced correction.')
            if not geom.IsValid():
                if not spec.get('repair_invalid'):raise ValueError(f'{record["layer"]}, feature {feature.GetFID()}: invalid geometry. Enable documented repair or correct the source.')
                before=geom.GetArea() if family=='polygon' else None
                geom=geom.MakeValid()
                if not geom or not geom.IsValid():raise ValueError('Geometry could not be repaired.')
                _family(geom.GetGeometryType())
                repairs.append({'dataset':spec.get('id',record['layer']),'source_fid':feature.GetFID(),
                                'action':'MakeValid','source_area_native_units':before,'repaired_area_native_units':geom.GetArea() if family=='polygon' else None,
                                'review_required':True})
            if transform and geom.Transform(transform)!=0:raise ValueError('Coordinate transformation failed.')
            yield feature,geom
    return ds,layer,record,generate()


def _write_vector(db,name,spec,target,scratch,clip,control,repairs):
    ds,source,record,features=_geometries(spec,target,scratch,control,repairs)
    family=_family(source.GetGeomType())
    types={'point':ogr.wkbMultiPoint,'line':ogr.wkbMultiLineString,'polygon':ogr.wkbMultiPolygon}
    geometry_type=ogr.GT_SetZ(types[family]) if ogr.GT_HasZ(source.GetGeomType()) else types[family]
    layer=db.CreateLayer(name,srs=target,geom_type=geometry_type,options=['SPATIAL_INDEX=YES','FID=prep_rowid'])
    has_trace='prep_source_fid' in [f.GetName() for f in source.schema]
    for field in source.schema:
        if field.GetName().lower()=='prep_rowid':raise ValueError('Reserved field prep_rowid already exists; rename it explicitly.')
        if layer.CreateField(field)!=0:raise ValueError('Cannot preserve an input attribute field.')
    if not has_trace:layer.CreateField(ogr.FieldDefn('prep_source_fid',ogr.OFTInteger64))
    output_count=0
    # Materialise the layer schema before the feature transaction. Otherwise
    # GPKG's deferred schema/index creation can be rolled back with the rows,
    # leaving the driver's close routine referring to a table that vanished.
    db.FlushCache() if hasattr(db,'FlushCache') else db.SyncToDisk()
    layer.StartTransaction()
    try:
        for feature,geom in features:
            if clip is not None:
                if not geom.Intersects(clip):continue
                geom=geom.Intersection(clip)
                if geom is None:raise ValueError('Geometry clipping failed.')
                if geom.IsEmpty():continue
                if family=='polygon' and geom.GetArea()<=1e-8:continue
                if family=='line' and geom.Length()<=1e-8:continue
            geom=_multi(geom,family)
            if not geom.IsValid():raise ValueError('Clipping produced invalid geometry; review the source.')
            output=ogr.Feature(layer.GetLayerDefn())
            if output.SetFrom(feature,1)!=0:raise ValueError('Cannot preserve input attributes.')
            if not has_trace:output.SetField('prep_source_fid',feature.GetFID())
            output.SetGeometry(geom)
            if layer.CreateFeature(output)!=0:raise ValueError('Cannot write prepared vector feature.')
            output_count+=1
        layer.CommitTransaction()
    except BaseException:
        layer.RollbackTransaction();raise
    record.update(output_layer=name,output_count=output_count,clip='none' if clip is None else 'study_area' if spec.get('clip')=='study_area' else 'search_buffer')
    return record


def _grid(job,aoi,target):
    grid=job.get('grid') or {}
    master=grid.get('master')
    native=None; source_record=None
    if master:
        source=gdal.Open(master['path'])
        if source is None:raise ValueError('Master raster cannot be opened.')
        crs,source_record=source_reference(_srs(source.GetProjection()) if source.GetProjection() else None,master)
        gt=source.GetGeoTransform()
        if crs.IsSame(target) and not(gt[2] or gt[4]) and gt[1]>0 and gt[5]<0:
            native=gt
        elif not grid.get('cell_size_m'):
            raise ValueError('A reprojected/rotated master raster needs an explicit target cell_size_m; its degrees cannot become metres.')
    requested=grid.get('cell_size_m')
    if requested:
        size=[float(requested)]*2 if isinstance(requested,(int,float)) else list(map(float,requested))
    elif native:size=[native[1],abs(native[5])]
    else:raise ValueError('Choose a master raster or an explicit projected cell_size_m.')
    if len(size)!=2 or not all(math.isfinite(v) and v>0 for v in size):raise ValueError('Cell sizes must be finite positive metres.')
    origin=grid.get('origin') or ([native[0],native[3]] if native else [0.,0.])
    if len(origin)!=2 or not all(math.isfinite(float(v)) for v in origin):raise ValueError('Grid origin must have two finite coordinates.')
    ox,oy=map(float,origin);dx,dy=size
    x0,x1,y0,y1=aoi.GetEnvelope()
    if native:
        # Retain the provider's actual master coverage; do not invent cells or
        # negative source IDs outside it. Missing coverage remains documented.
        x0=max(x0,native[0]);x1=min(x1,native[0]+source.RasterXSize*native[1])
        y0=max(y0,native[3]+source.RasterYSize*native[5]);y1=min(y1,native[3])
        if x1<=x0 or y1<=y0:raise ValueError('Study area and master raster do not overlap in the target CRS.')
    left=ox+math.floor((x0-ox)/dx+1e-9)*dx;right=ox+math.ceil((x1-ox)/dx-1e-9)*dx
    bottom=oy+math.floor((y0-oy)/dy+1e-9)*dy;top=oy+math.ceil((y1-oy)/dy-1e-9)*dy
    width,height=round((right-left)/dx),round((top-bottom)/dy)
    if width*height>job.get('max_cells',25000000):raise ValueError('Preparation grid exceeds max_cells; partition the study without silently coarsening.')
    preserved=bool(native and abs(dx-native[1])<1e-8 and abs(dy+native[5])<1e-8 and abs((left-native[0])/dx-round((left-native[0])/dx))<1e-8 and abs((top-native[3])/dy-round((top-native[3])/dy))<1e-8)
    return {'bounds':[left,bottom,right,top],'width':width,'height':height,'cell_size_m':size,'origin':[ox,oy],
            'geotransform':[left,dx,0.,top,0.,-dy],'master_crs':source_record,'native_master_grid_preserved':preserved,
            'master_index_offset':[round((top-native[3])/native[5]),round((left-native[0])/native[1])] if preserved else None}


def _raster(spec,path,grid,target,gpkg,control):
    source=gdal.Open(spec['path'])
    if not source:raise ValueError('Raster cannot be opened.')
    band=spec.get('band',1)
    if isinstance(band,bool) or not isinstance(band,int) or not 1<=band<=source.RasterCount:raise ValueError('Requested raster band does not exist.')
    reference,crs_record=source_reference(_srs(source.GetProjection()) if source.GetProjection() else None,spec)
    if reference.IsGeographic():
        gt=source.GetGeoTransform()
        corners=[(gt[0]+x*gt[1]+y*gt[2],gt[3]+x*gt[4]+y*gt[5]) for x,y in [(0,0),(source.RasterXSize,0),(0,source.RasterYSize),(source.RasterXSize,source.RasterYSize)]]
        if any(abs(x)>180 or abs(y)>90 for x,y in corners):raise ValueError('Raster coordinates contradict its geographic CRS; supply an evidenced correction.')
    kind=spec.get('kind','continuous');method=spec.get('resampling','near')
    allowed={'categorical':('near','mode'),'flood_depth':('near','max'),'continuous':('near','bilinear','average')}
    if kind not in allowed or method not in allowed[kind]:raise ValueError(f'Unsupported resampling {method} for {kind}; categorical values must not be interpolated.')
    gt=source.GetGeoTransform()
    changed=not reference.IsSame(target) or any(abs(a-b)>1e-8 for a,b in zip(gt[1:3]+gt[4:],(grid['cell_size_m'][0],0.,0.,-grid['cell_size_m'][1])))
    if not changed:
        changed=any(abs(value-round(value))>1e-8 for value in ((grid['geotransform'][0]-gt[0])/gt[1],(grid['geotransform'][3]-gt[3])/gt[5]))
    if kind=='flood_depth' and changed and not spec.get('resampling_evidence_ref'):
        raise ValueError('Changing the flood grid requires resampling_evidence_ref: depth thresholds and MURIEL area/depth outcomes can change.')
    srcband=source.GetRasterBand(band)
    if srcband.GetScale() not in (None,1,1.0) or srcband.GetOffset() not in (None,0,0.0):
        raise ValueError('Raster has a nontrivial scale/offset. Apply and document the physical-unit conversion before screening; raw encoded values cannot be treated as depths or soil measurements.')
    if kind=='flood_depth' and srcband.GetUnitType() and spec.get('units'):
        aliases={'cm':'cm','centimetre':'cm','centimeter':'cm','centimetres':'cm','centimeters':'cm','m':'m','metre':'m','meter':'m','metres':'m','meters':'m'}
        declared_unit=aliases.get(srcband.GetUnitType().strip().lower())
        if declared_unit and declared_unit!=spec['units']:raise ValueError('Flood band units disagree with configured units. Correct the unit registration before screening.')
    if srcband.DataType in (gdal.GDT_Int64,gdal.GDT_UInt64):raise ValueError('Int64 raster values require a separately verified lossless data-type/NoData strategy.')
    # Float64 preserves Float32 and <=32-bit integer values while representing
    # unknown/outside cells with NaN, never a fabricated zero or category.
    options=dict(format='GTiff',srcSRS=reference.ExportToWkt(),dstSRS=target.ExportToWkt(),
                 outputBounds=grid['bounds'],width=grid['width'],height=grid['height'],
                 outputType=gdal.GDT_Float64,dstNodata=float('nan'),resampleAlg=method,
                 cutlineDSName=str(gpkg),cutlineLayer='study_area',
                 warpOptions=['CUTLINE_ALL_TOUCHED=TRUE'],transformerOptions=['ALLOW_BALLPARK=NO','ONLY_BEST=YES'],
                 creationOptions=['COMPRESS=DEFLATE','TILED=YES','BIGTIFF=IF_SAFER'])
    if spec.get('coordinate_operation'):options['coordinateOperation']=spec['coordinate_operation']
    selected=gdal.Translate('',source,format='MEM',bandList=[band])
    def checkpoint(complete,message,data):
        return 0 if control.cancelled() else 1
    options['callback']=checkpoint
    try:result=gdal.Warp(str(path),selected,**options)
    except RuntimeError:
        control.check();raise
    if not result:raise ValueError('Raster preparation failed.')
    result.GetRasterBand(1).SetUnitType(srcband.GetUnitType())
    result.GetRasterBand(1).SetDescription(srcband.GetDescription())
    result.FlushCache()
    import numpy as np
    valid_count=0;minimum=math.inf;maximum=-math.inf
    for row in range(0,result.RasterYSize,128):
        control.check()
        block=result.GetRasterBand(1).ReadAsArray(0,row,result.RasterXSize,min(128,result.RasterYSize-row))
        values=block[np.isfinite(block)];valid_count+=int(values.size)
        if values.size:minimum=min(minimum,float(values.min()));maximum=max(maximum,float(values.max()))
    result=None
    return {'source':spec['path'],'band':band,'kind':kind,'resampling':method,'crs':crs_record,
            'source_geotransform':list(gt),'source_datatype':gdal.GetDataTypeName(srcband.DataType),
            'source_units':srcband.GetUnitType() or None,'source_resolution_warning':'Resampling does not create finer source information.',
            'unit_warning':None if srcband.GetUnitType() else 'No band units declared: obtain source documentation before interpreting physical suitability.',
            'resampling_evidence_ref':spec.get('resampling_evidence_ref'),'unknown_handling':'NaN NoData; all-touched AOI boundary cells retained',
            'grid_changed':changed,'output':str(path.name),'valid_pixels_in_bounding_grid':valid_count,
            'prepared_min_max':[minimum,maximum] if valid_count else None,
            'coverage_warning':None if valid_count else 'No valid pixels: review source coverage and CRS. Missing cells are unknown, not dry.'}


def prepare(job_source,progress=None,cancelled=None):
    from . import __version__
    from .configuration import load_data
    job=load_data(job_source)
    if not isinstance(job,dict) or not isinstance(job.get('output_dir'),str) or not job['output_dir'].strip():raise ValueError('A preparation job needs a new output_dir.')
    base=Path(job_source).resolve().parent if not isinstance(job_source,dict) else Path.cwd()
    job=deepcopy(job)
    if not isinstance(job.get('study_area'),dict) or not job['study_area'].get('path'):raise ValueError('Select a study-area polygon before clipping.')
    datasets=job.get('datasets',[])
    if not isinstance(datasets,list) or any(not isinstance(s,dict) or not s.get('path') for s in datasets):raise ValueError('datasets must list input files with path and unique id.')
    ids=[s.get('id') for s in datasets]
    if any(not isinstance(i,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',i) or i=='study_area' for i in ids) or len(set(ids))!=len(ids):raise ValueError('Each dataset needs a unique id using letters, digits and underscores.')
    for spec in [job['study_area'],*datasets,*([job['grid']['master']] if (job.get('grid') or {}).get('master') else [])]:
        spec['path']=str((base/spec['path']).resolve())
    target=_srs(job.get('target_crs'))
    if not target.IsProjected() or abs(target.GetLinearUnits()-1)>1e-8:raise ValueError('Target CRS must be projected in metres.')
    destination=(base/job['output_dir']).resolve()
    if destination.exists():raise ValueError(f'Preparation output already exists: {destination}. Choose a new folder.')
    control=RunControl(progress,cancelled);control.update(0,'Checking preparation inputs')
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.'+destination.name+'_preparing_',dir=destination.parent))
    scratch=staging/'_working';scratch.mkdir();repairs=[];records=[];db=None;boundary=None
    try:
        ds,layer,boundary_record,features=_geometries(job['study_area'],target,scratch,control,repairs)
        if _family(layer.GetGeomType())!='polygon':raise ValueError('Study boundary must be polygonal.')
        from qgis.core import QgsGeometry
        geoms=[]
        for _,geom in features:
            q=QgsGeometry();q.fromWkb(bytes(geom.ExportToWkb()));geoms.append(q)
        if not geoms:raise ValueError('Study boundary is empty.')
        dissolved=QgsGeometry.unaryUnion(geoms)
        aoi=ogr.CreateGeometryFromWkb(bytes(dissolved.asWkb()))
        if aoi is None or not aoi.IsValid() or aoi.GetArea()<=0:raise ValueError('Study boundary union is invalid.')
        buffer=float(job.get('search_buffer_m',100))
        if not math.isfinite(buffer) or buffer<0:raise ValueError('Search buffer must be finite and nonnegative metres.')
        search=aoi.Buffer(buffer) if buffer else aoi
        gpkg=staging/'prepared.gpkg';db=ogr.GetDriverByName('GPKG').CreateDataSource(str(gpkg))
        boundary=db.CreateLayer('study_area',srs=target,geom_type=ogr.wkbMultiPolygon)
        feature=ogr.Feature(boundary.GetLayerDefn());feature.SetGeometry(_multi(aoi.Clone(),'polygon'));boundary.CreateFeature(feature);feature=None
        rasters=[s for s in datasets if s.get('type')=='raster']
        grid=_grid(job,aoi,target) if rasters else None
        for i,spec in enumerate(datasets):
            control.update(5+75*i/max(1,len(datasets)),'Preparing '+spec['id'])
            if spec.get('type','vector')=='raster':continue
            clip=None if spec.get('clip') is False else aoi if spec.get('clip')=='study_area' else search
            records.append({'id':spec['id'],'type':'vector',**_write_vector(db,spec['id'],spec,target,scratch,clip,control,repairs)})
        db=None;boundary=None;ds=None
        (staging/'rasters').mkdir()
        for spec in rasters:
            control.update(82,'Aligning raster '+spec['id'])
            records.append({'id':spec['id'],'type':'raster',**_raster(spec,staging/'rasters'/(spec['id']+'.tif'),grid,target,gpkg,control)})
        hashes={}
        for spec in [job['study_area'],*datasets,*([job['grid']['master']] if (job.get('grid') or {}).get('master') else [])]:
            parts=companions(spec['path']).values() if Path(spec['path']).suffix.lower()=='.shp' else [Path(spec['path'])]
            for source in parts:
                if source and str(source) not in hashes:hashes[str(source)]=file_hash(source)
        _review_project(staging,target,aoi)
        import csv
        if repairs:
            with (staging/'geometry_repairs.csv').open('w',newline='',encoding='utf-8') as file:
                writer=csv.DictWriter(file,fieldnames=list(repairs[0]));writer.writeheader();writer.writerows(repairs)
        manifest={'workflow':__version__,'gdal':gdal.VersionInfo(),'created_at_utc':datetime.now(timezone.utc).isoformat(),
                  'code_sha256':{p.name:file_hash(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
                  'target_crs':reference_info(target),'study_area':boundary_record,'search_buffer_m':buffer,'grid':grid,
                  'datasets':records,'input_sha256':hashes,'repairs':repairs,
                  'limitations':['Declared CRS transformation is not positional verification against survey/control points.',
                                 'No unit conversions, soil interpolation, semantic class mapping or permissions are inferred.',
                                 'Regridding cannot improve source accuracy; flood-grid changes can alter threshold and MURIEL results.',
                                 'Vector clipping does not certify inventory completeness; geometry repairs require review.']}
        manifest['performance']=control.finish()
        (staging/'preparation_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
        (staging/'preparation_job.json').write_text(json.dumps(job,indent=2,ensure_ascii=False))
        shutil.rmtree(scratch)
        if destination.exists():raise ValueError('Preparation destination was created by another run.')
        staging.rename(destination)
    except BaseException:
        boundary=None
        if db is not None:
            db.Close() if hasattr(db,'Close') else db.Destroy()
            db=None
        shutil.rmtree(staging,ignore_errors=True);raise
    return destination


def prepare_run(config_source, progress=None, cancelled=None):
    """Prepare registered inputs and return a reusable engine configuration."""
    from .configuration import input_specs, resolve_config
    config=resolve_config(config_source)
    options=config.get('preparation') or {}
    if options.get('enabled') is not True:return Path(config_source)
    flood=config['flood']
    if flood['type']=='vector' and config.get('raster_evidence'):
        raise ValueError('Vector flood partitions need polygon evidence joins; aligned raster evidence requires raster-cell mode.')
    output=Path(options.get('output_dir') or (config['output_dir']+'_prepared'))
    if not output.is_absolute():output=Path(config_source).resolve().parent/output
    pairs=list(input_specs(config))
    datasets=[]
    for index,(role,spec) in enumerate(pairs):
        if role=='study_area':continue
        item=deepcopy(spec);item['id']='input_'+str(index)
        item['type']='raster' if (role=='flood' and flood['type']=='raster') or role.startswith('raster_evidence') else 'vector'
        item.setdefault('clip',False if role.startswith('distance_evidence') else 'search_buffer')
        if role=='flood':item['kind']='flood_depth'
        elif item['type']=='raster':item['kind']='categorical' if item.get('units')=='category' else 'continuous'
        datasets.append(item)
    m=config.get('muriel') or {}
    from .engine import muriel_settings
    criteria=muriel_settings(m.get('thresholds')) if m.get('enabled') else {}
    required_buffer=max((criteria.get(key,0) for key in ('receptor_distance_m','municipal_distance_m','destination_distance_m')),default=0)
    buffer=max(float(options.get('search_buffer_m',100)),float(required_buffer))
    job={'study_area':deepcopy(config['study_area']),'datasets':datasets,
         'target_crs':config['crs'],'output_dir':str(output),'search_buffer_m':buffer}
    if flood['type']=='raster':job['grid']={**options.get('grid',{}),'master':deepcopy(flood)}
    prepared=prepare(job,progress,cancelled)
    manifest=json.loads((prepared/'preparation_manifest.json').read_text())
    grid=manifest['grid']
    if grid and not grid['native_master_grid_preserved'] and any(s.get('join','id')=='id' for s in config.get('evidence',[])):
        raise ValueError('Changing the flood grid invalidates ID-joined evidence. Use spatial evidence or explicitly remap IDs; the prepared files remain available for review.')
    if grid and not grid['native_master_grid_preserved'] and config.get('combinations'):
        raise ValueError('Changing the flood grid invalidates combination unit IDs. Explicitly remap modules to the new grid before screening combinations.')
    replacements=iter(datasets)
    original_inputs=[]
    for role,spec in pairs:
        original_inputs.append({'role':role,'path':spec['path'],'layer':spec.get('layer')})
        spec['metadata']={**spec.get('metadata',{}),'preparation_manifest':str(prepared/'preparation_manifest.json'),
                          'original_path':spec['path'],'preparation_scope':'geometry/grid only; source evidence status preserved'}
        if role=='study_area':
            spec.update(path=str(prepared/'prepared.gpkg'),layer='study_area')
        else:
            item=next(replacements)
            if item['type']=='raster':spec.update(path=str(prepared/'rasters'/(item['id']+'.tif')),band=1)
            else:spec.update(path=str(prepared/'prepared.gpkg'),layer=item['id'])
        for key in ('source_crs','crs_evidence_ref','coordinate_operation'):
            spec.pop(key,None)
    offset=(grid or {}).get('master_index_offset') or [0,0]
    original_offset=config.get('unit_id_grid_offset',[0,0])
    config['unit_id_grid_offset']=[a+b for a,b in zip(offset,original_offset)]
    config['preparation']={'enabled':False,'completed_manifest':str(prepared/'preparation_manifest.json'),
                           'original_config_sha256':file_hash(config_source),'original_inputs':original_inputs}
    path=prepared/'prepared_run.json'
    path.write_text(json.dumps(config,indent=2,ensure_ascii=False))
    return path


def check_run_sources(config):
    """Read-only checks before preparation; geometry/fields are checked afterwards."""
    from .configuration import input_specs
    issues=[]
    if config.get('mode') != 'planning' and not config.get('evidence') and not config.get('raster_evidence'):
        issues.append(('WARNING','Evidence','No design/groundwater evidence is registered.','Preparation does not close conditional suitability gates.'))
    for role,spec in input_specs(config):
        try:
            path=Path(spec['path'])
            if not path.is_file():raise ValueError('File does not exist: '+str(path))
            declared=None
            if path.suffix.lower()=='.shp':
                parts=companions(path)
                if not parts['.dbf'] and not spec.get('allow_geometry_only'):raise ValueError('Missing .dbf attribute table; re-export a complete GeoPackage.')
                if parts['.prj']:declared=_srs(parts['.prj'].read_text())
                if not parts['.shx']:issues.append(('WARNING',role,'Missing .shx will be rebuilt on a working copy.','Original files are preserved.'))
            elif (role=='flood' and spec['type']=='raster') or role.startswith('raster_evidence'):
                ds=gdal.Open(str(path))
                if ds is None:raise ValueError('Raster cannot be opened.')
                declared=_srs(ds.GetProjection()) if ds.GetProjection() else None
            else:
                ds=ogr.Open(str(path),0)
                if ds is None:raise ValueError('Vector cannot be opened.')
                layer=ds.GetLayerByName(spec['layer']) if spec.get('layer') else ds.GetLayer(0)
                if layer is None:raise ValueError('Selected layer is absent.')
                declared=layer.GetSpatialRef()
            source_reference(declared,spec)
        except (ValueError,RuntimeError,OSError) as exc:
            issues.append(('ERROR',role,str(exc),'Supply complete data or an evidenced CRS correction.'))
    for path,label in [(config['output_dir'],'Output folder'),((config.get('preparation') or {}).get('output_dir') or config['output_dir']+'_prepared','Prepared inputs')]:
        if Path(path).exists():issues.append(('ERROR',label,'Folder already exists: '+str(path),'Choose a new run folder or use an existing prepared_run.json.'))
    return issues


def _review_project(directory,target,aoi):
    """Portable input QA project, kept separate from opportunity-map results."""
    from qgis.core import (Qgis,QgsApplication,QgsCoordinateReferenceSystem,QgsProject,
                           QgsRasterLayer,QgsRectangle,QgsReferencedRectangle,QgsVectorLayer,QgsFillSymbol)
    if QgsApplication.instance() is None:return
    project=QgsProject();crs=QgsCoordinateReferenceSystem();crs.createFromWkt(target.ExportToWkt());project.setCrs(crs)
    project.setTitle('Prepared GIS inputs · review CRS and coverage')
    source=ogr.Open(str(directory/'prepared.gpkg'),0)
    names=[layer.GetName() for layer in source]
    for name in reversed(names):
        layer=QgsVectorLayer(str(directory/'prepared.gpkg')+'|layername='+name+'|option:NOLOCK=NO',name,'ogr')
        if not layer.isValid():raise ValueError('Prepared review layer cannot be reopened: '+name)
        if name=='study_area':layer.renderer().setSymbol(QgsFillSymbol.createSimple({'color':'transparent','outline_color':'#20766b','outline_width':'0.8'}))
        project.addMapLayer(layer)
    for path in (directory/'rasters').glob('*.tif'):
        raster=QgsRasterLayer(str(path),path.stem+' · source resolution retained in manifest')
        if not raster.isValid():raise ValueError('Prepared review raster cannot be reopened.')
        project.addMapLayer(raster)
        project.layerTreeRoot().findLayer(raster.id()).setItemVisibilityChecked(False)
    x0,x1,y0,y1=aoi.GetEnvelope()
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(QgsRectangle(x0,y0,x1,y1),crs))
    project.setFilePathStorage(Qgis.FilePathType.Relative);project.setFileName(str(directory/'prepared_inputs.qgz'))
    if not project.write():raise ValueError('Cannot save prepared input review project.')
