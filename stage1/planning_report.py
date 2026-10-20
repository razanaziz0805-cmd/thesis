"""Offline, planner-facing action register with no server or dependencies."""
import html


def create_planning_report(out, config, manifest, actions, exported):
    esc = lambda v: html.escape(str(v))
    stats = manifest['planning']
    demo = 'SYNTHETIC DEMONSTRATION · NOT KÖLN-KALK FINDINGS' if config.get('demo') else 'PHASE C · CONDITIONAL PLANNING OPPORTUNITIES'
    cards = [('Flood action areas', str(stats['action_area_count'])),
             ('Mapped flood need', f'{stats["flood_need_area_m2"]/10000:.2f} ha'),
             ('Unknown flood coverage', f'{stats["flood_unknown_area_m2"]/10000:.2f} ha')]
    metrics = ''.join('<div class="card"><strong>'+esc(value)+'</strong>'+esc(label)+'</div>' for label,value in cards)
    files = [('stage1.qgz','Open QGIS project'),('stage1.gpkg','GeoPackage'),('planning_options.csv','NbS planning options'),
             ('planning_shortlist.csv','Action-area register'),('action_membership.csv','Source-unit links'),
             ('decision_audit.csv','Groundwater / MURIEL decisions'),('source_registry.csv','Rule references'),('run_manifest.json','Provenance and limitations')]
    files += [(p.name, 'PDF atlas' if p.name == 'stage1_atlas.pdf' else p.stem) for p in sorted(out.glob('*.pdf'))]
    files = [(file,label) for file,label in files if (out/file).exists()]
    links = ''.join('<a class="button" href="'+esc(file)+'">'+esc(label)+'</a>' for file,label in files)
    rows = ''
    for a,_ in actions:
        heat = 'Unknown' if a['heat_priority_fraction'] is None else f'{a["heat_priority_fraction"]:.0%} priority; {a["heat_unknown_fraction"]:.0%} unknown'
        shares = f'{a["municipal_fraction"]:.0%} city / {a["private_fraction"]:.0%} private / {a["unknown_fraction"]:.0%} unknown'
        rows += ('<tr data-owner="'+esc(a['owner_class'])+'"><th scope="row">'+esc(a['action_label'])+'<br><small>'+esc(a['action_id'])+'</small></th>'
                 '<td>'+esc(f'{a["area_m2"]:,.0f}')+'</td><td>'+esc(f'{a["max_depth_m"]*100:g}')+'</td><td>'+esc(shares)+'</td><td>'+esc(heat)+'</td>'
                 '<td>'+('Edge / NoData: extent uncertain' if a['extent_incomplete'] else 'Mapped interior extent')+'</td>'
                 '<td>'+esc(a['next_action'])+'<details><summary>Why and reference</summary>'+esc(a['explanation'])+'</details></td></tr>')
    if not rows:
        rows = '<tr><td colspan="7">No mapped area meets this depth threshold. Review unknown coverage and retain upstream source-control investigations.</td></tr>'
    figures = ''.join('<figure><a href="'+esc(file)+'"><img loading="lazy" src="'+esc(file)+'" alt="'+esc(title)+'"></a><figcaption>'+esc(title)+'</figcaption></figure>' for title,file in exported)
    limits = ''.join('<li>'+esc(s)+'</li>' for s in manifest['limitations'])
    m = manifest.get('muriel', {})
    muriel = ('<p>MURIEL executed: '+esc(m.get('footprint_count',0))+' observed footprints. <a href="muriel_priority.csv">Read its separate decisions</a>.</p>' if m.get('enabled') else
              '<p>MURIEL is available in advanced setup when receptor footprints, verified municipal land, roads and usable spaces are ready. Flood action areas below do not claim MURIEL qualification.</p>')
    page = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NbS planning brief</title><style>
*{box-sizing:border-box}body{font:16px/1.6 system-ui,sans-serif;color:#243f4a;background:#f2f6f7;margin:0}main{max-width:1380px;margin:auto;padding:28px}h1{font-size:38px;line-height:1.2}h2{font-size:24px}a{color:#176e68}.banner{background:#fff0dd;border-left:5px solid #b26f35;padding:12px;font-weight:700}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card,.panel,figure{background:white;border:1px solid #d5e1e4;border-radius:8px;padding:18px}.card strong{display:block;font-size:32px}.links{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}.button{background:white;border:1px solid #b6cacf;padding:8px 12px;border-radius:5px;text-decoration:none}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #d5e1e4;padding:10px}th small{font-weight:400;color:#536d76}summary{cursor:pointer;color:#176e68}details{margin-top:8px}input,select{font:inherit;padding:8px;border:1px solid #9eb7bf;border-radius:4px;margin:5px 12px 12px 0}.maps{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(440px,100%),1fr));gap:18px}figure{margin:0}img{width:100%}figcaption{font-weight:600}tr[hidden]{display:none}code{background:#e9f1f2;padding:2px}@media(max-width:650px){main{padding:14px}.metrics{grid-template-columns:1fr}h1{font-size:30px}}
</style></head><body><main>'''
    page += '<p class="banner">'+esc(demo)+'</p><h1>Flood-ready neighbourhood planning</h1><p>'+esc(config['area_label'])+' · '+esc(config['scenario_id'])+' · Flood need ≥'+esc(f'{config["flood_threshold_m"]*100:g}')+' cm</p><div class="metrics">'+metrics+'</div><nav class="links" aria-label="Result files">'+links+'</nav>'
    page += '<section class="panel"><h2>Use this brief in a planning meeting</h2><ol><li>Locate flood action areas and inspect nearby buildings, access and existing retention.</li><li>Compare surface-matched NbS concepts, ownership routes and documented heat context.</li><li>Assign the next investigation; qualify physical modules in the advanced engine before simulation.</li></ol><p>In QGIS, open <b>stage1.qgz</b>, choose a map theme, then use <b>Identify Features</b>. Every unit retains its reason and reference. All retained concepts are <b>CONDITIONAL</b>; a mapped opportunity is not a design approval.</p>'+muriel+'</section>'
    page += '<h2>Flood action areas and next steps</h2><p>'+esc(stats['browsing_order'])+' These areas contain mapped local need; they do not define a connected source or receiving-water system.</p><label>Find an action <input id="search" type="search" placeholder="Area ID, owner or action"></label><label>Delivery category <select id="owner"><option value="all">All</option>'+''.join('<option value="'+k+'">'+v+'</option>' for k,v in [('municipal','Municipal'),('private','Private'),('other_public','Other public'),('mixed','Mixed'),('conflict','Ownership conflict'),('unknown','Unknown')])+'</select></label><p id="count" aria-live="polite"></p><div class="scroll panel"><table><thead><tr><th>Action area</th><th>Mapped m²</th><th>Max depth cm</th><th>Ownership shares</th><th>Heat context</th><th>Extent evidence</th><th>Next step</th></tr></thead><tbody id="actions">'+rows+'</tbody></table></div>'
    page += '<h2>Map sheets</h2><div class="maps">'+(figures or '<p>Printing was off. All analytical maps remain available as QGIS themes.</p>')+'</div><details class="panel"><summary>Method and interpretation</summary><ul>'+limits+'</ul><p>Palette and workflow: Abdulaziz (2026), Table 4.2; §§5.1, 5.4–5.5. Local infiltration rules: Stadt Köln (2022), as cited in thesis; current authority review outstanding. Full source names, URLs and verification status are in source_registry.csv.</p></details>'
    page += '''<script>
const search=document.getElementById('search'),owner=document.getElementById('owner'),rows=[...document.querySelectorAll('#actions tr[data-owner]')];
function filter(){let n=0;for(const row of rows){row.hidden=!(row.textContent.toLowerCase().includes(search.value.toLowerCase().trim())&&(owner.value==='all'||owner.value===row.dataset.owner));if(!row.hidden)n++;}document.getElementById('count').textContent=n+' action areas shown';}
search.addEventListener('input',filter);owner.addEventListener('change',filter);filter();
</script></main></body></html>'''
    (out/'report.html').write_text(page,encoding='utf-8')
