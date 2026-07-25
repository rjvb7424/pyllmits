"""studio_ui.py - the single-page app served by studio.py (HTML/CSS/JS)."""

INDEX_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>Crafter Studio</title>
<style>
  :root { --bg:#14161c; --panel:#1c1f28; --panel2:#232732; --line:#333947;
          --fg:#e6e8ef; --muted:#9aa3b2; --accent:#4c7ef0; --ok:#2f9e6f; --bad:#c44e52; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }
  header { display:flex; align-items:center; gap:6px; padding:10px 16px;
           background:var(--panel); border-bottom:1px solid var(--line); }
  header b { font-size:16px; margin-right:16px; }
  .tab { padding:6px 14px; border-radius:8px; cursor:pointer; color:var(--muted); }
  .tab.active { background:var(--accent); color:#fff; }
  main { padding:16px; max-width:1100px; margin:0 auto; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:12px;
          padding:16px; margin-bottom:16px; }
  h3 { margin:0 0 12px; }
  label { display:block; color:var(--muted); font-size:12px; margin:8px 0 2px; }
  input,select,textarea { width:100%; background:var(--panel2); color:var(--fg);
      border:1px solid var(--line); border-radius:8px; padding:7px 9px; font:inherit; }
  textarea { min-height:120px; font-family:ui-monospace,Menlo,monospace; font-size:12px; }
  .row { display:flex; gap:12px; flex-wrap:wrap; }
  .row > div { flex:1; min-width:120px; }
  button { background:var(--accent); color:#fff; border:0; border-radius:8px;
           padding:8px 14px; cursor:pointer; font:inherit; }
  button.ghost { background:var(--panel2); border:1px solid var(--line); color:var(--fg); }
  button.bad { background:var(--bad); } button.ok { background:var(--ok); }
  table { width:100%; border-collapse:collapse; }
  th,td { text-align:left; padding:8px; border-bottom:1px solid var(--line); font-size:13px; }
  .pill { display:inline-block; background:var(--panel2); border:1px solid var(--line);
          border-radius:20px; padding:1px 8px; font-size:11px; color:var(--muted); }
  .hidden { display:none; }
  .grid-wrap { overflow:auto; border:1px solid var(--line); border-radius:8px; background:#0e1014; padding:8px; }
  #grid { display:grid; gap:1px; }
  .cell { width:20px; height:20px; border-radius:3px; cursor:pointer; }
  .swatch { display:inline-flex; align-items:center; gap:6px; padding:5px 9px; margin:2px;
            border:1px solid var(--line); border-radius:8px; cursor:pointer; background:var(--panel2); }
  .swatch.sel { outline:2px solid var(--accent); }
  .dot { width:14px; height:14px; border-radius:3px; display:inline-block; }
  pre { background:#0e1014; border:1px solid var(--line); border-radius:8px; padding:10px;
        overflow:auto; font-size:12px; line-height:1.15; }
  .muted { color:var(--muted); } .flex { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  img.plot { max-width:100%; border:1px solid var(--line); border-radius:8px; margin:6px 0; background:#fff; }
</style>
</head>
<body>
<header>
  <b>Crafter Studio</b>
  <div class="tab active" data-tab="configs">Configs</div>
  <div class="tab" data-tab="run">Run</div>
  <div class="tab" data-tab="graphs">Graphs</div>
</header>
<main>
  <!-- CONFIGS -->
  <section id="tab-configs">
    <div class="card">
      <div class="flex" style="justify-content:space-between">
        <h3>Config files</h3>
        <button onclick="newConfig()">+ New config</button>
      </div>
      <table><thead><tr><th>Name</th><th>Trials</th><th>Turns</th><th>Size</th>
        <th>Objective</th><th>Models</th><th></th></tr></thead>
        <tbody id="cfgRows"></tbody></table>
    </div>
  </section>

  <!-- EDITOR -->
  <section id="tab-editor" class="hidden">
    <div class="card">
      <div class="flex" style="justify-content:space-between">
        <h3>Editor <span class="pill" id="edPath">unsaved</span></h3>
        <div class="flex">
          <input id="savePath" style="width:320px" placeholder="configs/my_world.yaml"/>
          <button class="ok" onclick="saveConfig()">Save</button>
          <button class="ghost" onclick="go('run')">Go to Run &rarr;</button>
        </div>
      </div>
    </div>

    <div class="card"><h3>Experiment</h3>
      <div class="row">
        <div><label>Name</label><input id="e_name"></div>
        <div><label>Trials</label><input id="e_trials" type="number"></div>
        <div><label>Max turns</label><input id="e_turns" type="number"></div>
        <div><label>Seed</label><input id="e_seed" type="number"></div>
      </div>
      <div class="row">
        <div><label>Video resolution</label><input id="e_vres" type="number"></div>
        <div><label>Video fps</label><input id="e_vfps" type="number"></div>
        <div><label>Record video</label><select id="e_vid"><option value="true">yes</option><option value="false">no</option></select></div>
        <div><label>Same world each trial</label><select id="e_same"><option value="true">yes</option><option value="false">no</option></select></div>
      </div>
    </div>

    <div class="card"><h3>Objective</h3>
      <div class="row">
        <div><label>Type</label><select id="o_type"><option>achievement</option><option>inventory</option></select></div>
        <div><label>Target</label><select id="o_target"></select></div>
        <div><label>Item</label><input id="o_item"></div>
        <div><label>Amount</label><input id="o_amount" type="number"></div>
      </div>
    </div>

    <div class="card"><h3>World builder</h3>
      <div class="row">
        <div><label>Width</label><input id="w_w" type="number" onchange="resizeGrid()"></div>
        <div><label>Height</label><input id="w_h" type="number" onchange="resizeGrid()"></div>
        <div><label>Static</label><select id="w_static"><option value="true">yes</option><option value="false">no</option></select></div>
        <div><label>Freeze daylight</label><select id="w_day"><option value="true">yes</option><option value="false">no</option></select></div>
      </div>
      <label>Palette (click a tile, then paint on the grid; drag to paint many)</label>
      <div id="palette"></div>
      <div class="grid-wrap"><div id="grid"></div></div>
      <div class="flex" style="margin-top:10px">
        <button class="ghost" onclick="clearGrid()">Clear</button>
        <button class="ghost" onclick="previewWorld()">Preview (engine)</button>
        <span class="muted">Tip: exactly one Player tile = the start position.</span>
      </div>
      <pre id="previewOut" class="hidden"></pre>
    </div>

    <div class="card"><h3>Models</h3>
      <div id="models"></div>
      <button class="ghost" onclick="addModel()">+ Add model</button>
    </div>

    <div class="card"><h3>Prompt</h3>
      <div class="flex">
        <label class="flex"><input type="checkbox" id="p_leg" style="width:auto"> legend</label>
        <label class="flex"><input type="checkbox" id="p_inv" style="width:auto"> inventory</label>
        <label class="flex"><input type="checkbox" id="p_ach" style="width:auto"> achievements</label>
        <label class="flex"><input type="checkbox" id="p_act" style="width:auto"> action list</label>
      </div>
      <label>System</label><textarea id="p_sys"></textarea>
      <label>User</label><textarea id="p_user"></textarea>
      <label>Action parse strategy / fallback</label>
      <div class="row"><div><input id="a_strat"></div><div><input id="a_fall"></div></div>
    </div>
  </section>

  <!-- RUN -->
  <section id="tab-run" class="hidden">
    <div class="card">
      <h3>Run experiment</h3>
      <div class="flex">
        <span>Config: <b id="runPath">none selected</b></span>
        <button class="ok" onclick="runStart()">&#9654; Start</button>
        <button class="ghost" onclick="runPause()">&#10073;&#10073; Pause</button>
        <button class="ghost" onclick="runResume()">&#9654; Resume</button>
        <button class="bad" onclick="runStop()">&#9632; Stop</button>
      </div>
      <div class="flex" style="margin-top:10px">
        <span class="pill" id="st_state">idle</span>
        <span class="muted" id="st_detail"></span>
      </div>
      <img id="liveFrame" class="plot" style="max-width:420px; image-rendering:pixelated" />
    </div>
  </section>

  <!-- GRAPHS -->
  <section id="tab-graphs" class="hidden">
    <div class="card">
      <h3>Result graphs</h3>
      <select id="runPick" onchange="showRun()" style="max-width:360px"></select>
      <div id="plots"></div>
    </div>
  </section>
</main>

<script>
let META=null, CFG=null, GRID=[], SEL='water', painting=false;
const $=id=>document.getElementById(id);
const api=(u,m,b)=>fetch(u,{method:m||'GET',headers:{'Content-Type':'application/json'},
  body:b?JSON.stringify(b):undefined}).then(r=>r.json());

function go(t){document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.dataset.tab==t));
  ['configs','editor','run','graphs'].forEach(s=>$('tab-'+s).classList.toggle('hidden',s!=t));
  if(t=='configs')loadConfigs(); if(t=='graphs')loadRuns();}
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
  const r=await api('/api/configs');
  $('cfgRows').innerHTML = r.configs.map(c=>`<tr>
    <td>${c.name||''}</td><td>${c.trials??''}</td><td>${c.turns??''}</td>
    <td>${c.size?c.size.join('x'):''}</td><td>${c.objective||''}</td>
    <td>${(c.models||[]).map(m=>'<span class=pill>'+m+'</span>').join(' ')}</td>
    <td class="flex"><button class="ghost" onclick='editConfig(${JSON.stringify(c.path)})'>Edit</button>
      <button onclick='selectRun(${JSON.stringify(c.path)})'>Run</button></td></tr>`).join('');
}
function newConfig(){CFG=defaultConfig();$('savePath').value='configs/'+CFG.experiment.name+'.yaml';
  $('edPath').textContent='new';formFromCfg();go('editor');}
async function editConfig(path){const r=await api('/api/config?path='+encodeURIComponent(path));
  CFG=r.data;$('savePath').value=path;$('edPath').textContent=path;formFromCfg();go('editor');}

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
  `<span class="swatch ${p.id==SEL?'sel':''}" onclick="SEL='${p.id}';renderPalette()">
     <span class="dot" style="background:${p.color}"></span>${p.label}</span>`).join('');}
function W(){return +$('w_w').value;} function H(){return +$('w_h').value;}
function blankGrid(w,h){return Array.from({length:h},()=>Array.from({length:w},()=>'grass'));}
let CELLS=[];
function renderGrid(){const w=W(),h=H();const g=$('grid');
  g.style.gridTemplateColumns=`repeat(${w},20px)`;
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
// mouseup/leave anywhere ends a paint stroke - so a single click never sticks.
document.addEventListener('mouseup',()=>{painting=false;});
window.addEventListener('blur',()=>{painting=false;});
function setCell(x,y,id){GRID[y][x]=id;
  if(CELLS[y]&&CELLS[y][x])CELLS[y][x].style.background=paletteInfo(id).color;}
function applyPaint(x,y){const info=paletteInfo(SEL);
  if(info.kind=='player'){ // player is unique - clear any existing one
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
  const o=$('previewOut');o.classList.remove('hidden');o.textContent=r.ok?r.map:('Error: '+r.error);}

// ---------- Models ----------
function presetsFor(backend){return (META.model_presets&&META.model_presets[backend])||[];}
function modelOptions(m){
  const list=presetsFor(m.backend).slice();
  if(m.name&&!list.includes(m.name))list.unshift(m.name); // keep loaded custom id
  const opts=list.map(p=>`<option ${p==m.name?'selected':''}>${p}</option>`).join('');
  return opts+`<option value="__custom__">(custom id...)</option>`;
}
function pickModel(i,v){
  if(v=='__custom__'){const c=prompt('Enter model id:',CFG.models[i].name||'');
    if(c)CFG.models[i].name=c; renderModels(); return;}
  CFG.models[i].name=v;
}
function renderModels(){$('models').innerHTML=(CFG.models||[]).map((m,i)=>`
  <div class="card" style="background:var(--panel2)">
    <div class="flex" style="justify-content:space-between">
      <b>${m.name||'model '+(i+1)}</b><button class="bad ghost" onclick="delModel(${i})">remove</button></div>
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
function modelsFromForm(){/* models edited live via oninput */}

// ---------- Save ----------
async function saveConfig(){cfgFromForm();const path=$('savePath').value.trim();
  if(!path){alert('Enter a save path');return;}
  const r=await api('/api/config/save','POST',{path,data:CFG});
  if(r.ok){$('edPath').textContent=r.path;alert('Saved '+r.path);}else alert('Error: '+r.error);}

// ---------- Run ----------
let RUNPATH=null, poll=null;
function selectRun(path){RUNPATH=path;$('runPath').textContent=path;go('run');}
async function runStart(){if(!RUNPATH){alert('Pick a config on the Configs tab first');return;}
  const r=await api('/api/run/start','POST',{path:RUNPATH});
  if(!r.ok){alert(r.error);return;} startPolling();}
function runPause(){api('/api/run/pause','POST');}
function runResume(){api('/api/run/resume','POST');}
function runStop(){api('/api/run/stop','POST');}
function startPolling(){if(poll)clearInterval(poll);poll=setInterval(async()=>{
  const s=await api('/api/run/status');
  $('st_state').textContent=s.state||'idle';
  $('st_detail').textContent=s.model?`${s.model} - trial ${s.trial}/${s.num_trials}, turn ${s.turn}/${s.max_turns}`:(s.error||'');
  $('liveFrame').src='/api/run/frame.png?'+Date.now();
  if(['finished','stopped','error','idle'].includes(s.state)&&!s.running){/* keep last frame */}
},700);}

// ---------- Graphs ----------
async function loadRuns(){const r=await api('/api/runs');
  $('runPick').innerHTML='<option value="">-- pick a run --</option>'+
    r.runs.map(x=>`<option value="${x.name}">${x.name}</option>`).join('');
  window._runs=r.runs;}
function showRun(){const name=$('runPick').value;const run=(window._runs||[]).find(r=>r.name==name);
  $('plots').innerHTML=run?run.plots.map(f=>`<div><div class="muted">${f}</div>
    <img class="plot" src="/api/plot?run=${encodeURIComponent(name)}&file=${encodeURIComponent(f)}"></div>`).join(''):'';}

// ---------- boot ----------
(async()=>{META=await api('/api/meta');renderPalette();loadConfigs();})();
</script>
</body></html>
"""
