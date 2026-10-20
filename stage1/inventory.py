"""Read-only GIS inventory. Attribute values and asset locations are not exported."""
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

from osgeo import gdal, ogr, osr

gdal.UseExceptions()


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda: file.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def reference_info(srs):
    if not srs:
        return None
    srs = srs.Clone()
    srs.AutoIdentifyEPSG()
    return {'authority': srs.GetAuthorityName(None), 'code': srs.GetAuthorityCode(None),
            'name': srs.GetName(), 'wkt': srs.ExportToWkt()}


def companions(path):
    path = Path(path)
    found = {p.suffix.lower():p for p in path.parent.iterdir() if p.is_file() and p.stem.lower()==path.stem.lower()}
    return {suffix:found.get(suffix) for suffix in ('.shp','.shx','.dbf','.prj','.cpg')}


def inspect_file(path, statistics=True):
    path = Path(path).resolve()
    result = {'name':path.name, 'path':str(path), 'issues':[], 'layers':[]}
    if not path.is_file():
        return {**result,'status':'MISSING','issues':['File does not exist.']}
    result.update(bytes=path.stat().st_size, sha256=file_hash(path))
    extension = path.suffix.lower()
    if extension == '.shp':
        # Inspect bare geometry without recreating indices or changing uploads.
        parts = companions(path)
        result['components'] = {k:str(v) if v else None for k,v in parts.items()}
        with path.open('rb') as file:
            header = file.read(100)
            if len(header)!=100 or struct.unpack('>i',header[:4])[0]!=9994:
                raise ValueError(f'Invalid shapefile header: {path.name}')
            result['shape_type'] = struct.unpack('<i',header[32:36])[0]
            result['raw_extent'] = list(struct.unpack('<4d',header[36:68]))
            count=0
            while True:
                record=file.read(8)
                if not record:break
                if len(record)!=8:raise ValueError('Truncated shapefile record header.')
                length=struct.unpack('>2i',record)[1]*2
                if length<4 or file.tell()+length>result['bytes']:raise ValueError('Truncated shapefile record.')
                file.seek(length,1);count+=1
            result['geometry_records']=count
        result['missing_components']=[k for k in ('.shx','.dbf','.prj') if not parts[k]]
        if not parts['.dbf']:result['issues'].append('Attribute table (.dbf) is missing; semantic classes and evidence cannot be recovered from geometry.')
        if not parts['.prj']:result['issues'].append('CRS definition (.prj) is missing; source CRS confirmation is required.')
        if not parts['.shx']:result['issues'].append('Index (.shx) is missing; it can be rebuilt on a working copy.')
        if parts['.prj']:
            srs=osr.SpatialReference();srs.SetFromUserInput(parts['.prj'].read_text());result['crs']=reference_info(srs)
        else:result['crs']=None
        if not parts['.shx']:
            result['status']='INCOMPLETE'
            return result
    if extension in ('.tif','.tiff'):
        ds=gdal.Open(str(path))
        if not ds:raise ValueError('Raster cannot be opened.')
        gt=ds.GetGeoTransform();srs=osr.SpatialReference(wkt=ds.GetProjection()) if ds.GetProjection() else None
        result.update(kind='raster',crs=reference_info(srs),width=ds.RasterXSize,height=ds.RasterYSize,
                      geotransform=list(gt),north_up=not(gt[2] or gt[4]) and gt[1]>0 and gt[5]<0,bands=[])
        for i in range(1,ds.RasterCount+1):
            band=ds.GetRasterBand(i);nodata=band.GetNoDataValue()
            if nodata is not None and not math.isfinite(nodata):nodata='NaN' if math.isnan(nodata) else str(nodata)
            entry={'band':i,'type':gdal.GetDataTypeName(band.DataType),'nodata':nodata,
                                          'unit':band.GetUnitType() or None,'description':band.GetDescription() or None}
            if statistics:
                approximate=ds.RasterXSize*ds.RasterYSize>2000000
                try:entry['min_max']=list(band.ComputeRasterMinMax(approximate))
                except RuntimeError:
                    entry['min_max']=None;result['issues'].append('No valid raster statistics; check NoData/coverage.')
                entry['approximate_statistics']=approximate
            result['bands'].append(entry)
        if srs is None:result['issues'].append('Raster CRS is missing.')
    elif extension=='.xml':
        tree=ET.parse(path)
        names=[e.text for e in tree.iter() if e.tag.split('}')[-1] in ('WKID','LatestWKID') and e.text]
        result.update(kind='metadata_only',declared_codes=sorted(set(names)))
        result['issues'].append('Metadata only; the spatial dataset and attributes are not present.')
    else:
        ds=ogr.Open(str(path),0)
        if not ds:raise ValueError('Vector cannot be opened; check all shapefile components.')
        result['kind']='vector'
        for layer in ds:
            result['layers'].append({'name':layer.GetName(),'features':layer.GetFeatureCount(),
                                     'geometry_type':ogr.GeometryTypeToName(layer.GetGeomType()),'crs':reference_info(layer.GetSpatialRef()),
                                     'fields':[{'name':f.GetName(),'type':f.GetTypeName()} for f in layer.schema]})
    result['status']='INCOMPLETE' if result['issues'] else 'READABLE'
    return result


def inspect_paths(paths, output_dir=None):
    records=[];seen={}
    for path in paths:
        try:row=inspect_file(path)
        except (RuntimeError,ValueError,OSError,ET.ParseError) as exc:
            row={'name':Path(path).name,'path':str(path),'status':'ERROR','issues':[str(exc)]}
        digest=row.get('sha256')
        if digest and digest in seen:
            row['duplicate_of']=seen[digest]
            row['issues'].append('Byte-identical file content; do not count this as an independent data source.')
        elif digest:seen[digest]=row['path']
        records.append(row)
    if output_dir:
        out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
        (out/'inventory.json').write_text(json.dumps(records,indent=2,ensure_ascii=False,allow_nan=False))
        with (out/'inventory.csv').open('w',newline='',encoding='utf-8') as file:
            writer=csv.DictWriter(file,fieldnames=['name','status','bytes','sha256','duplicate_of','issues']);writer.writeheader()
            for row in records:writer.writerow({key:'; '.join(row.get(key,[])) if key=='issues' else row.get(key) for key in writer.fieldnames})
    return records
