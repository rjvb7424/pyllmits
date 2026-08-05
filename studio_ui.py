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
<title>Pyllmits</title>
<link rel="icon" type="image/png" href="/api/logo.png"/>
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
    /* config table columns: Name | Size | Objective | Status | Trials | Turns | Models | Actions */
    --cfg-cols:minmax(130px,1fr) 70px 120px 96px 60px 60px minmax(220px,1.4fr) 300px;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 var(--ui);-webkit-font-smoothing:antialiased;
    display:flex;flex-direction:column;overflow:hidden}
  h1,h2,h3{margin:0;line-height:1.2;font-weight:600;letter-spacing:-.01em}
  h2{font-size:22px} h3{font-size:18px}
  a{color:var(--accent)}
  .mono{font-family:var(--mono)}
  .muted{color:var(--muted)} .faint{color:var(--faint)}
  .flex{display:flex;gap:var(--s3);align-items:center;flex-wrap:wrap}
  .between{display:flex;gap:var(--s3);align-items:center;justify-content:space-between;flex-wrap:wrap}
  .hidden{display:none!important}
  ::selection{background:var(--accent);color:var(--on-accent)}

  /* Welcome screen - shown before the app shell (#app); both are direct flex
     children of body so whichever isn't .hidden fills the viewport, same
     pattern the header/main/terminal stack already uses. */
  #welcome{flex:1;min-height:0;overflow-y:auto}
  #app{display:flex;flex-direction:column;flex:1;min-height:0}
  /* Top app bar - sticky (the one bar on this screen that should stay put;
     unlike the bottom footer, a top bar being pinned while content scrolls
     beneath it is the idiomatic, expected pattern). Brand on the left reuses
     the app shell's own .brand/.mark so the two screens read as one product;
     social/reference links on the right as icon buttons. */
  .welcome-appbar{position:sticky;top:0;z-index:5;flex-shrink:0;display:flex;align-items:center;
    justify-content:space-between;padding:var(--s3) var(--s6);background:var(--surface);
    border-bottom:1px solid var(--line)}
  .welcome-appbar-links{display:flex;align-items:center;gap:var(--s1)}
  .appbar-icon-btn{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;
    border-radius:var(--radius);color:var(--muted);transition:background .12s,color .12s}
  .appbar-icon-btn:hover{background:var(--raised);color:var(--text)}
  .appbar-icon-btn svg{width:18px;height:18px;display:block}
  .welcome-inner{max-width:720px;margin:0 auto;padding:var(--s8) var(--s6)}
  .welcome-brand{margin-bottom:var(--s3);display:flex;align-items:center;gap:var(--s3)}
  .welcome-brand-logo{width:40px;height:40px;border-radius:8px;object-fit:cover;flex-shrink:0;
    box-shadow:inset 0 0 0 1px rgba(255,255,255,.15)}
  .welcome-brand h1{font-size:32px;color:var(--accent)}
  .welcome-tagline{color:var(--text);font-size:15px;margin:0 0 var(--s6)}
  /* Demo clip - a locked-down preview, not a player: no controls, no focus
     ring, no pointer events (so a click can't fullscreen/pause it), no
     context menu (see oncontextmenu on the <video> itself). object-fit:contain
     shows the whole frame (nothing cropped out of the source); any leftover
     space on the sides is just the card's own background, not black bars. */
  .welcome-demo{margin-bottom:var(--s6);border:1px solid var(--line);border-radius:var(--radius-lg);
    overflow:hidden;background:var(--surface)}
  .welcome-demo video{display:block;width:100%;max-height:420px;object-fit:contain;object-position:center;
    background:var(--raised);pointer-events:none;outline:none}
  .welcome-demo-caption{padding:var(--s2) var(--s4);font:12px var(--mono);color:var(--muted);
    background:var(--surface);border-top:1px solid var(--line)}
  /* Footer - a real footer: the last thing on the page, scrolling up with
     everything above it (not pinned/sticky - that read as an app bar). Full
     viewport width for visual weight, its content column matching the rest
     of the page. */
  .welcome-footer{border-top:1px solid var(--line);background:var(--surface);margin-top:var(--s4)}
  .welcome-footer-inner{max-width:720px;margin:0 auto;padding:var(--s6);
    display:flex;align-items:center;justify-content:space-between;gap:var(--s4);flex-wrap:wrap}
  .welcome-footer-cta{font-weight:600;font-size:15px;color:var(--text)}
  .welcome-footer-sub{color:var(--muted);font-size:13px;margin-top:2px}
  .welcome-desc{color:var(--text);line-height:1.65;margin-bottom:var(--s6)}
  .welcome-desc code{font-family:var(--mono);font-size:.92em;background:var(--raised);
    border:1px solid var(--line);border-radius:4px;padding:1px 5px}
  .python-logo{display:inline-flex;vertical-align:-5px;margin-right:var(--s2)}
  .python-logo svg{width:20px;height:20px;display:block}
  .python-logo.mono{color:var(--text)}
  .pypi-row{display:flex;align-items:center;gap:var(--s3);flex-wrap:wrap}
  .pypi-row pre{margin:0;flex-shrink:0}
  .env-field{margin-bottom:var(--s4)}
  .env-field:last-child{margin-bottom:0}
  .env-field .env-label-row{display:flex;justify-content:space-between;align-items:baseline;gap:var(--s3)}
  .env-field label{margin-top:0}
  .env-field .env-hint{font-family:var(--mono);font-size:12px;color:var(--faint);white-space:nowrap}
  .env-field .env-hint.set{color:var(--ok)}
  .env-field .env-hint.unset{color:var(--danger)}
  .env-field .flex{align-items:stretch}
  .env-field input{flex:1;min-width:180px}
  .provider-row{display:flex;align-items:center;justify-content:space-between;gap:var(--s3);
    padding:var(--s3) 0;border-top:1px solid var(--line)}
  .provider-row:first-child{border-top:0;padding-top:0}
  .provider-row:last-child{padding-bottom:0}
  @media (max-width:600px){.welcome-inner{padding:var(--s8) var(--s4)}.welcome-brand h1{font-size:26px}
    .welcome-brand-logo{width:32px;height:32px}}

  header{flex-shrink:0;z-index:20;display:flex;align-items:center;flex-wrap:wrap;gap:var(--s4);
    padding:var(--s3) var(--s6);background:var(--surface);border-bottom:1px solid var(--line)}
  /* Header status - an interactive dot plus its state/detail text, so the
     run's status reads at a glance from anywhere in the app without needing
     to hover (title attr still holds the full text as a tooltip backup;
     click jumps to Run). */
  #hdrStatus{flex-shrink:0;appearance:none;border:1px solid var(--line);background:var(--raised);
    padding:5px 12px;border-radius:999px;cursor:pointer;display:flex;align-items:center;gap:8px}
  #hdrStatus:hover{border-color:var(--line2);background:#242a34}
  #hdrStatus .status-label{font:600 12px var(--mono);color:var(--text);text-transform:capitalize;white-space:nowrap}
  #hdrStatus .status-detail{font:12px var(--mono);color:var(--muted);white-space:nowrap}
  .status-dot{width:9px;height:9px;border-radius:50%;display:block;flex-shrink:0;background:var(--faint)}
  .status-dot.running{background:var(--ok);animation:statusPulse 1.4s infinite;--pulse-rgb:63,178,127}
  .status-dot.paused{background:var(--accent)}
  .status-dot.finished{background:var(--ok)}
  .status-dot.stopped{background:var(--danger);animation:statusPulse 1.4s infinite;--pulse-rgb:224,86,86}
  .status-dot.cancelled{background:var(--danger)}
  .status-dot.error{background:var(--danger);animation:statusPulse 1.4s infinite;--pulse-rgb:224,86,86}
  @keyframes statusPulse{
    0%{box-shadow:0 0 0 0 rgba(var(--pulse-rgb),.55)}
    70%{box-shadow:0 0 0 8px rgba(var(--pulse-rgb),0)}
    100%{box-shadow:0 0 0 0 rgba(var(--pulse-rgb),0)}
  }
  .brand{display:flex;align-items:center;gap:var(--s2);font-weight:700;font-size:16px;letter-spacing:-.02em}
  .brand-link{cursor:pointer;border-radius:var(--radius);padding:var(--s1) var(--s2);margin:calc(var(--s1) * -1) calc(var(--s2) * -1)}
  .brand-link:hover{background:var(--raised)}
  .brand-link:focus-visible{outline:none;box-shadow:0 0 0 3px rgba(232,134,60,.25)}
  .brand .mark{width:20px;height:20px;border-radius:5px;object-fit:cover;display:block;
    box-shadow:inset 0 0 0 1px rgba(255,255,255,.15)}
  nav{display:flex;gap:var(--s1);margin-left:var(--s2)}
  .tab{appearance:none;border:0;background:transparent;color:var(--muted);cursor:pointer;
    font:500 14px var(--ui);padding:var(--s2) var(--s3);border-radius:var(--radius);min-height:36px}
  .tab:hover{color:var(--text);background:var(--raised)}
  .tab.active{color:var(--on-accent);background:var(--accent)}
  .tab.active:hover{background:var(--accent-press)}

  main{flex:1;overflow-y:auto;padding:var(--s6);max-width:1500px;margin:0 auto;width:100%}

  /* Terminal - pinned to the bottom of every tab, like the header at the
     top. Mirrors the real process's stdout/stderr + logging 1:1 (see
     studio.py's ConsoleLog / _install_console_capture), not a separate
     "activity log" - so it looks and behaves like an actual terminal. */
  #terminal{flex-shrink:0;z-index:20;display:flex;flex-direction:column;height:240px;
    background:#0c0c0c;border-top:1px solid var(--line)}
  #terminal.collapsed{height:auto!important}
  #terminal.collapsed #termOut,#terminal.collapsed #termResize{display:none}
  #termResize{height:5px;flex-shrink:0;cursor:row-resize}
  #termResize:hover,#termResize.active{background:var(--accent)}
  .term-bar{display:flex;align-items:center;justify-content:space-between;gap:var(--s3);
    padding:3px var(--s4);background:#161616;border-bottom:1px solid #2a2a2a;flex-shrink:0}
  .term-bar .term-title{display:flex;align-items:center;gap:8px;color:#cfd3d8;
    font:600 10.5px var(--ui);text-transform:uppercase;letter-spacing:.06em}
  #termOut{flex:1;overflow-y:auto;margin:0;padding:var(--s2) var(--s4);
    font-family:var(--mono);font-size:12.5px;line-height:1.55;color:#d4d4d4;
    white-space:pre-wrap;word-break:break-word}
  #termOut .line.stderr{color:#f27272}
  #termOut .line.log{color:#8fb8e0}
  #termOut .empty{color:#5a5f66;font-style:italic}
  @media (max-width:768px){#terminal{height:180px}}

  .card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius-lg);
    padding:var(--s6);margin-bottom:var(--s4)}
  .card h3{margin-bottom:var(--s4)}
  .sub{color:var(--muted);font-size:13px;margin-top:6px}
  /* A pill's own vertical padding makes its line taller than plain .sub text
     (26px vs ~19.5px) - tighten it here so every tab's header is the same
     height whether its .sub line holds text or a pill. */
  .sub .pill{padding-top:0;padding-bottom:0}

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

  /* Buttons and button-styled links (an <a class="btn-*"> - e.g. an external
     link that should look identical to a same-tier <button>) share this base:
     element selector alone won't reach an <a>, so it's listed explicitly. */
  button,a.btn-primary,a.btn-secondary,a.btn-ghost,a.btn-danger{
    font:600 14px var(--ui);border-radius:var(--radius);cursor:pointer;min-height:40px;
    padding:0 var(--s4);border:1px solid transparent;display:inline-flex;align-items:center;
    justify-content:center;gap:var(--s2);transition:background .12s,border-color .12s,transform .04s;
    text-decoration:none}
  button:active,a.btn-primary:active,a.btn-secondary:active,a.btn-ghost:active,a.btn-danger:active{transform:translateY(1px)}
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
  .pill.ok{color:var(--ok);border-color:rgba(63,178,127,.35)}
  .pill.danger{color:var(--danger);border-color:rgba(224,86,86,.35)}

  /* exec-style table: header + rows share the same fixed column tracks */
  .cfg-table{display:flex;flex-direction:column;gap:var(--s2);overflow-x:auto}
  .cfg-head,.cfg{display:grid;grid-template-columns:var(--cfg-cols);gap:var(--s3);
    padding:var(--s3) var(--s4);border:1px solid transparent}
  .cfg-head>*,.cfg>*{min-width:0}                    /* keep columns from bleeding */
  .cfg-head{color:var(--muted);font-size:11.5px;font-weight:600;text-transform:uppercase;
    letter-spacing:.05em;padding-top:0;padding-bottom:var(--s1);align-items:center}
  .cfg{background:var(--surface);border-color:var(--line);border-radius:var(--radius-lg);
    min-height:92px;align-items:center}                /* ~3 lines tall, content vertically centered */
  .cfg:hover{border-color:var(--line2)}
  .cfg .name{font-weight:600;font-size:15px;overflow:hidden;text-overflow:ellipsis;
    display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}
  /* Objective and Status are both "a pill in a field" - .obj is just .field
     plus overflow handling for long text, so their pills always share the
     same box model and sit on the same baseline instead of drifting.
     (Named .field, not .cell, to avoid colliding with the World Builder's
     unrelated #grid .cell tile class - that collision was silently forcing
     these down to a 22px tile size.) */
  .cfg .field{color:var(--text);font-family:var(--mono);font-size:13px;display:flex;align-items:center}
  .cfg .obj .pill{max-width:100%;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  /* Short model lists (fit without scrolling) center vertically like every
     other pill column; once there are enough models to need scrolling,
     .scroll (added in JS, after measuring) pins content to the top instead
     so scrolling down always reveals more rather than jumping around. */
  .cfg .models{display:flex;gap:6px;flex-wrap:wrap;align-content:center;align-self:center;
    overflow-y:auto;max-height:72px;                  /* ~3 rows visible; scroll for the rest */
    padding-right:4px;scrollbar-width:thin;scrollbar-color:var(--line2) transparent}
  .cfg .models.scroll{align-content:flex-start;align-self:start}
  .cfg .models::-webkit-scrollbar{width:6px}
  .cfg .models::-webkit-scrollbar-thumb{background:var(--line2);border-radius:3px}
  .cfg .actions{display:flex;gap:var(--s2);justify-content:flex-start;align-items:center;flex-wrap:wrap}

  .empty{text-align:center;color:var(--muted);padding:var(--s12) var(--s4);border:1px dashed var(--line2);border-radius:var(--radius-lg)}
  .empty b{color:var(--text);display:block;margin-bottom:var(--s2);font-size:16px}

  .grid-wrap{overflow:auto;border:1px solid var(--line);border-radius:var(--radius);background:#0b0d11;padding:var(--s3);
    max-height:70vh;display:flex;justify-content:center}
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

  /* Run tab live view - always rendered (with placeholder values) rather than
     only appearing once a run starts, so the tab shows the real layout, not
     an empty state that implies a page is loading. */
  .live-grid{display:grid;grid-template-columns:minmax(280px,420px) 1fr;gap:var(--s4)}
  .live-frame{background:#0b0d11;border:1px solid var(--line);border-radius:var(--radius);
    min-height:280px;display:flex;align-items:center;justify-content:center;padding:var(--s3);margin-bottom:var(--s3)}
  .live-frame img{image-rendering:pixelated;width:100%;max-width:380px;border-radius:4px;display:block}
  .live-chips{display:flex;gap:var(--s3);flex-wrap:wrap;margin-bottom:var(--s3)}
  .chip{background:var(--raised);border:1px solid var(--line);border-radius:var(--radius);
    padding:var(--s2) var(--s3);flex:1;min-width:92px}
  .chip .k{color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.08em}
  .chip .v{font-family:var(--mono);font-size:15px;margin-top:3px;color:var(--text)}
  .chip .v.accent{color:var(--accent)}
  .chip .v.bad{color:var(--danger)}
  #lvState,#lvResponse,#lvPrompt,#pfRawResponse,#pfRawPrompt{white-space:pre-wrap;word-break:break-word;max-height:40vh}
  @media (max-width:900px){.live-grid{grid-template-columns:1fr}}

  .plot{max-width:100%;border:1px solid var(--line);border-radius:var(--radius);margin:var(--s2) auto;background:#fff;display:block}
  #plots{display:flex;flex-direction:column;align-items:center}
  #plots>div{margin-bottom:var(--s4);text-align:center}
  #plots>.empty{align-self:stretch}
  button:disabled{opacity:.45;cursor:not-allowed}

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
    .cfg .models{max-height:none;overflow-y:visible;flex-wrap:wrap}
    .cfg .name{-webkit-line-clamp:2}
    .cfg .actions{justify-content:flex-start}
    .cfg .actions .btn-primary{flex:1}
  }
  @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>

<!-- WELCOME - the landing page shown before the app shell. Branding, what
     Pyllmits is, the PyPI package, and where to drop API keys (written
     straight to a local .env - see /api/env/save in studio.py). -->
<div id="welcome">
  <div class="welcome-appbar">
    <div class="brand"><img class="mark" src="/api/logo.png" alt=""/><span>Pyllmits</span></div>
    <div class="welcome-appbar-links">
      <a class="appbar-icon-btn" href="https://github.com/rjvb7424/pyllmits" target="_blank" rel="noopener noreferrer" aria-label="GitHub repository" title="GitHub">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>
      </a>
      <a class="appbar-icon-btn" href="https://pypi.org/project/pyllmits/" target="_blank" rel="noopener noreferrer" aria-label="PyPI package" title="PyPI">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor"><path d="M23.922 13.58v3.912L20.55 18.72l-.078.055.052.037 3.45-1.256.026-.036v-3.997l-.053-.036-.025.092z M23.621 5.618l-3.04 1.107v3.912l3.339-1.215V5.509zM23.92 13.457V9.544l-3.336 1.215v3.913zM20.47 14.71V10.8L17.17 12v3.913zM17.034 19.996v-3.912l-3.313 1.206v3.912zM17.17 16.057v3.868l3.314-1.206V14.85l-3.314 1.206zm2.093 1.882c-.367.134-.663-.074-.663-.463s.296-.814.663-.947c.365-.133.662.075.662.464s-.297.814-.662.946z M13.225 9.315l.365-.132-3.285-1.197-3.323 1.21.102.037 3.184 1.16zM20.507 10.664V6.751L17.17 7.965v3.913zM17.058 11.918V8.005l-3.302 1.202v3.912zM13.643 9.246l-3.336 1.215v3.913l3.336-1.215zM6.907 13.165l3.322 1.209v-3.913L6.907 9.252z M10.34 7.873l3.281 1.193V5.198l-3.28-1.193zM20.507 2.715L17.19 3.922v3.913l3.317-1.207zM16.95 3.903L13.724 2.73l-3.269 1.19 3.225 1.174zM15.365 4.606l-1.624.592v3.868l3.317-1.207V3.991l-1.693.615zm-.391 2.778c-.367.134-.662-.074-.662-.464s.295-.813.662-.946c.366-.133.663.074.663.464s-.297.813-.663.946z M10.229 18.41v-3.914l-3.322-1.209V17.2zM13.678 17.182v-3.913l-3.371 1.227v3.913z M13.756 17.154l3.3-1.2V12.04l-3.3 1.2zM13.678 21.217l-3.371 1.227v-3.912h-.078v3.912l-3.322-1.209v-3.913l-.053-.058-.025-.06-3.336-1.21v-3.948l.034.013 3.287 1.196.015-.078-3.261-1.187 3.26-1.187v-.109L3.876 9.62l-.307-.112 3.26-1.188v.877l.079-.055V6.769l3.257 1.185.058-.061L7.084 6.75l-.102-.037 3.24-1.179v-.083L6.854 6.677v.018l-.025.018v1.523L3.44 9.47v.02l-.025.017v4.007l-3.39 1.233v.019L0 14.784v3.995l.025.037 3.4 1.237.008-.006.007.01 3.4 1.238.008-.006.006.01 3.4 1.237.014-.009.012.01 3.45-1.256.026-.037-.078-.027zM3.493 9.563l3.257 1.185-3.257 1.187V9.562zM3.4 19.96L.078 18.752v-3.913l2.361.86.96.349v3.913zm.015-3.99L.335 14.85l-.182-.066 3.262-1.187v2.374zm3.399 5.231l-3.321-1.209v-3.912l3.321 1.209v3.912zM23.791 5.434l-3.21-1.17v2.338zM20.387 2.643l-3.24-1.18-3.27 1.19 3.247 1.182z"/></svg>
      </a>
    </div>
  </div>
  <div class="welcome-inner">
    <div class="welcome-brand"><img class="welcome-brand-logo" src="/api/logo.png" alt="Pyllmits logo"/><h1>Pyllmits</h1></div>
    <div class="welcome-tagline">Finding the limits of spatial reasoning in large language models</div>

    <!-- Demo clip - a real run from the harness, pinned to autoplay/loop/muted
         with no controls, no focus, no pointer events and no context menu, so
         it's a passive demo, not a player the user can pause or scrub. -->
    <div class="welcome-demo">
      <video src="/api/demo_video"
        autoplay muted loop playsinline disablepictureinpicture disableremoteplayback
        controlslist="nodownload noplaybackrate nofullscreen" tabindex="-1"
        oncontextmenu="return false"></video>
      <div class="welcome-demo-caption">gpt-5.6-sol navigating an 18&times;18 maze with two zombies</div>
    </div>

    <div class="card">
      <h3><span class="python-logo" aria-hidden="true"><svg viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
        <linearGradient id="pyLogoA" gradientUnits="userSpaceOnUse" x1="70.252" y1="1237.476" x2="170.659" y2="1151.089" gradientTransform="matrix(.563 0 0 -.568 -29.215 707.817)"><stop offset="0" stop-color="#5A9FD4"/><stop offset="1" stop-color="#306998"/></linearGradient>
        <linearGradient id="pyLogoB" gradientUnits="userSpaceOnUse" x1="209.474" y1="1098.811" x2="173.62" y2="1149.537" gradientTransform="matrix(.563 0 0 -.568 -29.215 707.817)"><stop offset="0" stop-color="#FFD43B"/><stop offset="1" stop-color="#FFE873"/></linearGradient>
        <path fill="url(#pyLogoA)" transform="translate(0 10.26)" d="M63.391 1.988c-4.222.02-8.252.379-11.8 1.007-10.45 1.846-12.346 5.71-12.346 12.837v9.411h24.693v3.137H29.977c-7.176 0-13.46 4.313-15.426 12.521-2.268 9.405-2.368 15.275 0 25.096 1.755 7.311 5.947 12.519 13.124 12.519h8.491V67.234c0-8.151 7.051-15.34 15.426-15.34h24.665c6.866 0 12.346-5.654 12.346-12.548V15.833c0-6.693-5.646-11.72-12.346-12.837-4.244-.706-8.645-1.027-12.866-1.008zM50.037 9.557c2.55 0 4.634 2.117 4.634 4.721 0 2.593-2.083 4.69-4.634 4.69-2.56 0-4.633-2.097-4.633-4.69-.001-2.604 2.073-4.721 4.633-4.721z"/>
        <path fill="url(#pyLogoB)" transform="translate(0 10.26)" d="M91.682 28.38v10.966c0 8.5-7.208 15.655-15.426 15.655H51.591c-6.756 0-12.346 5.783-12.346 12.549v23.515c0 6.691 5.818 10.628 12.346 12.547 7.816 2.297 15.312 2.713 24.665 0 6.216-1.801 12.346-5.423 12.346-12.547v-9.412H63.938v-3.138h37.012c7.176 0 9.852-5.005 12.348-12.519 2.578-7.735 2.467-15.174 0-25.096-1.774-7.145-5.161-12.521-12.348-12.521h-9.268zM77.809 87.927c2.561 0 4.634 2.097 4.634 4.692 0 2.602-2.074 4.719-4.634 4.719-2.55 0-4.633-2.117-4.633-4.719 0-2.595 2.083-4.692 4.633-4.692z"/>
      </svg></span>The <code>pyllmits</code> package</h3>
      <div class="sub" style="margin-bottom:var(--s4)">
        Pyllmits is published on PyPI - install it to drive experiments from the command line.
      </div>
      <div class="pypi-row">
        <pre>pip install pyllmits</pre>
        <a class="btn-primary btn-sm" href="https://pypi.org/project/pyllmits/" target="_blank" rel="noopener noreferrer">View on PyPI &#8594;</a>
      </div>
    </div>

    <div class="card">
      <h3><span class="python-logo mono" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg></span>The <code>pyllmits</code> repository</h3>
      <div class="sub" style="margin-bottom:var(--s4)">
        Everything - this Studio included - lives in one repo. Browse the code, star it, or open an issue.
      </div>
      <div class="pypi-row">
        <pre>git clone https://github.com/rjvb7424/pyllmits.git</pre>
        <a class="btn-primary btn-sm" href="https://github.com/rjvb7424/pyllmits" target="_blank" rel="noopener noreferrer">View on GitHub &#8594;</a>
      </div>
    </div>

    <p class="welcome-desc">
      Pyllmits drops language models into a hand-built <b>Crafter</b> survival world and measures
      whether they can complete an objective, turn by turn. This Studio is the browser UI for
      building configs, launching runs, and reviewing results.
    </p>

    <div class="card">
      <h3>API keys</h3>
      <div class="sub" style="margin-bottom:var(--s4)">
        Paste keys for the backends you plan to use. They're written straight to a local
        <code>.env</code> file in this project (never committed - it's git-ignored, never sent
        anywhere else) and picked up immediately, no restart needed. Leave a field blank to keep
        whatever's already set.
      </div>
      <div id="envFields"><div class="muted">Loading&hellip;</div></div>
    </div>
  </div>

  <div class="welcome-footer">
    <div class="welcome-footer-inner">
      <div>
        <div class="welcome-footer-cta">Ready to put a model in the maze?</div>
        <div class="welcome-footer-sub">Head into the Studio to build a config and launch a run.</div>
      </div>
      <button class="btn-primary" onclick="continueToApp()" style="min-width:220px;padding:0 var(--s8)">Continue &#8594;</button>
    </div>
  </div>
</div>

<div id="app" class="hidden">
<header>
  <div class="brand brand-link" role="button" tabindex="0" onclick="showWelcome()"
    onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();showWelcome();}"
    title="Back to start screen" aria-label="Back to start screen">
    <img class="mark" src="/api/logo.png" alt=""/><span>Pyllmits</span>
  </div>
  <nav role="tablist">
    <button class="tab active" data-tab="configs" role="tab">Configs</button>
    <button class="tab" data-tab="run" role="tab">Run</button>
    <button class="tab" data-tab="graphs" role="tab">Graphs</button>
    <button class="tab" data-tab="videos" role="tab">Videos</button>
    <button class="tab" data-tab="paperfold" role="tab">Paper Folding</button>
    <button class="tab" data-tab="providers" role="tab">Providers</button>
  </nav>
  <div style="flex:1"></div>
  <button id="hdrStatus" onclick="hdrStatusClick()" title="idle" aria-label="Run status - idle">
    <span class="status-dot idle" id="statusDot"></span>
    <span class="status-label" id="statusLabel">idle</span>
    <span class="status-detail" id="statusDetail"></span>
  </button>
</header>

<main>
  <!-- CONFIGS -->
  <section id="tab-configs">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Configs</h2><div class="sub">Browse, edit, duplicate, and run your saved experiment configs.</div></div>
      <button class="btn-primary" onclick="newConfig()">+ New config</button>
    </div>
    <div class="cfg-table" id="cfgRows"></div>
  </section>

  <!-- EDITOR (reached via New / Edit / Duplicate) -->
  <section id="tab-editor" class="hidden">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Editor</h2><div class="sub"><span class="pill" id="edPath">unsaved</span><span class="pill danger hidden" id="edDirty" style="margin-left:8px" title="You have changes that haven't been saved yet">&#9679; Unsaved changes</span></div></div>
      <div class="flex">
        <button class="btn-secondary" onclick="go('configs')">Cancel</button>
        <button class="btn-primary" onclick="saveConfig()">Save config</button>
        <button class="btn-danger hidden" id="edDelete" onclick="deleteCurrentConfig()">Delete</button>
      </div>
    </div>

    <div class="card"><h3>Experiment</h3>
      <div class="sub" style="margin-bottom:var(--s4)">Basic run settings - trials, turn limit, and video recording.</div>
      <div class="row">
        <div><label for="e_name">Name</label><input id="e_name"></div>
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
      <div class="sub" style="margin-bottom:var(--s4)">What counts as success in this world.</div>
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
    </div>

    <div class="card"><h3>Models</h3>
      <div class="sub" style="margin-bottom:var(--s4)">The models being evaluated - each one runs independently through every trial.</div>
      <div id="models"></div>
      <button class="btn-secondary btn-sm" onclick="addModel()">+ Add model</button>
    </div>

    <div class="card"><h3>Prompt</h3>
      <div class="sub" style="margin-bottom:var(--s4)">What the model sees each turn: the system instructions and the per-turn state.</div>
      <div class="flex" style="margin-bottom:var(--s2)">
        <label class="check"><input type="checkbox" id="p_leg"> legend</label>
        <label class="check"><input type="checkbox" id="p_inv"> inventory</label>
        <label class="check"><input type="checkbox" id="p_ach"> achievements</label>
        <label class="check"><input type="checkbox" id="p_act"> action list</label>
      </div>
      <label for="p_sys">System</label><textarea id="p_sys"></textarea>
      <label for="p_user">User</label><textarea id="p_user"></textarea>
    </div>
  </section>

  <!-- RUN -->
  <section id="tab-run" class="hidden">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Run</h2><div class="sub">Launch a config and watch it live.</div></div>
      <div class="flex">
        <select id="runConfigPick" onchange="pickRunConfig(this.value)" style="width:260px;text-overflow:ellipsis" aria-label="Config to run"></select>
        <button class="btn-primary" onclick="runGo()">&#9654;&nbsp;Go</button>
        <button class="btn-secondary" onclick="runPause()">&#10073;&#10073;&nbsp;Pause</button>
        <button class="btn-secondary" onclick="runResume()">&#9654;&nbsp;Resume</button>
        <button class="btn-secondary" onclick="runRestart()">&#8635;&nbsp;Restart</button>
        <button class="btn-danger" onclick="runStop()">&#9632;&nbsp;Stop</button>
        <button class="btn-ghost" onclick="runCancel()">Cancel</button>
      </div>
    </div>
    <div class="live-grid">
      <div>
        <div class="live-frame" id="liveFrame"><span class="muted mono" style="font-size:28px">&ndash;</span></div>
        <div class="live-chips">
          <div class="chip"><div class="k">Model</div><div class="v" id="lvModel">&ndash;</div></div>
          <div class="chip"><div class="k">Trial</div><div class="v" id="lvTrial">&ndash;</div></div>
          <div class="chip"><div class="k">Turn</div><div class="v" id="lvTurn">&ndash;</div></div>
        </div>
        <div class="live-chips">
          <div class="chip"><div class="k">Action</div><div class="v accent" id="lvAction">&ndash;</div></div>
          <div class="chip"><div class="k">Think time</div><div class="v" id="lvThink">&ndash;</div></div>
          <div class="chip"><div class="k">Facing</div><div class="v" id="lvFacing">&ndash;</div></div>
        </div>
        <div class="card"><h3>Inventory / achievements</h3><pre id="lvState">&ndash;</pre></div>
      </div>
      <div>
        <div class="card"><h3>Model raw response</h3><pre id="lvResponse">&ndash;</pre></div>
        <div class="card"><h3>Prompt sent this turn</h3><pre id="lvPrompt">&ndash;</pre></div>
      </div>
    </div>
  </section>

  <!-- GRAPHS -->
  <section id="tab-graphs" class="hidden">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Graphs</h2><div class="sub">Result plots for a completed run.</div></div>
      <div class="flex">
        <select id="runPick" onchange="showRun()" style="width:240px;text-overflow:ellipsis" aria-label="Pick a run"></select>
        <button class="btn-primary" onclick="regenGraphs()">&#8635;&nbsp;Regenerate graphs</button>
        <button class="btn-secondary" id="downloadAllBtn" onclick="downloadAllGraphs()" disabled
          title="Saves every graph as a PNG into a new folder in your Downloads">Download all</button>
      </div>
    </div>
    <div id="plots"></div>
  </section>

  <!-- VIDEOS -->
  <section id="tab-videos" class="hidden">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Videos</h2><div class="sub">Recorded trial videos for a completed run, per model.</div></div>
      <div class="flex">
        <select id="vidPick" onchange="showVideos()" style="width:240px;text-overflow:ellipsis" aria-label="Pick a run"></select>
        <button class="btn-danger" onclick="deleteRun('vidPick')">Delete run</button>
      </div>
    </div>
    <div id="videosList"></div>
  </section>

  <!-- PAPER FOLDING - a second, independent experiment. It shares the models/
       provider layer (same Backend/Model pickers, same API keys) but nothing
       else with the Crafter tabs above: its own run state, its own results,
       its own status panel (not the header pill), its own graphs. -->
  <section id="tab-paperfold" class="hidden">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Paper Folding</h2><div class="sub">A spatial-reasoning test: fold a grid, punch a hole through the folded layers, and ask a model which of five unfolded candidates matches. Independent of the Crafter tabs above - runs its own trials against its own model pool.</div></div>
    </div>

    <div class="card"><h3>Setup</h3>
      <div class="sub" style="margin-bottom:var(--s4)">Each puzzle is freshly randomised (no fixed seed) - accuracy is meant to average out over enough trials, not to be reproduced trial-for-trial.</div>

      <label for="pfSetupPick">Resume or edit a previous run</label>
      <div class="sub" style="margin-top:0;margin-bottom:var(--s2)">Picking a run loads its settings below. Raise trials to run more (already-completed trials are skipped); add a new model and only that one runs, from trial 1.</div>
      <div class="flex">
        <select id="pfSetupPick" onchange="pfPickSetupRun(this.value)" style="flex:1;text-overflow:ellipsis">
          <option value="">-- start a new run --</option>
        </select>
        <button class="btn-secondary btn-sm" onclick="pfSaveSetup()" title="Save this setup to disk without running any trials - handy for reserving a name and model list you'll come back to">Save setup</button>
        <button class="btn-danger btn-sm" onclick="pfDeleteRun('pfSetupPick')">Delete</button>
      </div>

      <div class="row" style="margin-top:var(--s4)">
        <div><label for="pf_name">Run name</label><input id="pf_name" placeholder="my_paperfold_run"></div>
        <div><label for="pf_trials">Trials per model</label><input id="pf_trials" type="number" min="1" value="30"></div>
        <div><label for="pf_folds">Folds per puzzle</label><input id="pf_folds" type="number" min="1" value="3"></div>
      </div>

      <label for="pf_dirmode">Direction names</label>
      <div class="sub" style="margin-top:0;margin-bottom:var(--s2)">Optionally replace north/south/east/west with placeholder words in the prompt, to test whether a model is doing real spatial reasoning or just pattern-matching on those specific direction words.</div>
      <select id="pf_dirmode" onchange="pfUpdateDirMode()">
        <option value="real">Real names (north / south / east / west)</option>
        <option value="fixed">Custom placeholders (same words every trial)</option>
        <option value="random">Random placeholders (new words every trial)</option>
      </select>
      <div id="pfDirLabelsBox" class="hidden" style="margin-top:var(--s3)">
        <div class="row">
          <div><label for="pf_dir_north">North</label><input id="pf_dir_north" placeholder="e.g. yellow"></div>
          <div><label for="pf_dir_south">South</label><input id="pf_dir_south" placeholder="e.g. green"></div>
          <div><label for="pf_dir_east">East</label><input id="pf_dir_east" placeholder="e.g. blue"></div>
          <div><label for="pf_dir_west">West</label><input id="pf_dir_west" placeholder="e.g. red"></div>
          <div><label aria-hidden="true">&nbsp;</label><button class="btn-secondary" style="width:100%" onclick="pfShuffleDirLabels()">&#127922;&nbsp;Shuffle</button></div>
        </div>
      </div>

      <label>Models</label>
      <div class="sub" style="margin-top:0;margin-bottom:var(--s2)">The pool of models to test - pick as many as you like, from any provider you have a key for.</div>
      <div id="pfModels"></div>
      <button class="btn-secondary btn-sm" onclick="pfAddModel()">+ Add model</button>
    </div>

    <div class="card"><h3>Run</h3>
      <div class="flex" style="margin-bottom:var(--s4)">
        <button class="btn-primary" onclick="pfRunGo()">&#9654;&nbsp;Start</button>
        <button class="btn-secondary" onclick="pfRunPause()">&#10073;&#10073;&nbsp;Pause</button>
        <button class="btn-secondary" onclick="pfRunResume()">&#9654;&nbsp;Resume</button>
        <button class="btn-danger" onclick="pfRunStop()">&#9632;&nbsp;Stop</button>
      </div>
      <div class="live-chips">
        <div class="chip"><div class="k">State</div><div class="v" id="pfState">idle</div></div>
        <div class="chip"><div class="k">Model</div><div class="v" id="pfModel">&ndash;</div></div>
        <div class="chip"><div class="k">Trial</div><div class="v" id="pfTrial">&ndash;</div></div>
        <div class="chip"><div class="k">This question</div><div class="v accent" id="pfTimerCurrent">&ndash;</div></div>
        <div class="chip"><div class="k">Previous question</div><div class="v" id="pfTimerPrev">&ndash;</div></div>
      </div>
      <div class="live-chips">
        <div class="chip"><div class="k">Last answer</div><div class="v" id="pfLast">&ndash;</div></div>
        <div class="chip"><div class="k">Directions this trial</div><div class="v mono" id="pfDirLive" style="font-size:12px">&ndash;</div></div>
      </div>
      <div class="row">
        <div class="card"><h3>Model raw response</h3><pre id="pfRawResponse">&ndash;</pre></div>
        <div class="card"><h3>Prompt sent last trial</h3><pre id="pfRawPrompt">&ndash;</pre></div>
      </div>
    </div>

    <div class="card"><h3>Graphs</h3>
      <div class="between" style="margin-bottom:var(--s4)">
        <div class="sub">Result plots for a paper-folding run - regenerate any time, independently of running new trials.</div>
        <div class="flex">
          <select id="pfRunPick" onchange="pfShowRun()" style="width:220px;text-overflow:ellipsis" aria-label="Pick a paper-folding run"></select>
          <button class="btn-primary" onclick="pfRegenGraphs()">&#8635;&nbsp;Regenerate graphs</button>
          <button class="btn-danger" onclick="pfDeleteRun('pfRunPick')">Delete run</button>
        </div>
      </div>
      <div id="pfPlots"></div>
    </div>
  </section>

  <!-- PROVIDERS -->
  <section id="tab-providers" class="hidden">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Providers</h2><div class="sub">API keys for the model backends you use, and links to each provider's own dashboard.</div></div>
    </div>

    <div class="card">
      <h3>API keys</h3>
      <div class="sub" style="margin-bottom:var(--s4)">
        Paste keys for the backends you plan to use. They're written straight to a local
        <code>.env</code> file in this project (never committed - it's git-ignored, never sent
        anywhere else) and picked up immediately, no restart needed. Leave a field blank to keep
        whatever's already set.
      </div>
      <div id="envFieldsMain"><div class="muted">Loading&hellip;</div></div>
    </div>

    <div class="card">
      <h3>Dashboards</h3>
      <div class="sub" style="margin-bottom:var(--s4)">
        Remaining credits and usage live on each provider's own site - Pyllmits has no access to
        that (no provider exposes it through a normal API key). These just jump you there.
      </div>
      <div id="providerDashboards"></div>
    </div>
  </section>
</main>

<div id="terminal" class="collapsed">
  <div id="termResize" title="Drag to resize"></div>
  <div class="term-bar">
    <div class="term-title">Terminal</div>
    <div class="flex" style="gap:4px">
      <button class="btn-ghost btn-sm" id="termToggle" onclick="toggleTerminal()" aria-label="Expand terminal">&#9650;</button>
    </div>
  </div>
  <pre id="termOut"><div class="empty">Waiting for output&hellip;</div></pre>
</div>
</div>

<div id="toasts" aria-live="polite"></div>

<script>
let META=null, CFG=null, GRID=[], SEL='water', painting=false;
const $=id=>document.getElementById(id);
const api=(u,m,b)=>fetch(u,{method:m||'GET',headers:{'Content-Type':'application/json'},
  body:b?JSON.stringify(b):undefined}).then(r=>r.json());
function toast(msg,kind){const t=document.createElement('div');t.className='toast'+(kind?' '+kind:'');
  t.textContent=msg;$('toasts').appendChild(t);setTimeout(()=>t.remove(),3200);}
function go(t){document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.dataset.tab==t));
  ['configs','editor','run','graphs','videos','paperfold','providers'].forEach(s=>$('tab-'+s).classList.toggle('hidden',s!=t));
  if(t=='configs')loadConfigs(); if(t=='graphs')loadRuns(); if(t=='videos')loadRuns(); if(t=='run')loadRunConfigs();
  if(t=='providers')loadEnvStatus(); if(t=='paperfold')pfLoadRuns();}
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
// Model pill colors: grouped by provider family, with distinct shades within
// a family for each specific model (deterministic per name, so a model always
// gets the same shade). OpenAI -> green (GPT-5.x darker, GPT-6.x lighter);
// DeepSeek -> blue (newer versions darker); other known families get their
// own hue so the column stays readable at a glance.
function hashString(s){let h=0;for(let i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))>>>0;}return h;}
function modelColorFamily(n){
  // Amber/gold for OpenAI - kept away from green/red so it never reads as a
  // Completed/Incomplete status color.
  if(/gpt-6|gpt6/.test(n))return{hue:42,sat:60,light:58};              // GPT-6.x: lighter amber
  if(/gpt-5|gpt5/.test(n))return{hue:38,sat:70,light:32};              // GPT-5.x: dark amber
  if(/gpt-oss|gpt-4|(^|[^a-z])o\d/.test(n))return{hue:40,sat:55,light:42}; // other OpenAI: mid amber
  if(/deepseek/.test(n)){
    const v=n.match(/v(\d+(?:\.\d+)?)/), r=n.match(/r(\d+)/);
    const score=v?parseFloat(v[1]):(r?parseFloat(r[1])*0.6:1.5);       // higher version = more modern
    return{hue:214,sat:60,light:Math.max(16,Math.min(46,46-score*6))}; // modern -> darker blue
  }
  if(/qwen/.test(n))return{hue:280,sat:40,light:36};
  if(/llama/.test(n))return{hue:22,sat:55,light:38};
  if(/gemini/.test(n))return{hue:195,sat:50,light:36};
  if(/phi-?\d/.test(n))return{hue:325,sat:40,light:38};
  if(/heuristic|baseline/.test(n))return{hue:0,sat:0,light:45};
  return{hue:210,sat:12,light:42};
}
function modelPillStyle(name){
  const n=name.toLowerCase(), fam=modelColorFamily(n), hash=hashString(n);
  const h=(fam.hue+((hash>>3)%7)-3+360)%360;                // small per-model hue nudge
  const l=Math.max(14,Math.min(66,fam.light+(hash%9)-4));   // per-model shade within the family
  const s=fam.sat;
  return `background:hsla(${h},${s}%,${l}%,.22);border-color:hsla(${h},${s}%,${Math.min(78,l+24)}%,.55);`+
         `color:hsl(${h},${Math.min(s+18,85)}%,${Math.min(90,l+44)}%)`;
}
function modelPill(name){return `<span class="pill" style="${modelPillStyle(name)}">${name}</span>`;}
function configStatus(c){
  if(c.error)return '<span class="pill">error</span>';
  if(c.trials==null)return '<span class="pill">—</span>';
  const done=c.trials_done??0;
  return done>=c.trials?'<span class="pill ok">Completed</span>':'<span class="pill danger">Incomplete</span>';
}
async function loadConfigs(){
  const el=$('cfgRows'); el.innerHTML='<div class="empty muted">Loading configs&hellip;</div>';
  const r=await api('/api/configs');
  if(!r.configs||!r.configs.length){el.innerHTML='<div class="empty"><b>No configs yet</b>Create one with + New config, then paint a world.</div>';return;}
  el.innerHTML=`<div class="cfg-head">
      <div>Name</div><div>Size</div><div>Objective</div><div>Status</div><div>Trials</div><div>Turns</div>
      <div>Models</div><div>Actions</div>
    </div>`+r.configs.map(c=>`<div class="cfg">
    <div class="name">${c.name||'(unnamed)'}</div>
    <div class="field">${c.size?c.size.join('\u00d7'):'\u2014'}</div>
    <div class="field obj">${c.objective?`<span class="pill accent" title="${c.objective}">${c.objective}</span>`:'\u2014'}</div>
    <div class="field">${configStatus(c)}</div>
    <div class="field">${c.trials!=null?(c.trials_done??0)+'/'+c.trials:'\u2014'}</div>
    <div class="field">${c.turns!=null?c.turns:'\u2014'}</div>
    <div class="models" title="${(c.models||[]).join(', ')}">${(c.models||[]).map(modelPill).join('')||'<span class="muted">\u2014</span>'}</div>
    <div class="actions">
      <button class="btn-secondary btn-sm" onclick='dupConfig(${JSON.stringify(c.path)})'>Duplicate</button>
      <button class="btn-secondary btn-sm" onclick='editConfig(${JSON.stringify(c.path)})'>Edit</button>
      <button class="btn-primary btn-sm" onclick='selectRun(${JSON.stringify(c.path)})'>&#9654; Run</button>
      <button class="btn-danger btn-sm" onclick='delConfigRow(${JSON.stringify(c.path)})'>Delete</button>
    </div></div>`).join('');
  // Only lists long enough to actually need scrolling pin to the top; a
  // short list centers like every other column (checked post-render, since
  // it depends on real layout - a fixed row count can't predict wrapping).
  el.querySelectorAll('.models').forEach(m=>{if(m.scrollHeight>m.clientHeight+1)m.classList.add('scroll');});
}
// ---------- Unsaved-changes tracking ----------
let DIRTY=false;
function markDirty(){DIRTY=true;$('edDirty').classList.remove('hidden');}
function clearDirty(){DIRTY=false;$('edDirty').classList.add('hidden');}
// One delegated listener catches every field in the editor - including ones
// re-rendered later (models, world grid inputs) - without wiring each up by hand.
document.getElementById('tab-editor').addEventListener('input',markDirty);
document.getElementById('tab-editor').addEventListener('change',markDirty);

let EDPATH=null;
function newConfig(){CFG=defaultConfig();EDPATH=null;
  $('edPath').textContent='new';$('edDelete').classList.add('hidden');formFromCfg();clearDirty();go('editor');}
async function editConfig(path){const r=await api('/api/config?path='+encodeURIComponent(path));
  CFG=r.data;EDPATH=path;$('edPath').textContent=path;
  $('edDelete').classList.remove('hidden');formFromCfg();clearDirty();go('editor');}
async function dupConfig(path){if(!confirm('Duplicate '+path+'?'))return;
  const r=await api('/api/config/duplicate','POST',{path});
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
  setCell(x,y,SEL); markDirty();}
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

// ---------- Models ----------
function presetsFor(backend){return (META.model_presets&&META.model_presets[backend])||[];}
function modelOptions(m){
  const list=presetsFor(m.backend).slice();
  if(m.name&&!list.includes(m.name))list.unshift(m.name);
  const placeholder=m.name?'':`<option value="" selected disabled>-- pick a model --</option>`;
  const opts=list.map(p=>`<option ${p==m.name?'selected':''}>${p}</option>`).join('');
  return placeholder+opts+`<option value="__custom__">(custom id...)</option>`;
}
function pickModel(i,v){
  if(v=='__custom__'){const c=prompt('Enter model id:',CFG.models[i].name||'');
    if(c)CFG.models[i].name=c; renderModels(); return;}
  CFG.models[i].name=v; renderModels();
}
function switchBackend(i,v){CFG.models[i].backend=v; CFG.models[i].name='';
  // A model id from one backend usually isn't valid for another, so force a
  // deliberate re-pick rather than silently keeping a mismatched name.
  renderModels();}
// Reasoning-style models (OpenAI o-series, gpt-5.x/6.x, or anything given a
// reasoning_effort) reject a custom temperature - mirrors
// OpenAIModel._is_reasoning_model in models/openai_api.py, so the editor
// never offers a field that would just be silently dropped at request time.
function isReasoningModel(m){
  if(m.reasoning_effort)return true;
  const n=(m.name||'').toLowerCase();
  return /^o\d/.test(n)||/^gpt-?[56](\.\d+)?/.test(n);
}
function renderModels(){$('models').innerHTML=(CFG.models||[]).map((m,i)=>{
  const ready=!!m.name;
  const readyIcon=ready
    ?`<span title="Ready - ${m.name} on ${m.backend}" style="color:var(--ok);font-size:16px" aria-label="Model ready">&#10003;</span>`
    :`<span title="Not ready - pick a model for this backend" style="color:var(--danger);font-size:16px" aria-label="Model not ready">&#10007;</span>`;
  const reasoning=isReasoningModel(m);
  if(reasoning)delete m.temperature;
  const temperatureField=reasoning
    ?`<div><label>temperature</label><div class="muted" style="min-height:40px;display:flex;align-items:center;font-size:13px">Not supported by this model</div></div>`
    :`<div><label>temperature</label><input value="${m.temperature??''}" oninput="setOpt(${i},'temperature',this.value)"></div>`;
  return `
  <div class="model">
    <div class="between" style="margin-bottom:var(--s2)">
      <div class="flex" style="gap:var(--s2)">${readyIcon}<b>${m.name||'model '+(i+1)}</b></div>
      <button class="btn-danger btn-sm" onclick="delModel(${i})">Remove</button></div>
    <div class="row">
      <div><label>Backend</label><select onchange="switchBackend(${i},this.value)">
        ${META.backends.map(b=>`<option ${b==m.backend?'selected':''}>${b}</option>`).join('')}</select></div>
      <div><label>Model</label><select onchange="pickModel(${i},this.value)">${modelOptions(m)}</select></div>
    </div>
    <div class="row">
      <div><label>max_tokens</label><input value="${m.max_tokens??''}" oninput="setOpt(${i},'max_tokens',this.value)"></div>
      ${temperatureField}
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
  </div>`;
}).join('');}
function setOpt(i,k,v){if(v===''){delete CFG.models[i][k];return;}
  CFG.models[i][k]=isNaN(+v)||['reasoning_effort'].includes(k)?v:+v;}
function addModel(){CFG.models.push({name:presetsFor('openai')[0]||'gpt-4o-mini',backend:'openai',history_turns:8});renderModels();markDirty();}
function delModel(i){CFG.models.splice(i,1);renderModels();markDirty();}
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
  if(r.ok){EDPATH=r.path;$('edPath').textContent=r.path;$('edDelete').classList.remove('hidden');clearDirty();toast('Saved '+r.path,'ok');}
  else toast('Error: '+r.error,'err');}

// ---------- Run ----------
// Status polling runs continuously from boot (not just while the Run tab is
// open) and drives both the header status dot and the live-view panel below
// - a run keeps going in the background no matter which tab you're looking
// at, so status belongs where it's always visible, and the live view is
// native markup (always rendered, filled with placeholders when idle)
// instead of an iframe that's blank until a run starts.
let RUNPATH=null, lastRunState=null, runCancelled=false, lvFrameKey=null;
async function loadRunConfigs(){const r=await api('/api/configs');
  const sel=$('runConfigPick');
  sel.innerHTML='<option value="">-- select a config --</option>'+
    (r.configs||[]).map(c=>`<option value="${c.path}" ${c.path==RUNPATH?'selected':''}>${c.name||c.path}</option>`).join('');
}
function pickRunConfig(path){RUNPATH=path||null;}
function selectRun(path){RUNPATH=path;go('run');}
async function runGo(){if(!RUNPATH){toast('Pick a config to run first','err');return;}
  const r=await api('/api/run/start','POST',{path:RUNPATH});
  if(!r.ok){toast(r.error,'err');return;}
  runCancelled=false;
  toast('Experiment started','ok');}
function runPause(){api('/api/run/pause','POST');}
function runResume(){api('/api/run/resume','POST');}
function runStop(){api('/api/run/stop','POST');toast('Stopping\u2026');}
async function runRestart(){await api('/api/run/stop','POST');
  let tries=0;const wait=setInterval(async()=>{const s=await api('/api/run/status');
    if(!s.running||++tries>15){clearInterval(wait);runGo();}},600);}
async function runCancel(){await api('/api/run/stop','POST');
  runCancelled=true;go('configs');}

// ---------- Header status dot (reflects Crafter AND Paper Folding - whichever
// is more "active" drives the dot's colour/label; the detail line shows both
// at once if both happen to be running/paused, since they're fully
// independent and can be going simultaneously) ----------
let LAST_CRAFTER_STATUS={state:'idle'}, LAST_PAPERFOLD_STATUS={state:'idle'};
const STATUS_RANK={running:0,stopping:0,paused:1,error:2,cancelled:2,stopped:3,finished:4,idle:5};
function oneStatusMeta(s,cancelled){
  if(cancelled)return{cls:'cancelled',label:'cancelled'};
  const st=s.state||'idle';
  if(['running','paused','stopped','finished','error'].includes(st))return{cls:st,label:st};
  return{cls:'idle',label:'idle'};
}
function craftDetail(s){
  return s.model?`${s.model} \u00b7 trial ${s.trial}/${s.num_trials} \u00b7 turn ${s.turn}/${s.max_turns}`:(s.error||'');
}
function pfHdrDetail(s){
  return s.model?`${s.model} \u00b7 trial ${s.trial}/${s.num_trials}`:(s.error||'');
}
function updateStatusDot(){
  const c=LAST_CRAFTER_STATUS, p=LAST_PAPERFOLD_STATUS;
  const cMeta=oneStatusMeta(c,runCancelled), pMeta=oneStatusMeta(p,false);
  const craftLeads=(STATUS_RANK[cMeta.cls]??5)<=(STATUS_RANK[pMeta.cls]??5);
  const meta=craftLeads?cMeta:pMeta;

  $('statusDot').className='status-dot '+meta.cls;
  $('statusLabel').textContent=meta.label;

  const parts=[];
  if(['running','paused'].includes(cMeta.cls))parts.push('Crafter: '+craftDetail(c));
  if(['running','paused'].includes(pMeta.cls))parts.push('Paper Folding: '+pfHdrDetail(p));
  const detail=parts.length?parts.join('  \u00b7  '):((craftLeads?c:p).error||'');

  $('statusDetail').textContent=detail;
  const title=meta.label+(detail?(' \u2014 '+detail):'');
  $('hdrStatus').title=title;$('hdrStatus').setAttribute('aria-label','Run status - '+title);
}
function hdrStatusClick(){
  const active=s=>['running','paused'].includes(s.state||'idle');
  go(active(LAST_PAPERFOLD_STATUS)&&!active(LAST_CRAFTER_STATUS)?'paperfold':'run');
}

// ---------- Run tab live view (native, not an iframe) ----------
function fmtInventory(inv){
  if(!inv||!Object.keys(inv).length)return'(empty)';
  return Object.entries(inv).map(([k,v])=>k+': '+v).join('\n');
}
function updateLiveView(s){
  const has=s.model!=null;
  $('lvModel').textContent=s.model||'\u2013';
  $('lvTrial').textContent=has?`${s.trial||'\u2013'} / ${s.num_trials||'\u2013'}`:'\u2013';
  $('lvTurn').textContent=has?`${s.turn||'\u2013'} / ${s.max_turns||'\u2013'}`:'\u2013';
  const act=$('lvAction');act.textContent=s.action||'\u2013';
  act.classList.toggle('bad',s.parse_ok===false);
  $('lvThink').textContent=s.think_seconds!=null?s.think_seconds.toFixed(2)+'s':'\u2013';
  $('lvFacing').textContent=s.facing||'\u2013';
  const ach=(s.achievements&&s.achievements.length)?s.achievements.join(', '):'none yet';
  $('lvState').textContent=has?('inventory\n'+fmtInventory(s.inventory)+'\n\nachievements\n'+ach):'\u2013';
  $('lvResponse').textContent=s.raw_response||'\u2013';
  $('lvPrompt').textContent=s.prompt||'\u2013';

  const frameKey=has?`${s.model}|${s.trial}|${s.turn}`:null;
  if(frameKey&&frameKey!==lvFrameKey){
    lvFrameKey=frameKey;
    $('liveFrame').innerHTML=`<img alt="state" src="/api/run/frame.png?t=${Date.now()}">`;
  }else if(!has&&lvFrameKey!==null){
    lvFrameKey=null;
    $('liveFrame').innerHTML='<span class="muted mono" style="font-size:28px">\u2013</span>';
  }
}

async function pollRunStatus(){
  const s=await api('/api/run/status');
  LAST_CRAFTER_STATUS=s;
  updateStatusDot();
  updateLiveView(s);
  if(['finished','stopped','error'].includes(s.state)&&!s.running&&lastRunState!==s.state){
    if(s.state=='finished'){toast('Run finished \u2014 generating graphs\u2026','ok');
      if(s.run_name)analyzeAfterRun(s.run_name);}}
  lastRunState=s.state;
}
setInterval(pollRunStatus,700);
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
  $('downloadAllBtn').disabled=!$('runPick').value;
  window._runs=r.runs;}
function showRun(){const name=$('runPick').value;const run=(window._runs||[]).find(r=>r.name==name);const bust=Date.now();
  $('downloadAllBtn').disabled=!name;
  if(!name){$('plots').innerHTML='<div class="empty"><b>No run selected</b>Pick a run above to see its plots.</div>';return;}
  if(!run||!run.plots.length){$('plots').innerHTML='<div class="empty"><b>No plots yet</b>Run this config, or press Regenerate graphs.</div>';return;}
  // success_matrix leads the page - everything else keeps its existing order.
  const isMatrix=f=>f.startsWith('success_matrix');
  const files=run.plots.slice().sort((a,b)=>isMatrix(a)?-1:isMatrix(b)?1:0);
  $('plots').innerHTML=files.map(f=>`<div>
    <img class="plot" alt="${f}" src="/api/plot?run=${encodeURIComponent(name)}&file=${encodeURIComponent(f)}&_=${bust}"></div>`).join('');}
async function regenGraphs(){const name=$('runPick').value;
  if(!name){toast('Pick a run first','err');return;}
  toast('Regenerating\u2026');const r=await api('/api/analyze','POST',{run:name});
  if(!r.ok){toast('Error: '+r.error,'err');return;}
  await loadRuns(); $('runPick').value=name; showRun(); toast('Graphs regenerated','ok');}
// Download-all: regenerate the graphs so they're current, then have the
// server copy every plot into one real folder under ~/Downloads (see
// /api/run/download_plots in studio.py). The Studio server and the browser
// are the same machine for this local tool, so this sidesteps the browser's
// download machinery entirely - no zip, no per-click file-picker permission,
// no loose files scattered in the Downloads root.
async function downloadAllGraphs(){
  const name=$('runPick').value;
  if(!name){toast('Pick a run first','err');return;}
  const btn=$('downloadAllBtn'); btn.disabled=true;
  try{
    toast('Regenerating\u2026');
    const r=await api('/api/analyze','POST',{run:name});
    if(!r.ok){toast('Error: '+r.error,'err');return;}
    await loadRuns(); $('runPick').value=name; showRun();
    if(!r.plots||!r.plots.length){toast('No graphs to download','err');return;}
    const d=await api('/api/run/download_plots','POST',{run:name});
    if(!d.ok){toast('Error: '+d.error,'err');return;}
    toast(`Saved ${d.count} graphs to ${d.path}`,'ok');
  } finally {
    btn.disabled=!$('runPick').value;
  }
}
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

// ---------- Paper folding (independent experiment - own state, own routes) ----------
// Model editor: same shape as the Crafter editor's renderModels()/addModel()/etc
// (same META.backends/META.model_presets pool), but not shared code - paper
// folding trials are one independent Q&A per trial, not a multi-turn episode,
// so history_turns/force_action/action_retries are dropped entirely (they'd be
// meaningless here, and force_action's tool schema is Crafter's action set).
// max_tokens defaults much higher than Crafter's 256, since a folded/punched
// grid plus five candidate grids is a lot more content than "one action word".
let PFCFG={models:[]};
function pfDefaultModel(){return{name:presetsFor('openai')[0]||'gpt-4o-mini',backend:'openai',max_tokens:4096};}

// ---------- Paper folding: direction naming ----------
// "real" (default) leaves the prompt exactly as before. "fixed" swaps in one
// set of placeholder words for every trial in the run. "random" draws a
// fresh mapping every trial (still explained at the top of that trial's own
// prompt) - the more rigorous variant, since accuracy can't come from the
// model latching onto one particular word choice.
const PF_WORD_BANK=['red','blue','green','yellow','purple','orange','pink','teal','gold','silver','indigo','crimson'];
function pfUpdateDirMode(){
  const mode=$('pf_dirmode').value;
  $('pfDirLabelsBox').classList.toggle('hidden',mode!=='fixed');
  if(mode=='fixed'&&!$('pf_dir_north').value)pfShuffleDirLabels();
}
function pfShuffleDirLabels(){
  const pool=PF_WORD_BANK.slice(),picks=[];
  for(let i=0;i<4;i++){const idx=Math.floor(Math.random()*pool.length);picks.push(pool.splice(idx,1)[0]);}
  $('pf_dir_north').value=picks[0];$('pf_dir_south').value=picks[1];
  $('pf_dir_east').value=picks[2];$('pf_dir_west').value=picks[3];
}
function pfFormatDirLabels(labels){
  if(!labels)return 'real names';
  return `N=${labels.north} S=${labels.south} E=${labels.east} W=${labels.west}`;
}

function pfIsReasoningModel(m){
  if(m.reasoning_effort)return true;
  const n=(m.name||'').toLowerCase();
  return /^o\d/.test(n)||/^gpt-?[56](\.\d+)?/.test(n);
}
function pfModelOptions(m){
  const list=presetsFor(m.backend).slice();
  if(m.name&&!list.includes(m.name))list.unshift(m.name);
  const placeholder=m.name?'':`<option value="" selected disabled>-- pick a model --</option>`;
  const opts=list.map(p=>`<option ${p==m.name?'selected':''}>${p}</option>`).join('');
  return placeholder+opts+`<option value="__custom__">(custom id...)</option>`;
}
function pfPickModel(i,v){
  if(v=='__custom__'){const c=prompt('Enter model id:',PFCFG.models[i].name||'');
    if(c)PFCFG.models[i].name=c; pfRenderModels(); return;}
  PFCFG.models[i].name=v; pfRenderModels();
}
function pfSwitchBackend(i,v){PFCFG.models[i].backend=v; PFCFG.models[i].name=''; pfRenderModels();}
function pfSetOpt(i,k,v){if(v===''){delete PFCFG.models[i][k];return;}
  PFCFG.models[i][k]=isNaN(+v)||['reasoning_effort'].includes(k)?v:+v;}
function pfRenderModels(){$('pfModels').innerHTML=(PFCFG.models||[]).map((m,i)=>{
  const ready=!!m.name;
  const readyIcon=ready
    ?`<span title="Ready - ${m.name} on ${m.backend}" style="color:var(--ok);font-size:16px" aria-label="Model ready">&#10003;</span>`
    :`<span title="Not ready - pick a model for this backend" style="color:var(--danger);font-size:16px" aria-label="Model not ready">&#10007;</span>`;
  const reasoning=pfIsReasoningModel(m);
  if(reasoning)delete m.temperature;
  const temperatureField=reasoning
    ?`<div><label>temperature</label><div class="muted" style="min-height:40px;display:flex;align-items:center;font-size:13px">Not supported by this model</div></div>`
    :`<div><label>temperature</label><input value="${m.temperature??''}" oninput="pfSetOpt(${i},'temperature',this.value)"></div>`;
  return `
  <div class="model">
    <div class="between" style="margin-bottom:var(--s2)">
      <div class="flex" style="gap:var(--s2)">${readyIcon}<b>${m.name||'model '+(i+1)}</b></div>
      <button class="btn-danger btn-sm" onclick="pfDelModel(${i})">Remove</button></div>
    <div class="row">
      <div><label>Backend</label><select onchange="pfSwitchBackend(${i},this.value)">
        ${META.backends.map(b=>`<option ${b==m.backend?'selected':''}>${b}</option>`).join('')}</select></div>
      <div><label>Model</label><select onchange="pfPickModel(${i},this.value)">${pfModelOptions(m)}</select></div>
    </div>
    <div class="row">
      <div><label>max_tokens</label><input value="${m.max_tokens??''}" oninput="pfSetOpt(${i},'max_tokens',this.value)"></div>
      ${temperatureField}
      <div><label>reasoning_effort</label><input value="${m.reasoning_effort??''}" oninput="pfSetOpt(${i},'reasoning_effort',this.value)"></div>
      <div><label>request_delay</label><input value="${m.request_delay??''}" oninput="pfSetOpt(${i},'request_delay',this.value)"></div>
    </div>
  </div>`;
}).join('');}
function pfAddModel(){PFCFG.models.push(pfDefaultModel());pfRenderModels();}
function pfDelModel(i){PFCFG.models.splice(i,1);pfRenderModels();}

// ---------- Paper folding: run controls ----------
// Shared by Start and Save setup, so both send the exact same shape and
// validate the same way - the only difference is which route gets it.
function pfBuildRunBody(){
  const name=($('pf_name').value||'').trim();
  if(!name)return{error:'Enter a run name'};
  const models=(PFCFG.models||[]).filter(m=>m.name);
  if(!models.length)return{error:'Add at least one model (with a model id picked)'};
  const direction_mode=$('pf_dirmode').value;
  let direction_labels=null;
  if(direction_mode=='fixed'){
    direction_labels={north:$('pf_dir_north').value.trim(),south:$('pf_dir_south').value.trim(),
                       east:$('pf_dir_east').value.trim(),west:$('pf_dir_west').value.trim()};
    const vals=Object.values(direction_labels);
    if(vals.some(v=>!v))return{error:'Fill in all four direction placeholder names, or switch to Real/Random'};
    if(new Set(vals.map(v=>v.toLowerCase())).size<4)return{error:'Direction placeholder names must all be different'};
  }
  return{body:{name, num_trials:+$('pf_trials').value||30, num_folds:+$('pf_folds').value||3, models,
    direction_mode, direction_labels}};
}
let pfLastState=null;
async function pfRunGo(){
  const {body,error}=pfBuildRunBody();
  if(error){toast(error,'err');return;}
  const r=await api('/api/paperfold/run/start','POST',body);
  if(!r.ok){toast(r.error,'err');return;}
  toast('Paper-folding run started','ok');
}
function pfRunPause(){api('/api/paperfold/run/pause','POST');}
function pfRunResume(){api('/api/paperfold/run/resume','POST');}
function pfRunStop(){api('/api/paperfold/run/stop','POST');toast('Stopping…');}
// Writes the current Setup form to disk - no models built, no API calls - so
// a model list/config can be reserved and come back exactly as left, and so
// a run that later crashes partway through still has every configured model
// on record (not just the ones it got to before the crash).
async function pfSaveSetup(){
  const {body,error}=pfBuildRunBody();
  if(error){toast(error,'err');return;}
  const r=await api('/api/paperfold/setup/save','POST',body);
  if(!r.ok){toast(r.error,'err');return;}
  toast('Setup saved (no trials run yet)','ok');
  await pfLoadRuns();
  $('pfSetupPick').value=body.name;
}

// A local stopwatch, not the 700ms poll cadence - PF_TRIAL_STARTED_AT (the
// server's timestamp for when the in-flight trial began) is refreshed each
// poll, but the displayed number ticks smoothly in between via its own timer.
let PF_TRIAL_STARTED_AT=null, PF_LAST_ELAPSED=null;
function pfTickTimer(){
  $('pfTimerCurrent').textContent=PF_TRIAL_STARTED_AT!=null
    ?(Date.now()/1000-PF_TRIAL_STARTED_AT).toFixed(1)+'s':'–';
}
setInterval(pfTickTimer,100);

function pfUpdateStatus(s){
  $('pfState').textContent=s.state||'idle';
  $('pfModel').textContent=s.model||'–';
  $('pfTrial').textContent=s.model?`${s.trial||'–'} / ${s.num_trials||'–'}`:'–';
  const last=$('pfLast');
  if(s.last_predicted!=null){
    last.textContent=`${s.last_predicted} ${s.last_is_correct?'✓ correct':'✗ wrong (was '+s.last_correct_choice+')'}`;
    last.classList.toggle('bad',!s.last_is_correct);
  }else{last.textContent='–';last.classList.remove('bad');}
  $('pfDirLive').textContent=s.model?pfFormatDirLabels(s.direction_labels):'–';

  PF_TRIAL_STARTED_AT=(s.state=='running'&&s.trial_started_at)?s.trial_started_at:null;
  if(s.last_elapsed_seconds!=null)PF_LAST_ELAPSED=s.last_elapsed_seconds;
  $('pfTimerPrev').textContent=PF_LAST_ELAPSED!=null?PF_LAST_ELAPSED.toFixed(2)+'s':'–';
  pfTickTimer();

  $('pfRawResponse').textContent=s.last_raw_response||'–';
  $('pfRawPrompt').textContent=s.last_prompt||'–';
}
async function pfPollStatus(){
  const s=await api('/api/paperfold/run/status');
  LAST_PAPERFOLD_STATUS=s;
  updateStatusDot();
  pfUpdateStatus(s);
  if(['finished','stopped','error'].includes(s.state)&&!s.running&&pfLastState!==s.state){
    if(s.state=='finished'){toast('Paper-folding run finished — generating graphs…','ok');
      if(s.run_name)pfAnalyzeAfterRun(s.run_name);}
    if(s.state=='error')toast('Paper-folding run failed: '+(s.error||'unknown error'),'err');
  }
  pfLastState=s.state;
}
setInterval(pfPollStatus,700);
async function pfAnalyzeAfterRun(name){
  const r=await api('/api/paperfold/analyze','POST',{run:name});
  if(!r.ok){toast('Graph generation failed: '+r.error,'err');return;}
  toast('Graphs ready','ok');
  if($('tab-paperfold')&&!$('tab-paperfold').classList.contains('hidden')){
    await pfLoadRuns(); $('pfRunPick').value=name; pfShowRun();
  }
}

// ---------- Paper folding: graphs ----------
// Two independent pickers sharing one run list - same split Crafter uses
// between its Run tab's config picker and its Graphs tab's run picker:
// pfSetupPick answers "what do I resume/edit", pfRunPick answers "whose
// plots am I looking at". They usually end up pointing at the same run, but
// don't have to (e.g. comparing an old run's graphs while setting up a new
// one), so they're kept as two selects rather than one shared value.
async function pfLoadRuns(){const r=await api('/api/paperfold/runs');
  const prevGraph=$('pfRunPick').value, prevSetup=$('pfSetupPick').value;
  $('pfRunPick').innerHTML='<option value="">-- pick a run --</option>'+
    r.runs.map(x=>`<option value="${x.name}">${x.name}</option>`).join('');
  $('pfSetupPick').innerHTML='<option value="">-- start a new run --</option>'+
    r.runs.map(x=>`<option value="${x.name}">${x.name}</option>`).join('');
  $('pfRunPick').value=prevGraph;
  $('pfSetupPick').value=prevSetup;
  window._pfRuns=r.runs;}
function pfShowRun(){const name=$('pfRunPick').value;const run=(window._pfRuns||[]).find(r=>r.name==name);const bust=Date.now();
  if(!name){$('pfPlots').innerHTML='<div class="empty"><b>No run selected</b>Pick a run above to see its plots.</div>';return;}
  if(!run||!run.plots.length){$('pfPlots').innerHTML='<div class="empty"><b>No plots yet</b>Run this test, or press Regenerate graphs.</div>';return;}
  $('pfPlots').innerHTML=run.plots.map(f=>`<div>
    <img class="plot" alt="${f}" src="/api/paperfold/plot?run=${encodeURIComponent(name)}&file=${encodeURIComponent(f)}&_=${bust}"></div>`).join('');}
async function pfRegenGraphs(){const name=$('pfRunPick').value;
  if(!name){toast('Pick a run first','err');return;}
  toast('Regenerating…');const r=await api('/api/paperfold/analyze','POST',{run:name});
  if(!r.ok){toast('Error: '+r.error,'err');return;}
  await pfLoadRuns(); $('pfRunPick').value=name; pfShowRun(); toast('Graphs regenerated','ok');}

// ---------- Paper folding: resume/edit a previous run from Setup ----------
// Loads a past run's settings into the form so Start continues it: raising
// Trials makes already-complete models do just the difference (each model
// resumes from however many trials it already has - see
// PaperfoldRunner._run_model), and a newly added model runs in full since it
// has none yet. Only name/backend survive in results.json - per-model tuning
// options (max_tokens, temperature, ...) were never persisted, so those come
// back at their defaults, not whatever they were set to originally.
function pfApplyRunToSetup(run){
  $('pf_name').value=run.name;
  if(run.num_trials!=null)$('pf_trials').value=run.num_trials;
  if(run.num_folds!=null)$('pf_folds').value=run.num_folds;
  $('pf_dirmode').value=run.direction_mode||'real';
  pfUpdateDirMode();
  if(run.direction_mode=='fixed'&&run.direction_labels){
    $('pf_dir_north').value=run.direction_labels.north||'';
    $('pf_dir_south').value=run.direction_labels.south||'';
    $('pf_dir_east').value=run.direction_labels.east||'';
    $('pf_dir_west').value=run.direction_labels.west||'';
  }
  PFCFG.models=(run.models||[]).map(m=>({name:m.name,backend:m.backend||'openai',max_tokens:4096}));
  pfRenderModels();
}
function pfResetSetup(){
  $('pf_name').value='';
  $('pf_trials').value=30;
  $('pf_folds').value=3;
  $('pf_dirmode').value='real';
  pfUpdateDirMode();
  PFCFG.models=[pfDefaultModel()];
  pfRenderModels();
}
function pfPickSetupRun(name){
  if(!name){pfResetSetup();return;}
  const run=(window._pfRuns||[]).find(r=>r.name==name);
  if(!run){toast('Could not find that run','err');return;}
  pfApplyRunToSetup(run);
  // Keep the Graphs picker pointed at the same run, so its existing plots
  // are right there while you decide how to change it.
  $('pfRunPick').value=name; pfShowRun();
  toast('Loaded '+run.name+' - raise trials or add a model, then Start to continue it','ok');
}
async function pfDeleteRun(selectId){
  const name=$(selectId||'pfRunPick').value;
  if(!name){toast('Pick a run first','err');return;}
  if(!confirm('Delete paper-folding run \''+name+'\'? This permanently deletes its results and plots. This cannot be undone.'))return;
  const r=await api('/api/paperfold/run/delete','POST',{run:name});
  if(!r.ok){toast('Error: '+r.error,'err');return;}
  toast('Deleted run '+name,'ok');
  if($('pfSetupPick').value==name)pfResetSetup();
  await pfLoadRuns(); pfShowRun();
}

// ---------- Terminal (mirrors the real process's stdout/stderr/logging) ----------
let TERM_SEQ=0;
function toggleTerminal(){const t=$('terminal'),collapsed=t.classList.toggle('collapsed');
  $('termToggle').innerHTML=collapsed?'&#9650;':'&#9660;';
  $('termToggle').setAttribute('aria-label',collapsed?'Expand terminal':'Collapse terminal');}
function termAppend(lines){
  const out=$('termOut'); const empty=out.querySelector('.empty'); if(empty)empty.remove();
  const atBottom=out.scrollHeight-out.scrollTop-out.clientHeight<24;
  const frag=document.createDocumentFragment();
  for(const l of lines){const d=document.createElement('div');d.className='line '+(l.stream||'stdout');
    d.textContent=l.text;frag.appendChild(d);}
  out.appendChild(frag);
  while(out.childElementCount>4000)out.removeChild(out.firstChild);
  if(atBottom)out.scrollTop=out.scrollHeight;
}
async function pollTerminal(){
  try{const r=await api('/api/console?since='+TERM_SEQ);
    if(r.lines&&r.lines.length){TERM_SEQ=r.next;termAppend(r.lines);}}
  catch(e){/* server not reachable this tick - next poll retries */}
}
setInterval(pollTerminal,900);
// Drag the strip above the terminal to resize it, like an editor's panel.
(function(){const handle=$('termResize'),term=$('terminal');let dragging=false;
  handle.addEventListener('mousedown',e=>{dragging=true;handle.classList.add('active');e.preventDefault();});
  window.addEventListener('mousemove',e=>{if(!dragging)return;
    term.style.height=Math.min(window.innerHeight*0.75,Math.max(120,window.innerHeight-e.clientY))+'px';});
  window.addEventListener('mouseup',()=>{dragging=false;handle.classList.remove('active');});
})();

// ---------- Welcome screen (API keys -> .env, then into the app) ----------
let ENV_FIELDS=[];
async function loadEnvStatus(){
  const r=await api('/api/env/status');
  ENV_FIELDS=r.fields||[];
  renderEnvFields();
  renderProviderDashboards();
}
function renderEnvFields(){
  const html=ENV_FIELDS.map((f,i)=>`
    <div class="env-field">
      <div class="env-label-row">
        <label for="env_${i}">${f.label} <span class="faint mono">(${f.env})</span></label>
        <span class="env-hint${f.set?' set':' unset'}">${f.set?'&#10003; set '+f.hint:'&#10007; not set'}</span>
      </div>
      <div class="flex">
        <input id="env_${i}" data-env="${f.env}" type="password" autocomplete="off" spellcheck="false"
          placeholder="${f.set?'leave blank to keep the current key':f.placeholder}">
        <a class="btn-secondary btn-sm" href="${f.help_url}" target="_blank" rel="noopener noreferrer">Get a key</a>
        ${f.set?`<button class="btn-danger btn-sm" onclick="removeEnvKey('${f.env}')">Remove</button>`:''}
      </div>
    </div>`).join('');
  ['envFields','envFieldsMain'].forEach(id=>{const el=$(id); if(el)el.innerHTML=html;});
}
async function removeEnvKey(env){
  const field=ENV_FIELDS.find(f=>f.env===env);
  if(!confirm('Remove the '+(field?field.label:env)+' key from .env? Runs using it will fail until you add it back.'))return;
  const r=await api('/api/env/remove','POST',{env});
  if(!r.ok){toast('Could not remove key: '+(r.error||'unknown error'),'err');return;}
  toast((field?field.label:env)+' key removed','ok');
  await loadEnvStatus();
}
function renderProviderDashboards(){
  const el=$('providerDashboards');
  if(!el)return;
  el.innerHTML=ENV_FIELDS.map(f=>`
    <div class="provider-row">
      <div>
        <div>${f.label}</div>
        <div class="env-hint${f.set?' set':' unset'}">${f.set?'&#10003; set '+f.hint:'&#10007; not set'}</div>
      </div>
      <a class="btn-secondary btn-sm" href="${f.dashboard_url}" target="_blank" rel="noopener noreferrer">Open dashboard &#8594;</a>
    </div>`).join('');
}
async function continueToApp(){
  const body={};
  document.querySelectorAll('#envFields input[data-env]').forEach(inp=>{
    if(inp.value.trim())body[inp.dataset.env]=inp.value.trim();
  });
  if(Object.keys(body).length){
    const r=await api('/api/env/save','POST',body);
    if(!r.ok){toast('Could not save keys: '+(r.error||'unknown error'),'err');return;}
    toast((r.saved.length>1?'API keys':'API key')+' saved to .env','ok');
    await loadEnvStatus();
  }
  $('welcome').classList.add('hidden');
  $('app').classList.remove('hidden');
  go('configs');
}
function showWelcome(){
  $('app').classList.add('hidden');
  $('welcome').classList.remove('hidden');
  $('welcome').scrollTop=0;
  loadEnvStatus();
}

// ---------- boot ----------
(async()=>{META=await api('/api/meta');renderPalette();loadConfigs();loadEnvStatus();pollTerminal();pollRunStatus();
  PFCFG.models=[pfDefaultModel()];pfRenderModels();pfLoadRuns();pfPollStatus();})();
</script>
</body></html>
"""