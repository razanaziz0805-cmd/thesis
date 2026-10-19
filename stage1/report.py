"""Offline results dashboard and an actionable evidence task register."""
from collections import Counter
import csv
import html
import json


def create_report(out, config, layers, manifest, exported, audit):
    escape=lambda value: html.escape(str(value))
    counts={}
    for name,records in layers:
        if name=='nbs_opportunities':
            by_design={design:Counter() for design in config['designs']}
            for attributes,_ in records:
                by_design[attributes['design']][attributes['status']]+=1
            for design,values in by_design.items():
                counts[design]={s:values[s] for s in ('ADMISSIBLE','CONDITIONAL','FAIL','NOT_APPLICABLE')}
        else:
            field='planning_class' if name=='muriel_priority' else 'hotspot_class' if name=='muriel_hotspots' else 'context_type' if name=='muriel_context' else 'status'
            counts[name]=dict(sorted(Counter(a[field] for a,_ in records).items()))
    (out/'summary.json').write_text(json.dumps(counts,indent=2))
    tasks={}
    for row in audit:
        if row['status'] not in ('FAIL','CONDITIONAL'): continue
        key=(row['rule_id'],row['status'],row['closure'],row['responsible_party'])
        if key not in tasks:
            tasks[key]={'rule_id':row['rule_id'],'status':row['status'],'evaluation_count':0,
                        'action':row['closure'],'responsible_party':row['responsible_party'],
                        'citation':row['citation'],'source_url':row['source_url']}
        tasks[key]['evaluation_count']+=1
    tasks=sorted(tasks.values(),key=lambda row:(-row['evaluation_count'],row['rule_id'],row['status']))
    if tasks:
        with (out/'evidence_tasks.csv').open('w',encoding='utf-8',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=list(tasks[0])); writer.writeheader(); writer.writerows(tasks)
    demo=bool(config.get('demo'))
    banner='SYNTHETIC DEMONSTRATION — NOT KÖLN-KALK RESULTS' if demo else 'SPATIAL SCREENING — review evidence before design decisions'
    need=counts.get('intervention_need',{})
    cards=[('Analysis units',manifest['unit_count']),('Depth meets intervention threshold',need.get('YES',0)),('Unknown flood depths',need.get('UNKNOWN',0))]
    if manifest.get('muriel',{}).get('enabled'):
        cards.append(('MURIEL footprints',manifest['muriel']['footprint_count']))
    card_html=''.join('<div class="metric"><strong>'+escape(value)+'</strong><span>'+escape(label)+'</span></div>' for label,value in cards)
    links=[('stage1.qgz','QGIS project'),('candidate_register.csv','Candidates'),('decision_audit.csv','All rule decisions'),('source_registry.csv','References'),('run_manifest.json','Run manifest')]
    for file,label in [('stage1_atlas.pdf','Full PDF atlas'),('muriel_atlas.pdf','MURIEL PDF atlas'),('muriel_priority.csv','MURIEL decisions'),('evidence_tasks.csv','Evidence tasks')]:
        if (out/file).exists(): links.append((file,label))
    links.extend((p.name,'PDF sheet '+str(i+1)) for i,p in enumerate(sorted(out.glob('_sheet_*.pdf'))))
    link_html=''.join('<a class="button" href="'+escape(file)+'">'+escape(label)+'</a>' for file,label in links)
    limits=''.join('<li>'+escape(value)+'</li>' for value in manifest['limitations'])
    rows=''.join('<tr><th scope="row">'+escape(k)+'</th><td>'+escape('; '.join(str(status)+': '+str(n) for status,n in values.items()))+'</td></tr>' for k,values in counts.items())
    task_rows=''.join('<tr><td>'+escape(row['status'])+'</td><td>'+escape(row['rule_id'])+'</td><td>'+str(row['evaluation_count'])+'</td><td>'+escape(row['action'])+'<br><small>'+escape(row['responsible_party'])+'</small></td></tr>' for row in tasks[:20])
    figures=''
    for name,file in exported:
        lower=name.lower()
        group='muriel' if 'muriel' in lower else 'flood' if 'flood intervention' in lower else 'groundwater' if 'infiltration pathway' in lower else 'ownership' if 'ownership' in lower else 'combinations' if 'combined systems' in lower else 'nbs'
        figures+='<figure data-group="'+group+'" data-name="'+escape(lower)+'"><a href="'+escape(file)+'"><img loading="lazy" src="'+escape(file)+'" alt="'+escape(name)+'"></a><figcaption>'+escape(name)+'</figcaption></figure>'
    m=manifest.get('muriel',{})
    muriel=''
    if m.get('enabled'):
        muriel='<p>MURIEL: '+escape(m['footprint_count'])+' observed footprints; '+escape(m['destination_count'])+' eligible destinations; '+escape(m['unknown_source_unit_count'])+' unknown source units. Footprint mode: <code>'+escape(m['thresholds']['footprint_mode'])+'</code>. <a href="muriel_summary.json">Criteria and counts</a>. Missing source coverage can conceal additional hotspots.</p>'
    if not exported: figures='<p>Printing was turned off for this run. All analytical layers and explanations are available in the QGIS project. Enable printing in a new run for PNG/PDF sheets.</p>'
    doc='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Stage 1 results</title>
<style>
:root{--ink:#213f4a;--teal:#20766b;--line:#d5e1e4}*{box-sizing:border-box}body{font:16px/1.55 system-ui,sans-serif;background:#f3f7f8;color:var(--ink);margin:0}main{max-width:1280px;margin:auto;padding:28px 24px}h1{font-size:38px;line-height:1.15}h2{margin-top:32px}.banner{border-left:5px solid #aa4d43;background:#fff0df;padding:14px 18px;font-weight:700}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}.metric{background:white;padding:20px;border:1px solid var(--line);border-radius:9px}.metric strong{display:block;font-size:30px}.metric span{font-size:14px}a{color:#116b65}.actions{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}.button{padding:9px 13px;background:white;border:1px solid var(--line);border-radius:6px;text-decoration:none}.panel{background:white;padding:20px;border:1px solid var(--line);border-radius:9px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:10px}small{color:#526972}.scroll{overflow-x:auto}.maps{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(440px,100%),1fr));gap:20px}figure{margin:0;padding:12px;background:white;border:1px solid var(--line);border-radius:8px}figure[hidden]{display:none}img{width:100%}figcaption{font-weight:600;margin-top:8px}.filters{display:flex;flex-wrap:wrap;gap:16px;margin:16px 0}input,select{padding:9px;border:1px solid #9fb3bc;border-radius:5px;font:inherit}code{background:#edf2f4;padding:2px 4px}summary{cursor:pointer;font-weight:600}.legend{display:flex;flex-wrap:wrap;gap:14px}.legend span{border-left:8px solid;padding-left:8px}.legend .pass{border-color:#23766a}.legend .conditional{border-color:#e8b04a}.legend .fail{border-color:#b94c52}.legend .unknown{border-color:#b5bdc6}
</style></head><body><main>'''
    doc+='<p class="banner">'+escape(banner)+'</p><h1>Stage 1 · opportunity mapping</h1><p>'+escape(config['area_label'])+' · '+escape(config['scenario_id'])+' · Intervention depth ≥'+escape(f"{config['flood_threshold_m']*100:g}")+' cm</p><div class="metrics">'+card_html+'</div><nav class="actions" aria-label="Result files">'+link_html+'</nav>'
    doc+='<section class="panel"><h2 style="margin-top:0">Explore your results in QGIS</h2><ol><li>Open <b>stage1.qgz</b>, keeping its result folder together.</li><li>Choose a named <b>map theme</b> to view one result at a time.</li><li>Use <b>Identify Features</b> and read <code>explanation</code> for the decision, reason, evidence and references.</li></ol><div class="legend"><span class="pass">Admissible: evidenced screening gates</span><span class="conditional">Conditional: evidence or decision needed</span><span class="fail">Fail: an applicable gate is not met</span><span class="unknown">Unknown / not applicable: read the feature</span></div>'+muriel+'</section>'
    doc+='<h2>What needs attention</h2><p>These are repeated rule evaluations across units and designs, not counts of independent sites. The full task register retains references. Address missing evidence; do not replace unknown values with approvals.</p><details class="panel"><summary>Review outstanding actions (top 20)</summary><div class="scroll"><table><thead><tr><th>Status</th><th>Rule</th><th>Evaluations</th><th>Action and responsible party</th></tr></thead><tbody>'+task_rows+'</tbody></table></div></details><details class="panel"><summary>Interpretation and limitations</summary><ul>'+limits+'</ul></details>'
    doc+='<h2>Map sheets</h2><div class="filters"><label>Find a map <input id="search" type="search" placeholder="For example: tree or MURIEL"></label><label>Map group <select id="group"><option value="all">All maps</option><option value="flood">Flood need</option><option value="groundwater">Groundwater</option><option value="ownership">Ownership</option><option value="nbs">NbS</option><option value="combinations">Combinations</option><option value="muriel">MURIEL</option></select></label></div><p id="map-count" aria-live="polite"></p><div class="maps">'+figures+'</div><details class="panel"><summary>Class counts</summary><p>Counts are analysis units per design; they are not delivered projects or measured flood benefits.</p><div class="scroll"><table><thead><tr><th>Layer / design</th><th>Counts</th></tr></thead><tbody>'+rows+'</tbody></table></div></details>'
    doc+='''<script>
const search=document.getElementById('search'), group=document.getElementById('group'), figures=[...document.querySelectorAll('figure')];
function filterMaps(){const query=search.value.toLowerCase().trim();let count=0;for(const item of figures){item.hidden=!(item.dataset.name.includes(query)&&(group.value==='all'||item.dataset.group===group.value));if(!item.hidden)count++;}document.getElementById('map-count').textContent=count+' map sheets shown';}
search.addEventListener('input',filterMaps);group.addEventListener('change',filterMaps);filterMaps();
</script></main></body></html>'''
    (out/'report.html').write_text(doc,encoding='utf-8')
