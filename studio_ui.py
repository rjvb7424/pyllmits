"""studio_ui.py - the single-page app served by studio.py (HTML/CSS/JS).

Redesign notes (behaviour preserved; markup + styling + feedback changed):
  * "Ember" design system via CSS tokens (warm accent, tool-like density).
  * Tiered buttons (primary / secondary / ghost / danger) so each screen has
    exactly one primary action.
  * Configs shown as a card grid (was a dense table) with an obvious Run action.
  * alert() replaced by inline toasts; empty/loading states added; visible focus
    rings; 44px-ish controls; responsive at 360 / 768 / 1440.
All JS function names, element IDs, handlers, and API calls are unchanged.
"""

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Crafter Studio</title>
<style>
  :root{
    --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s6:24px; --s8:32px; --s12:48px;
    --bg:#0e1116; --surface:#171b22; --raised:#1e232c; --line:#2a303b; --line2:#363d4a;
    --text:#eef1f6; --muted:#9aa4b2; --faint:#6b7480;
    --accent:#e8863c; --accent-press:#cf6f2c; --on-accent:#1a1206;
    --ok:#3fb27f; --danger:#e05656; --info:#5aa0e0;
    --radius:6px; --radius-lg:10px; --shadow:0 1px 2px rgba(0,0,0,.4);
    --ui:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
    --mono:'JetBrains Mono',ui-monospace,'SF Mono',Menlo,Consolas,monospace;
    /* config table columns: Name | Size | Objective | Trials | Turns | Models | Actions */
    --cfg-cols:minmax(170px,1.4fr) 76px 190px 66px 66px minmax(220px,2fr) 310px;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 var(--ui);-webkit-font-smoothing:antialiased}
  h1,h2,h3{margin:0;line-height:1.2;font-weight:600;letter-spacing:-.01em}
  h2{font-size:22px} h3{font-size:18px}
  a{color:var(--accent)}
  .mono{font-family:var(--mono)}
  .muted{color:var(--muted)} .faint{color:var(--faint)}
  .flex{display:flex;gap:var(--s3);align-items:center;flex-wrap:wrap}
  .between{display:flex;gap:var(--s3);align-items:center;justify-content:space-between;flex-wrap:wrap}
  .hidden{display:none!important}
  ::selection{background:var(--accent);color:var(--on-accent)}

  header{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:var(--s4);
    padding:var(--s3) var(--s6);background:var(--surface);border-bottom:1px solid var(--line)}
  .brand{display:flex;align-items:center;gap:var(--s2);font-weight:700;font-size:16px;letter-spacing:-.02em}
  .brand .mark{width:20px;height:20px;border-radius:5px;
    background:linear-gradient(150deg,var(--accent),#b8531e);box-shadow:inset 0 0 0 1px rgba(255,255,255,.15)}
  nav{display:flex;gap:var(--s1);margin-left:var(--s2)}
  .tab{appearance:none;border:0;background:transparent;color:var(--muted);cursor:pointer;
    font:500 14px var(--ui);padding:var(--s2) var(--s3);border-radius:var(--radius);min-height:36px}
  .tab:hover{color:var(--text);background:var(--raised)}
  .tab.active{color:var(--on-accent);background:var(--accent)}
  .tab.active:hover{background:var(--accent-press)}

  main{padding:var(--s6);max-width:1360px;margin:0 auto}

  .card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius-lg);
    padding:var(--s6);margin-bottom:var(--s4)}
  .card h3{margin-bottom:var(--s4)}
  .sub{color:var(--muted);font-size:13px;margin-top:6px}

  label{display:block;color:var(--muted);font-size:13px;font-weight:500;margin:var(--s3) 0 var(--s1)}
  input,select,textarea{width:100%;background:var(--raised);color:var(--text);
    border:1px solid var(--line2);border-radius:var(--radius);padding:0 var(--s3);min-height:40px;
    font:14px var(--ui);transition:border-color .12s,box-shadow .12s}
  textarea{min-height:130px;padding:var(--s2) var(--s3);font-family:var(--mono);font-size:12.5px;line-height:1.55;resize:vertical}
  input:hover,select:hover,textarea:hover{border-color:var(--faint)}
  input:focus,select:focus,textarea:focus,button:focus-visible,.tab:focus-visible,.cell:focus-visible,.swatch:focus-visible{
    outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(232,134,60,.25)}
  select{appearance:none;
    background-image:linear-gradient(45deg,transparent 50%,var(--muted) 50%),linear-gradient(135deg,var(--muted) 50%,transparent 50%);
    background-position:calc(100% - 16px) 17px,calc(100% - 11px) 17px;background-size:5px 5px,5px 5px;
    background-repeat:no-repeat;padding-right:var(--s8)}
  .row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:var(--s3)}
  .check{display:inline-flex;align-items:center;gap:var(--s2);color:var(--text);font-size:14px;min-height:40px;cursor:pointer}
  .check input{width:18px;height:18px;min-height:0;accent-color:var(--accent)}

  button{font:600 14px var(--ui);border-radius:var(--radius);cursor:pointer;min-height:40px;
    padding:0 var(--s4);border:1px solid transparent;display:inline-flex;align-items:center;
    justify-content:center;gap:var(--s2);transition:background .12s,border-color .12s,transform .04s}
  button:active{transform:translateY(1px)}
  .btn-primary{background:var(--accent);color:var(--on-accent);border-color:var(--accent)}
  .btn-primary:hover{background:var(--accent-press);border-color:var(--accent-press)}
  .btn-secondary{background:var(--raised);color:var(--text);border-color:var(--line2)}
  .btn-secondary:hover{border-color:var(--faint);background:#242a34}
  .btn-ghost{background:transparent;color:var(--muted);border-color:transparent}
  .btn-ghost:hover{background:var(--raised);color:var(--text)}
  .btn-danger{background:transparent;color:var(--danger);border-color:var(--line2)}
  .btn-danger:hover{background:rgba(224,86,86,.12);border-color:var(--danger)}
  .btn-sm{min-height:34px;padding:0 var(--s3);font-size:13px}

  .pill{display:inline-flex;align-items:center;gap:6px;background:var(--raised);border:1px solid var(--line);
    border-radius:999px;padding:3px 10px;font-size:12px;color:var(--muted);font-family:var(--mono)}
  .pill.accent{color:var(--accent);border-color:rgba(232,134,60,.35)}

  /* exec-style table: header + rows share the same fixed column tracks */
  .cfg-table{display:flex;flex-direction:column;gap:var(--s2)}
  .cfg-head,.cfg{display:grid;grid-template-columns:var(--cfg-cols);gap:var(--s4);
    padding:var(--s3) var(--s4);border:1px solid transparent}
  .cfg-head>*,.cfg>*{min-width:0}                    /* keep columns from bleeding */
  .cfg-head{color:var(--muted);font-size:11.5px;font-weight:600;text-transform:uppercase;
    letter-spacing:.05em;padding-top:0;padding-bottom:var(--s1);align-items:center}
  .cfg{background:var(--surface);border-color:var(--line);border-radius:var(--radius-lg);
    min-height:92px;align-items:center}                /* ~3 lines tall, content vertically centered */
  .cfg:hover{border-color:var(--line2)}
  .cfg .name{font-weight:600;font-size:15px;overflow:hidden;text-overflow:ellipsis;
    display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}
  .cfg .cell{color:var(--text);font-family:var(--mono);font-size:13px}
  .cfg .obj .pill{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .cfg .models{display:flex;gap:6px;flex-wrap:wrap;align-content:center;overflow:hidden;
    max-height:72px;                                  /* about 3 rows of pills, then fade */
    -webkit-mask-image:linear-gradient(to bottom,#000 78%,transparent);
    mask-image:linear-gradient(to bottom,#000 78%,transparent)}
  .cfg .actions{display:flex;gap:var(--s2);justify-content:flex-start;align-items:center;flex-wrap:wrap}

  .empty{text-align:center;color:var(--muted);padding:var(--s12) var(--s4);border:1px dashed var(--line2);border-radius:var(--radius-lg)}
  .empty b{color:var(--text);display:block;margin-bottom:var(--s2);font-size:16px}

  .grid-wrap{overflow:auto;border:1px solid var(--line);border-radius:var(--radius);background:#0b0d11;padding:var(--s3);max-height:70vh}
  #grid{display:grid;gap:1px;width:max-content}
  .cell{width:22px;height:22px;border-radius:3px;cursor:pointer;outline-offset:-2px}
  .cell:hover{box-shadow:inset 0 0 0 2px rgba(255,255,255,.35)}
  #palette{display:flex;flex-wrap:wrap;gap:var(--s2);margin:var(--s2) 0 var(--s4)}
  .swatch{display:inline-flex;align-items:center;gap:var(--s2);padding:0 var(--s3);min-height:40px;
    border:1px solid var(--line2);border-radius:var(--radius);cursor:pointer;background:var(--raised);font-size:13px;color:var(--text)}
  .swatch:hover{border-color:var(--faint)}
  .swatch.sel{border-color:var(--accent);box-shadow:0 0 0 2px rgba(232,134,60,.25)}
  .dot{width:16px;height:16px;border-radius:4px;box-shadow:inset 0 0 0 1px rgba(0,0,0,.3)}
  pre{background:#0b0d11;border:1px solid var(--line);border-radius:var(--radius);padding:var(--s3);
    overflow:auto;font-family:var(--mono);font-size:12.5px;line-height:1.25;color:var(--text)}

  .model{background:var(--raised);border:1px solid var(--line);border-radius:var(--radius-lg);padding:var(--s4);margin-bottom:var(--s3)}

  #liveView{width:100%;height:70vh;border:1px solid var(--line);border-radius:var(--radius);background:#0b0d11}

  .plot{max-width:100%;border:1px solid var(--line);border-radius:var(--radius);margin:var(--s2) 0;background:#fff;display:block}
  #plots>div{margin-bottom:var(--s4)}

  #toasts{position:fixed;right:var(--s6);bottom:var(--s6);z-index:50;display:flex;flex-direction:column;gap:var(--s2)}
  .toast{background:var(--raised);border:1px solid var(--line2);border-left:3px solid var(--accent);
    border-radius:var(--radius);padding:var(--s3) var(--s4);font-size:13.5px;box-shadow:var(--shadow);max-width:340px;animation:slidein .18s ease}
  .toast.ok{border-left-color:var(--ok)} .toast.err{border-left-color:var(--danger)}
  @keyframes slidein{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

  @media (max-width:768px){
    header{padding:var(--s3) var(--s4)} main{padding:var(--s4)}
    .card{padding:var(--s4)} nav{margin-left:0}
    .brand span{display:none}
  }
  @media (max-width:820px){
    .cfg-head{display:none}
    .cfg{grid-template-columns:1fr;gap:var(--s2);min-height:0;align-items:stretch;padding:var(--s3) var(--s4)}
    .cfg .models{-webkit-mask-image:none;mask-image:none;max-height:none;flex-wrap:wrap}
    .cfg .name{-webkit-line-clamp:2}
    .cfg .actions{justify-content:flex-start}
    .cfg .actions .btn-primary{flex:1}
  }
  @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<header>
  <div class="brand"><span class="mark"></span><span>Crafter Studio</span></div>
  <nav role="tablist">
    <button class="tab active" data-tab="configs" role="tab">Configs</button>
    <button class="tab" data-tab="run" role="tab">Run</button>
    <button class="tab" data-tab="graphs" role="tab">Graphs</button>
    <button class="tab" data-tab="videos" role="tab">Videos</button>
  </nav>
</header>

<main>
  <!-- CONFIGS -->
  <section id="tab-configs">
    <div class="between" style="margin-bottom:var(--s4)">
      <h2>Configs</h2>
      <button class="btn-primary" onclick="newConfig()">+ New config</button>
    </div>
    <div class="cfg-table" id="cfgRows"></div>
  </section>

  <!-- EDITOR (reached via New / Edit / Duplicate) -->
  <section id="tab-editor" class="hidden">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Editor</h2><div class="sub"><span class="pill" id="edPath">unsaved</span></div></div>
      <div class="flex">
        <button class="btn-secondary" onclick="go('configs')">Cancel</button>
        <button class="btn-danger hidden" id="edDelete" onclick="deleteCurrentConfig()">Delete</button>
        <button class="btn-primary" onclick="saveConfig()">Save config</button>
      </div>
    </div>

    <div class="card"><h3>Experiment</h3>
      <div class="row">
        <div><label for="e_name">Name</label><input id="e_name">
          <div class="sub" style="margin-top:4px">This is also the config's file name (and run folder) - letters, numbers, underscores and hyphens only.</div>
        </div>
        <div><label for="e_trials">Trials</label><input id="e_trials" type="number" min="1"></div>
        <div><label for="e_turns">Max turns</label><input id="e_turns" type="number" min="1"></div>
        <div><label for="e_seed">Seed</label><input id="e_seed" type="number"></div>
      </div>
      <div class="row">
        <div><label for="e_vres">Video resolution</label><input id="e_vres" type="number"></div>
        <div><label for="e_vfps">Video fps</label><input id="e_vfps" type="number"></div>
        <div><label for="e_vid">Record video</label><select id="e_vid"><option value="true">yes</option><option value="false">no</option></select></div>
        <div><label for="e_same">Same world each trial</label><select id="e_same"><option value="true">yes</option><option value="false">no</option></select></div>
      </div>
    </div>

    <div class="card"><h3>Objective</h3>
      <div class="row">
        <div><label for="o_type">Type</label><select id="o_type"><option>achievement</option><option>inventory</option></select></div>
        <div><label for="o_target">Target</label><select id="o_target"></select></div>
        <div><label for="o_item">Item</label><input id="o_item"></div>
        <div><label for="o_amount">Amount</label><input id="o_amount" type="number" min="1"></div>
      </div>
    </div>

    <div class="card"><h3>World builder</h3>
      <div class="sub" style="margin-bottom:var(--s4)">Pick a tile, then click or drag on the grid to paint. Exactly one Player tile sets the start.</div>
      <div class="row" style="max-width:640px">
        <div><label for="w_w">Width</label><input id="w_w" type="number" min="2" onchange="resizeGrid()"></div>
        <div><label for="w_h">Height</label><input id="w_h" type="number" min="2" onchange="resizeGrid()"></div>
        <div><label for="w_static">Static</label><select id="w_static"><option value="true">yes</option><option value="false">no</option></select></div>
        <div><label for="w_day">Freeze daylight</label><select id="w_day"><option value="true">yes</option><option value="false">no</option></select></div>
      </div>
      <label>Palette</label>
      <div id="palette"></div>
      <div class="grid-wrap"><div id="grid"></div></div>
      <div class="flex" style="margin-top:var(--s3)">
        <button class="btn-secondary btn-sm" onclick="clearGrid()">Clear</button>
        <button class="btn-secondary btn-sm" onclick="previewWorld()">Preview (engine)</button>
      </div>
      <pre id="previewOut" class="hidden" style="margin-top:var(--s3)"></pre>
    </div>

    <div class="card"><h3>Models</h3>
      <div id="models"></div>
      <button class="btn-secondary btn-sm" onclick="addModel()">+ Add model</button>
    </div>

    <div class="card"><h3>Prompt</h3>
      <div class="flex" style="margin-bottom:var(--s2)">
        <label class="check"><input type="checkbox" id="p_leg"> legend</label>
        <label class="check"><input type="checkbox" id="p_inv"> inventory</label>
        <label class="check"><input type="checkbox" id="p_ach"> achievements</label>
        <label class="check"><input type="checkbox" id="p_act"> action list</label>
      </div>
      <label for="p_sys">System</label><textarea id="p_sys"></textarea>
      <label for="p_user">User</label><textarea id="p_user"></textarea>
      <div class="row" style="max-width:420px">
        <div><label for="a_strat">Parse strategy</label><input id="a_strat"></div>
        <div><label for="a_fall">Fallback action</label><input id="a_fall"></div>
      </div>
    </div>
  </section>

  <!-- RUN -->
  <section id="tab-run" class="hidden">
    <div class="card">
      <div class="between">
        <div><h2>Run</h2>
          <div class="flex" style="margin-top:var(--s2)">
            <select id="runConfigPick" onchange="pickRunConfig(this.value)" style="min-width:300px" aria-label="Config to run"></select>
          </div>
        </div>
        <div class="flex">
          <button class="btn-primary" onclick="runGo()">&#9654;&nbsp;Go</button>
          <button class="btn-secondary" onclick="runPause()">&#10073;&#10073;&nbsp;Pause</button>
          <button class="btn-secondary" onclick="runResume()">&#9654;&nbsp;Resume</button>
          <button class="btn-secondary" onclick="runRestart()">&#8635;&nbsp;Restart</button>
          <button class="btn-danger" onclick="runStop()">&#9632;&nbsp;Stop</button>
          <button class="btn-ghost" onclick="runCancel()">Cancel</button>
        </div>
      </div>
      <div class="flex" style="margin:var(--s3) 0">
        <span class="pill accent" id="st_state">idle</span>
        <span class="muted mono" id="st_detail"></span>
      </div>
      <iframe id="liveView" title="Live experiment view"></iframe>
      <div id="liveHint" class="muted" style="margin-top:var(--s2);font-size:13px">
        Press <b>Go</b> to start &mdash; the live view appears here.</div>
    </div>
  </section>

  <!-- GRAPHS -->
  <section id="tab-graphs" class="hidden">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Graphs</h2><div class="sub">Result plots for a completed run.</div></div>
      <div class="flex">
        <select id="runPick" onchange="showRun()" style="min-width:240px" aria-label="Pick a run"></select>
        <button class="btn-danger" onclick="deleteRun('runPick')">Delete run</button>
        <button class="btn-primary" onclick="regenGraphs()">&#8635;&nbsp;Regenerate graphs</button>
      </div>
    </div>
    <div id="plots"></div>
  </section>

  <!-- VIDEOS -->
  <section id="tab-videos" class="hidden">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Videos</h2><div class="sub">Recorded trial videos for a completed run, per model.</div></div>
      <div class="flex">
        <select id="vidPick" onchange="showVideos()" style="min-width:240px" aria-label="Pick a run"></select>
        <button class="btn-danger" onclick="deleteRun('vidPick')">Delete run</button>
      </div>
    </div>
    <div id="videosList"></div>
  </section>
</main>
<div id="toasts" aria-live="polite"></div>

<script>
let META=null, CFG=null, GRID=[], SEL='water', painting=false;
const $=id=>document.getElementById(id);
const api=(u,m,b)=>fetch(u,{method:m||'GET',headers:{'Content-Type':'application/json'},
  body:b?JSON.stringify(b):undefined}).then(r=>r.json());
function toast(msg,kind){const t=document.createElement('div');t.className='toast'+(kind?' '+kind:'');
  t.textContent=msg;$('toasts').appendChild(t);setTimeout(()=>t.remove(),3200);}
function go(t){document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.dataset.tab==t));
  ['configs','editor','run','graphs','videos'].forEach(s=>$('tab-'+s).classList.toggle('hidden',s!=t));
  if(t=='configs')loadConfigs(); if(t=='graphs')loadRuns(); if(t=='videos')loadRuns(); if(t=='run')loadRunConfigs();}
document.querySelectorAll('.tab').forEach(x=>x.onclick=()=>go(x.dataset.tab));

function defaultConfig(){return {
  experiment:{name:'my_world',output_dir:'runs',num_trials:3,max_turns:60,seed:0,
    same_world_each_trial:true,record_video:true,video_fps:6,video_resolution:960},
  objective:{type:'achievement',target:'collect_wood',item:'wood',amount:1},
  world:{size:[10,10],base_terrain:'grass',player_start:[0,0],static:true,
    freeze_daylight:true,inventory:{},features:{},entities:{}},
  prompt:{include_legend:true,include_inventory:true,include_achievements:true,
    include_action_list:true,system:'You are playing Crafter. Reply with ONE action.',
    user:'GOAL: {objective}\n{map}\n{legend}\nPOSITION: {position} FACING: {facing}\n{inventory}\n{achievements}\n{actions}\nReply with one action.'},
  actions:{strategy:'keyword',fallback:'noop'},
  models:[{name:'gpt-4o-mini',backend:'openai',history_turns:8}]};}

// ---------- Configs list ----------
async function loadConfigs(){
  const el=$('cfgRows'); el.innerHTML='<div class="empty muted">Loading configs&hellip;</div>';
  const r=await api('/api/configs');
  if(!r.configs||!r.configs.length){el.innerHTML='<div class="empty"><b>No configs yet</b>Create one with + New config, then paint a world.</div>';return;}
  el.innerHTML=`<div class="cfg-head">
      <div>Name</div><div>Size</div><div>Objective</div><div>Trials</div><div>Turns</div>
      <div>Models</div><div>Actions</div>
    </div>`+r.configs.map(c=>`<div class="cfg">
    <div class="name">${c.name||'(unnamed)'}</div>
    <div class="cell">${c.size?c.size.join('\u00d7'):'\u2014'}</div>
    <div class="obj">${c.objective?`<span class="pill accent">${c.objective}</span>`:'\u2014'}</div>
    <div class="cell">${c.trials!=null?(c.trials_done??0)+'/'+c.trials:'\u2014'}</div>
    <div class="cell">${c.turns!=null?c.turns:'\u2014'}</div>
    <div class="models" title="${(c.models||[]).join(', ')}">${(c.models||[]).map(m=>`<span class="pill">${m}</span>`).join('')||'<span class="muted">\u2014</span>'}</div>
    <div class="actions">
      <button class="btn-secondary btn-sm" onclick='dupConfig(${JSON.stringify(c.path)})'>Duplicate</button>
      <button class="btn-secondary btn-sm" onclick='editConfig(${JSON.stringify(c.path)})'>Edit</button>
      <button class="btn-primary btn-sm" onclick='selectRun(${JSON.stringify(c.path)})'>&#9654; Run</button>
      <button class="btn-danger btn-sm" onclick='delConfigRow(${JSON.stringify(c.path)})'>Delete</button>
    </div></div>`).join('');
}
let EDPATH=null;
function newConfig(){CFG=defaultConfig();EDPATH=null;
  $('edPath').textContent='new';$('edDelete').classList.add('hidden');formFromCfg();go('editor');}
async function editConfig(path){const r=await api('/api/config?path='+encodeURIComponent(path));
  CFG=r.data;EDPATH=path;$('edPath').textContent=path;
  $('edDelete').classList.remove('hidden');formFromCfg();go('editor');}
async function dupConfig(path){const r=await api('/api/config/duplicate','POST',{path});
  if(r.ok){toast('Duplicated to '+r.path,'ok');await loadConfigs();editConfig(r.path);}else toast('Error: '+r.error,'err');}
async function deleteConfigPath(path){const r=await api('/api/config/delete','POST',{path});
  if(r.ok){toast(r.deleted_run_dir?'Deleted '+r.path+' and its run data':'Deleted '+r.path,'ok');return true;}
  toast('Error: '+r.error,'err');return false;}
const DELETE_WARNING='? This also permanently deletes that experiment\'s results, videos and graphs (its runs/ folder). This cannot be undone.';
async function delConfigRow(path){if(!confirm('Delete '+path+DELETE_WARNING))return;
  if(await deleteConfigPath(path))await loadConfigs();}
async function deleteCurrentConfig(){if(!EDPATH){toast('Nothing to delete — this config isn’t saved yet','err');return;}
  if(!confirm('Delete '+EDPATH+DELETE_WARNING))return;
  if(await deleteConfigPath(EDPATH))go('configs');}

// ---------- Editor form <-> CFG ----------
function formFromCfg(){const c=CFG;
  $('e_name').value=c.experiment.name; $('e_trials').value=c.experiment.num_trials;
  $('e_turns').value=c.experiment.max_turns; $('e_seed').value=c.experiment.seed??0;
  $('e_vres').value=c.experiment.video_resolution??960; $('e_vfps').value=c.experiment.video_fps??6;
  $('e_vid').value=String(c.experiment.record_video??true); $('e_same').value=String(c.experiment.same_world_each_trial??true);
  fillSelect($('o_target'),META.objectives,c.objective.target);
  $('o_type').value=c.objective.type||'achievement'; $('o_item').value=c.objective.item||'';
  $('o_amount').value=c.objective.amount??1;
  $('w_w').value=c.world.size[0]; $('w_h').value=c.world.size[1];
  $('w_static').value=String(c.world.static??true); $('w_day').value=String(c.world.freeze_daylight??true);
  $('p_leg').checked=c.prompt.include_legend; $('p_inv').checked=c.prompt.include_inventory;
  $('p_ach').checked=c.prompt.include_achievements; $('p_act').checked=c.prompt.include_action_list;
  $('p_sys').value=c.prompt.system||''; $('p_user').value=c.prompt.user||'';
  $('a_strat').value=c.actions.strategy||'keyword'; $('a_fall').value=c.actions.fallback||'noop';
  worldToGrid(); renderModels();
}
function fillSelect(sel,opts,val){sel.innerHTML=opts.map(o=>`<option ${o==val?'selected':''}>${o}</option>`).join('');}

function cfgFromForm(){const c=CFG;
  c.experiment.name=$('e_name').value; c.experiment.num_trials=+$('e_trials').value;
  c.experiment.max_turns=+$('e_turns').value; c.experiment.seed=+$('e_seed').value;
  c.experiment.video_resolution=+$('e_vres').value; c.experiment.video_fps=+$('e_vfps').value;
  c.experiment.record_video=$('e_vid').value=='true'; c.experiment.same_world_each_trial=$('e_same').value=='true';
  c.objective.type=$('o_type').value; c.objective.target=$('o_target').value;
  c.objective.item=$('o_item').value; c.objective.amount=+$('o_amount').value;
  c.world.static=$('w_static').value=='true'; c.world.freeze_daylight=$('w_day').value=='true';
  c.prompt.include_legend=$('p_leg').checked; c.prompt.include_inventory=$('p_inv').checked;
  c.prompt.include_achievements=$('p_ach').checked; c.prompt.include_action_list=$('p_act').checked;
  c.prompt.system=$('p_sys').value; c.prompt.user=$('p_user').value;
  c.actions.strategy=$('a_strat').value; c.actions.fallback=$('a_fall').value;
  gridToWorld(); modelsFromForm();
  return c;
}

// ---------- World builder grid ----------
function paletteInfo(id){return META.palette.find(p=>p.id==id);}
function renderPalette(){$('palette').innerHTML=META.palette.map(p=>
  `<span class="swatch ${p.id==SEL?'sel':''}" onclick="SEL='${p.id}';renderPalette()" tabindex="0"
     onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();SEL='${p.id}';renderPalette();}">
     <span class="dot" style="background:${p.color}"></span>${p.label}</span>`).join('');}
function W(){return +$('w_w').value;} function H(){return +$('w_h').value;}
function blankGrid(w,h){return Array.from({length:h},()=>Array.from({length:w},()=>'grass'));}
let CELLS=[];
function renderGrid(){const w=W(),h=H();const g=$('grid');
  g.style.gridTemplateColumns=`repeat(${w},22px)`;
  g.innerHTML=''; CELLS=[];
  for(let y=0;y<h;y++){const rowRefs=[];
    for(let x=0;x<w;x++){
      const d=document.createElement('div');d.className='cell';
      d.style.background=paletteInfo(GRID[y][x]).color;
      d.title=`${x},${y}`;
      const cx=x, cy=y;
      d.addEventListener('mousedown',e=>{e.preventDefault();painting=true;applyPaint(cx,cy);});
      d.addEventListener('mouseenter',()=>{if(painting)applyPaint(cx,cy);});
      g.appendChild(d); rowRefs.push(d);
    } CELLS.push(rowRefs);}
}
document.addEventListener('mouseup',()=>{painting=false;});
window.addEventListener('blur',()=>{painting=false;});
function setCell(x,y,id){GRID[y][x]=id;
  if(CELLS[y]&&CELLS[y][x])CELLS[y][x].style.background=paletteInfo(id).color;}
function applyPaint(x,y){const info=paletteInfo(SEL);
  if(info.kind=='player'){
    for(let j=0;j<GRID.length;j++)for(let i=0;i<GRID[0].length;i++)
      if(GRID[j][i]=='player')setCell(i,j,'grass');}
  setCell(x,y,SEL);}
function clearGrid(){GRID=blankGrid(W(),H());renderGrid();}
function resizeGrid(){const w=W(),h=H();const ng=blankGrid(w,h);
  for(let y=0;y<Math.min(h,GRID.length);y++)for(let x=0;x<Math.min(w,GRID[0]?.length||0);x++)ng[y][x]=GRID[y][x];
  GRID=ng;renderGrid();}
function worldToGrid(){const c=CFG.world;const w=c.size[0],h=c.size[1];GRID=blankGrid(w,h);
  const put=(key,coords)=>{(coords||[]).forEach(([x,y])=>{if(y<h&&x<w)GRID[y][x]=key;});};
  for(const p of META.palette){
    if(p.kind=='feature'){const f=(c.features||{})[p.key];if(f&&f.positions)put(p.id,f.positions);}
    if(p.kind=='entity'){const e=(c.entities||{})[p.key];if(e&&e.positions)put(p.id,e.positions);}
  }
  if(c.player_start){const [x,y]=c.player_start;if(y<h&&x<w)GRID[y][x]='player';}
  renderGrid();
}
function gridToWorld(){const c=CFG.world;c.size=[W(),H()];c.base_terrain='grass';
  const feats={},ents={};let player=null;
  for(let y=0;y<GRID.length;y++)for(let x=0;x<GRID[0].length;x++){
    const id=GRID[y][x];if(id=='grass')continue;const info=paletteInfo(id);
    if(info.kind=='player'){player=[x,y];}
    else if(info.kind=='feature'){(feats[info.key]=feats[info.key]||{positions:[]}).positions.push([x,y]);}
    else if(info.kind=='entity'){(ents[info.key]=ents[info.key]||{positions:[]}).positions.push([x,y]);}
  }
  c.features=feats;c.entities=ents;c.player_start=player||[0,0];
}
async function previewWorld(){gridToWorld();const r=await api('/api/preview','POST',{world:CFG.world});
  const o=$('previewOut');o.classList.remove('hidden');o.textContent=r.ok?r.map:('Error: '+r.error);
  if(!r.ok)toast('Preview error: '+r.error,'err');}

// ---------- Models ----------
function presetsFor(backend){return (META.model_presets&&META.model_presets[backend])||[];}
function modelOptions(m){
  const list=presetsFor(m.backend).slice();
  if(m.name&&!list.includes(m.name))list.unshift(m.name);
  const opts=list.map(p=>`<option ${p==m.name?'selected':''}>${p}</option>`).join('');
  return opts+`<option value="__custom__">(custom id...)</option>`;
}
function pickModel(i,v){
  if(v=='__custom__'){const c=prompt('Enter model id:',CFG.models[i].name||'');
    if(c)CFG.models[i].name=c; renderModels(); return;}
  CFG.models[i].name=v;
}
function renderModels(){$('models').innerHTML=(CFG.models||[]).map((m,i)=>`
  <div class="model">
    <div class="between" style="margin-bottom:var(--s2)">
      <b>${m.name||'model '+(i+1)}</b><button class="btn-danger btn-sm" onclick="delModel(${i})">Remove</button></div>
    <div class="row">
      <div><label>Backend</label><select onchange="CFG.models[${i}].backend=this.value;renderModels()">
        ${META.backends.map(b=>`<option ${b==m.backend?'selected':''}>${b}</option>`).join('')}</select></div>
      <div><label>Model</label><select onchange="pickModel(${i},this.value)">${modelOptions(m)}</select></div>
    </div>
    <div class="row">
      <div><label>max_tokens</label><input value="${m.max_tokens??''}" oninput="setOpt(${i},'max_tokens',this.value)"></div>
      <div><label>temperature</label><input value="${m.temperature??''}" oninput="setOpt(${i},'temperature',this.value)"></div>
      <div><label>history_turns</label><input value="${m.history_turns??''}" oninput="setOpt(${i},'history_turns',this.value)"></div>
      <div><label>reasoning_effort</label><input value="${m.reasoning_effort??''}" oninput="setOpt(${i},'reasoning_effort',this.value)"></div>
    </div>
    <div class="row">
      <div><label>force_action</label><select onchange="CFG.models[${i}].force_action=this.value=='true'">
        <option value="false" ${!m.force_action?'selected':''}>false</option>
        <option value="true" ${m.force_action?'selected':''}>true</option></select></div>
      <div><label>action_retries</label><input value="${m.action_retries??''}" oninput="setOpt(${i},'action_retries',this.value)"></div>
      <div><label>request_delay</label><input value="${m.request_delay??''}" oninput="setOpt(${i},'request_delay',this.value)"></div>
      <div></div>
    </div>
  </div>`).join('');}
function setOpt(i,k,v){if(v===''){delete CFG.models[i][k];return;}
  CFG.models[i][k]=isNaN(+v)||['reasoning_effort'].includes(k)?v:+v;}
function addModel(){CFG.models.push({name:presetsFor('openai')[0]||'gpt-4o-mini',backend:'openai',history_turns:8});renderModels();}
function delModel(i){CFG.models.splice(i,1);renderModels();}
function modelsFromForm(){}

// ---------- Save ----------
// The experiment name IS the file name - there's no separate save-path
// field - so validate it here for quick feedback; the server re-checks
// (and does the actual rename) since it alone knows what else exists.
const NAME_RE=/^[A-Za-z0-9_-]+$/;
async function saveConfig(){cfgFromForm();const name=(CFG.experiment.name||'').trim();
  if(!name){toast('Enter an experiment name','err');return;}
  if(!NAME_RE.test(name)){toast('Name can only contain letters, numbers, underscores and hyphens','err');return;}
  const r=await api('/api/config/save','POST',{old_path:EDPATH,data:CFG});
  if(r.ok){EDPATH=r.path;$('edPath').textContent=r.path;$('edDelete').classList.remove('hidden');toast('Saved '+r.path,'ok');}
  else toast('Error: '+r.error,'err');}

// ---------- Run ----------
let RUNPATH=null, poll=null;
async function loadRunConfigs(){const r=await api('/api/configs');
  const sel=$('runConfigPick');
  sel.innerHTML='<option value="">-- select a config --</option>'+
    (r.configs||[]).map(c=>`<option value="${c.path}" ${c.path==RUNPATH?'selected':''}>${c.name||c.path}</option>`).join('');
}
function pickRunConfig(path){RUNPATH=path||null;
  $('liveView').src='about:blank';$('liveHint').style.display='';}
function selectRun(path){RUNPATH=path;go('run');
  $('liveView').src='about:blank';$('liveHint').style.display='';}
async function runGo(){if(!RUNPATH){toast('Pick a config to run first','err');return;}
  const r=await api('/api/run/start','POST',{path:RUNPATH});
  if(!r.ok){toast(r.error,'err');return;}
  if(r.live_url){$('liveView').src=r.live_url;$('liveHint').style.display='none';}
  toast('Experiment started','ok');startPolling();}
function runPause(){api('/api/run/pause','POST');}
function runResume(){api('/api/run/resume','POST');}
function runStop(){api('/api/run/stop','POST');toast('Stopping\u2026');}
async function runRestart(){await api('/api/run/stop','POST');
  let tries=0;const wait=setInterval(async()=>{const s=await api('/api/run/status');
    if(!s.running||++tries>15){clearInterval(wait);runGo();}},600);}
async function runCancel(){await api('/api/run/stop','POST');
  if(poll)clearInterval(poll);$('liveView').src='about:blank';go('configs');}
function startPolling(){if(poll)clearInterval(poll);poll=setInterval(async()=>{
  const s=await api('/api/run/status');
  $('st_state').textContent=s.state||'idle';
  $('st_detail').textContent=s.model?`${s.model} \u00b7 trial ${s.trial}/${s.num_trials} \u00b7 turn ${s.turn}/${s.max_turns}`:(s.error||'');
  if(s.live_url&&$('liveView').src==='about:blank'){$('liveView').src=s.live_url;$('liveHint').style.display='none';}
  if(['finished','stopped','error'].includes(s.state)&&!s.running){clearInterval(poll);
    if(s.state=='finished'){toast('Run finished — generating graphs…','ok');
      if(s.run_name)analyzeAfterRun(s.run_name);}}
},700);}
async function analyzeAfterRun(name){
  const r=await api('/api/analyze','POST',{run:name});
  if(!r.ok){toast('Graph generation failed: '+r.error,'err');return;}
  toast('Graphs ready','ok');
  if($('tab-graphs')&&!$('tab-graphs').classList.contains('hidden')){
    await loadRuns(); $('runPick').value=name; showRun();
  }
}

// ---------- Graphs / Videos ----------
async function loadRuns(){const r=await api('/api/runs');
  const opts='<option value="">-- pick a run --</option>'+
    r.runs.map(x=>`<option value="${x.name}">${x.name}</option>`).join('');
  const prevRun=$('runPick').value, prevVid=$('vidPick').value;
  $('runPick').innerHTML=opts; $('vidPick').innerHTML=opts;
  $('runPick').value=prevRun; $('vidPick').value=prevVid;
  window._runs=r.runs;}
function showRun(){const name=$('runPick').value;const run=(window._runs||[]).find(r=>r.name==name);const bust=Date.now();
  if(!name){$('plots').innerHTML='<div class="empty"><b>No run selected</b>Pick a run above to see its plots.</div>';return;}
  if(!run||!run.plots.length){$('plots').innerHTML='<div class="empty"><b>No plots yet</b>Run this config, or press Regenerate graphs.</div>';return;}
  $('plots').innerHTML=run.plots.map(f=>`<div><div class="muted mono" style="font-size:12px;margin-bottom:4px">${f}</div>
    <img class="plot" alt="${f}" src="/api/plot?run=${encodeURIComponent(name)}&file=${encodeURIComponent(f)}&_=${bust}"></div>`).join('');}
async function regenGraphs(){const name=$('runPick').value;
  if(!name){toast('Pick a run first','err');return;}
  toast('Regenerating\u2026');const r=await api('/api/analyze','POST',{run:name});
  if(!r.ok){toast('Error: '+r.error,'err');return;}
  await loadRuns(); $('runPick').value=name; showRun(); toast('Graphs regenerated','ok');}
function showVideos(){const name=$('vidPick').value;const run=(window._runs||[]).find(r=>r.name==name);
  if(!name){$('videosList').innerHTML='<div class="empty"><b>No run selected</b>Pick a run above to see its videos.</div>';return;}
  if(!run||!run.videos.length){$('videosList').innerHTML='<div class="empty"><b>No videos yet</b>Run this config with record_video enabled.</div>';return;}
  $('videosList').innerHTML=run.videos.map(f=>`<div><div class="muted mono" style="font-size:12px;margin-bottom:4px">${f}</div>
    <video class="plot" controls preload="metadata" src="/api/video?run=${encodeURIComponent(name)}&file=${encodeURIComponent(f)}"></video></div>`).join('');}
// Deletes a run's whole folder (results/plots/videos) directly - covers runs
// left behind by configs deleted before that cascade existed, or whose
// config was removed outside the Studio, since those otherwise have no
// config row to delete from.
async function deleteRun(selectId){const name=$(selectId).value;
  if(!name){toast('Pick a run first','err');return;}
  if(!confirm('Delete run \''+name+'\'? This permanently deletes its results, plots and videos. This cannot be undone.'))return;
  const r=await api('/api/run/delete','POST',{run:name});
  if(!r.ok){toast('Error: '+r.error,'err');return;}
  toast('Deleted run '+name,'ok');
  await loadRuns(); showRun(); showVideos();}

// ---------- boot ----------
(async()=>{META=await api('/api/meta');renderPalette();loadConfigs();})();
</script>
</body></html>
"""