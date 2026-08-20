"""llmits.studio.ui - the single-page app served by server.py (HTML/CSS/JS).

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
<link rel="shortcut icon" href="/favicon.ico"/>
<link rel="apple-touch-icon" href="/api/logo.png"/>
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
     server.py's ConsoleLog / _install_console_capture), not a separate
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
  .model.drag-over{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent) inset}
  .model.dragging{opacity:.4}
  .model-drag-handle{cursor:grab;user-select:none;color:var(--muted);font-size:16px;line-height:1;padding:0 2px;touch-action:none}
  .model-drag-handle:active{cursor:grabbing}

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

  /* Clears the collapsed terminal bar along the bottom edge - error toasts
     now wait to be dismissed, so they must not sit half-hidden behind it. */
  #toasts{position:fixed;right:var(--s6);bottom:calc(42px + var(--s4));z-index:50;
    display:flex;flex-direction:column;gap:var(--s2)}
  .toast{background:var(--raised);border:1px solid var(--line2);border-left:3px solid var(--accent);
    border-radius:var(--radius);padding:var(--s3) var(--s4);font-size:13.5px;box-shadow:var(--shadow);
    max-width:340px;animation:slidein .18s ease;cursor:pointer}
  .toast.ok{border-left-color:var(--ok)}
  .toast.err{border-left-color:var(--danger);position:relative;padding-right:var(--s6);white-space:pre-line}
  .toast-x{position:absolute;top:2px;right:8px;font-size:16px;line-height:1;color:var(--muted)}
  @keyframes slidein{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

  /* Paper folding: what a save will do, and what each model already has */
  #pfNameHint{margin-top:calc(-1 * var(--s2))}
  .pf-hint-warn{color:var(--danger)}
  .model .trials-pill{font:11px var(--mono);color:var(--muted);border:1px solid var(--line2);
    border-radius:999px;padding:1px 7px}

  /* ---- Compare tab ----------------------------------------------------
     Its own vocabulary, because it is the one page whose job is difference
     rather than value: --up/--down are "the measure moved the way you wanted"
     and "it didn't", never literally up and down, so accuracy rising and
     tokens rising can be colored honestly by the same two tokens. */
  #tab-compare{--up:#3fb27f; --down:#e0716b; --flat:var(--muted)}
  .cmp-runs{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:var(--s3)}
  .cmp-run{display:flex;gap:var(--s3);align-items:flex-start;background:var(--raised);
    border:1px solid var(--line);border-radius:var(--radius-lg);padding:var(--s3) var(--s4);
    cursor:pointer;transition:border-color .12s,background .12s}
  .cmp-run:hover{border-color:var(--line2)}
  .cmp-run.on{border-color:var(--accent);background:rgba(232,134,60,.08)}
  .cmp-run input{width:18px;height:18px;min-height:0;margin-top:3px;flex-shrink:0;accent-color:var(--accent)}
  .cmp-run .n{font-weight:600;font-size:14px;word-break:break-word}
  .cmp-run .m{color:var(--muted);font-size:12px;margin-top:3px;font-family:var(--mono)}
  .cmp-run .labels{color:var(--faint);font-size:11.5px;margin-top:5px;line-height:1.45;
    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}

  /* Headline cards: one per non-baseline run, each answering "what did this
     wording do" in the three measures at once. */
  .cmp-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:var(--s3)}
  .cmp-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius-lg);
    padding:var(--s4);border-top:3px solid var(--line2)}
  .cmp-card.base{border-top-color:var(--faint)}
  .cmp-card .t{font-weight:600;font-size:14px;word-break:break-word;min-height:38px}
  .cmp-card .kindpill{margin-top:var(--s2)}
  .cmp-card .metrics{display:flex;flex-direction:column;gap:6px;margin-top:var(--s3)}
  .cmp-card .metric{display:flex;justify-content:space-between;align-items:baseline;gap:var(--s2);
    font-family:var(--mono);font-size:13px}
  .cmp-card .metric .k{color:var(--muted);font-size:11.5px;font-family:var(--ui)}
  .cmp-card .metric .d{font-size:12px;font-weight:600}
  .up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--flat)}

  /* Tables (summary + per-model matrix) share one look: sticky header, sticky
     first column, and horizontal scroll inside the card rather than across the
     page - seventeen models by six runs does not fit any screen. */
  .cmp-scroll{overflow:auto;max-height:70vh;border:1px solid var(--line);border-radius:var(--radius)}
  table.cmp{border-collapse:separate;border-spacing:0;width:100%;font-size:13px}
  table.cmp th,table.cmp td{padding:7px 10px;text-align:right;white-space:nowrap;
    border-bottom:1px solid var(--line)}
  table.cmp th{background:var(--raised);color:var(--muted);font:600 11.5px var(--ui);
    text-transform:uppercase;letter-spacing:.04em;position:sticky;top:0;z-index:2;
    border-bottom:1px solid var(--line2);cursor:pointer;user-select:none}
  table.cmp th:hover{color:var(--text)}
  table.cmp th.nosort{cursor:default}
  table.cmp th.sorted::after{content:' \25BC';font-size:9px}
  table.cmp th.sorted.asc::after{content:' \25B2'}
  table.cmp td.name,table.cmp th.name{text-align:left;position:sticky;left:0;background:var(--surface);
    z-index:1;font-family:var(--mono);font-size:12px;max-width:260px;overflow:hidden;
    text-overflow:ellipsis}
  table.cmp th.name{background:var(--raised);z-index:3}
  table.cmp tbody tr:hover td{background:#1c212a}
  table.cmp tbody tr:hover td.name{background:#1c212a}
  table.cmp td.base{box-shadow:inset 2px 0 0 var(--faint)}
  table.cmp .sub-v{color:var(--faint);font-size:11px;font-family:var(--mono)}
  /* Heat cells: the color carries the shape of the grid, the number carries the
     value - never only one of the two, so the matrix stays readable to anyone
     who can't separate the reds from the greens. */
  .heat{font-family:var(--mono);font-weight:600}
  .cmp-legend{display:flex;gap:var(--s4);flex-wrap:wrap;align-items:center;
    color:var(--muted);font-size:12px;margin-top:var(--s3)}
  .cmp-legend .swatches{display:flex;gap:2px}
  .cmp-legend .sw{width:22px;height:12px;border-radius:2px}

  /* Findings: the page's written half. Each one is a claim with its evidence,
     colored only by which way the measure moved. */
  .finding{border:1px solid var(--line);border-left:3px solid var(--line2);border-radius:var(--radius);
    padding:var(--s3) var(--s4);margin-bottom:var(--s2);background:var(--raised)}
  .finding.good{border-left-color:var(--up)}
  .finding.bad{border-left-color:var(--down)}
  .finding.warn{border-left-color:var(--accent)}
  .finding.note{border-left-color:var(--info)}
  .finding .ft{font-weight:600;font-size:14px;margin-bottom:3px}
  .finding .fx{color:var(--muted);font-size:13px;line-height:1.5}
  /* ---- Confusion tab ---------------------------------------------------
     One kind of object on this page: the matrix. It carries three numbers per
     cell - the share of its row, the count behind that share, and whether the
     cell is on the diagonal - and the column marginal underneath, which is
     where a bias actually reads: how often a letter was given as the answer
     against how often it was the right one. */
  #tab-confusion{--over:#e0716b; --under:#5b9bd5; --flat:var(--muted)}
  .cfm-level{margin-bottom:var(--s6)}
  .cfm-level>.lt{font-weight:600;font-size:15px;margin-bottom:4px}
  .cfm-level>.lc{color:var(--muted);font-size:12.5px;line-height:1.55;max-width:840px;
    margin-bottom:var(--s4)}
  .cfm-matrix{margin-bottom:var(--s6);padding-bottom:var(--s4);border-bottom:1px solid var(--line)}
  .cfm-matrix:last-child{border-bottom:0;margin-bottom:0}
  .cfm-matrix .mt{font-weight:600;font-size:14px}
  .cfm-matrix .ms{color:var(--muted);font-size:12px;font-family:var(--mono);margin:3px 0 var(--s3)}
  /* The one-sentence reading of the matrix, coloured by what it found. */
  .cfm-verdict{border-left:3px solid var(--line2);padding:6px var(--s3);margin-top:var(--s3);
    color:var(--muted);font-size:12.5px;line-height:1.55;background:var(--raised);
    border-radius:0 var(--radius) var(--radius) 0;max-width:840px}
  .cfm-verdict.leaning{border-left-color:var(--over);color:var(--text)}
  .cfm-verdict.unsettled{border-left-color:var(--accent)}
  .cfm-verdict.chance{border-left-color:var(--accent)}
  .cfm-verdict.even{border-left-color:#3fb27f}
  /* Axis captions in two parts, exactly as the charts do it: what the axis is,
     then a short line saying what that means in the puzzle. */
  .cfm-axis{color:var(--muted);font-size:12px;margin-bottom:var(--s3);line-height:1.5}
  .cfm-axis b{color:var(--text);font-weight:600}
  .cfm-axis .ax{display:block}
  .cfm-ycap{writing-mode:vertical-rl;transform:rotate(180deg);text-align:center;
    padding:0 6px 0 0;white-space:nowrap;color:var(--muted);font-size:11.5px;line-height:1.45}
  .cfm-ycap b{color:var(--text);font-weight:600;font-size:12.5px}
  .cfm-wrap{display:flex;align-items:stretch;gap:2px}
  .cfm-xcap{text-align:center;color:var(--muted);font-size:11.5px;margin-top:var(--s2);
    line-height:1.45}
  .cfm-xcap b{display:block;color:var(--text);font-weight:600;font-size:12.5px}
  table.cfm{border-collapse:separate;border-spacing:0;width:auto;font-size:12.5px}
  table.cfm th,table.cfm td{padding:6px 9px;text-align:center;white-space:nowrap;
    border-bottom:1px solid var(--line);min-width:70px}
  table.cfm td.cell{width:82px;font-family:var(--mono);font-weight:600;line-height:1.25}
  table.cfm th{background:var(--raised);color:var(--muted);font:600 12px var(--ui);
    border-bottom:1px solid var(--line2)}
  table.cfm td.name,table.cfm th.name{text-align:right;font-family:var(--mono);
    font-size:11.5px;color:var(--muted);min-width:0;padding-right:var(--s3)}
  table.cfm td.name b{color:var(--text);font-size:14px;font-weight:700}
  table.cfm td .n{display:block;font-weight:400;font-size:10.5px;color:var(--muted);margin-top:1px}
  table.cfm td.diag{box-shadow:inset 0 0 0 2px #2e8b57}
  /* The column marginal: the same three lines the charts print under the grid. */
  table.cfm tr.marg td{border-bottom:0;padding-top:3px;padding-bottom:3px;
    font-family:var(--mono);font-size:11.5px;color:var(--muted)}
  table.cfm tr.marg.first td{border-top:1px solid var(--line2);padding-top:var(--s2)}
  table.cfm tr.marg td.given{color:var(--text)}
  table.cfm tr.marg td.gap.over{color:var(--over);font-weight:700}
  table.cfm tr.marg td.gap.under{color:var(--under);font-weight:700}
  table.cfm tr.marg td.name{text-align:right;color:var(--faint);font-size:11px}
  .cfm-plots>figure{margin:0 0 var(--s6);text-align:center}
  .cfm-plots figcaption{color:var(--muted);font-size:12.5px;margin-top:var(--s2);
    max-width:760px;margin-left:auto;margin-right:auto;line-height:1.5}

  .cmp-plots>figure{margin:0 0 var(--s6);text-align:center}
  .cmp-plots figcaption{color:var(--muted);font-size:12.5px;margin-top:var(--s2);
    max-width:760px;margin-left:auto;margin-right:auto;line-height:1.5}

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
     straight to a local .env - see /api/env/save in server.py). -->
<div id="welcome">
  <div class="welcome-appbar">
    <div class="brand"><img class="mark" src="/api/logo.png" alt=""/><span>Pyllmits</span></div>
    <div class="welcome-appbar-links">
      <a class="appbar-icon-btn" href="https://github.com/rjvb7424/pyllmits" target="_blank" rel="noopener noreferrer" aria-label="GitHub repository" title="GitHub">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>
      </a>
      <a class="appbar-icon-btn" href="https://colab.research.google.com/drive/1FRfuSSkJzP3bWz3_0Yi2PcraNPBK10_J?usp=sharing" target="_blank" rel="noopener noreferrer" aria-label="User guide and documentation on Google Colab" title="User guide (Colab)">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="#F9AB00"><path d="M16.9414 4.9757a7.033 7.033 0 0 0-4.9308 2.0646 7.033 7.033 0 0 0-.1232 9.8068l2.395-2.395a3.6455 3.6455 0 0 1 5.1497-5.1478l2.397-2.3989a7.033 7.033 0 0 0-4.8877-1.9297zM7.07 4.9855a7.033 7.033 0 0 0-4.8878 1.9316l2.3911 2.3911a3.6434 3.6434 0 0 1 5.0227.1271l1.7341-2.9737-.0997-.0802A7.033 7.033 0 0 0 7.07 4.9855zm15.0093 2.1721l-2.3892 2.3911a3.6455 3.6455 0 0 1-5.1497 5.1497l-2.4067 2.4068a7.0362 7.0362 0 0 0 9.9456-9.9476zM1.932 7.1674a7.033 7.033 0 0 0-.002 9.6816l2.397-2.397a3.6434 3.6434 0 0 1-.004-4.8916zm7.664 7.4235c-1.38 1.3816-3.5863 1.411-5.0168.1134l-2.397 2.395c2.4693 2.3328 6.263 2.5753 9.0072.5455l.1368-.1115z"/></svg>
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

    <p class="welcome-desc">
      Pyllmits tests whether AI models can actually do spatial reasoning, using two very
      different challenges: <b>Crafter</b> - a hand-built 2D survival world the model must
      navigate, gather resources, and complete an objective in, using nothing but a text
      description of what it sees each turn - and <b>Paper Folding</b> - a classic spatial
      puzzle: fold a grid, punch a hole, and ask the model which of five unfolded results
      matches. Both experiments run through this same interface, so testing OpenAI, Gemini,
      and Hugging Face models side by side is just a matter of adding them to the same run.
    </p>

    <div class="card">
      <h3><span class="python-logo" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="#F9AB00"><path d="M16.9414 4.9757a7.033 7.033 0 0 0-4.9308 2.0646 7.033 7.033 0 0 0-.1232 9.8068l2.395-2.395a3.6455 3.6455 0 0 1 5.1497-5.1478l2.397-2.3989a7.033 7.033 0 0 0-4.8877-1.9297zM7.07 4.9855a7.033 7.033 0 0 0-4.8878 1.9316l2.3911 2.3911a3.6434 3.6434 0 0 1 5.0227.1271l1.7341-2.9737-.0997-.0802A7.033 7.033 0 0 0 7.07 4.9855zm15.0093 2.1721l-2.3892 2.3911a3.6455 3.6455 0 0 1-5.1497 5.1497l-2.4067 2.4068a7.0362 7.0362 0 0 0 9.9456-9.9476zM1.932 7.1674a7.033 7.033 0 0 0-.002 9.6816l2.397-2.397a3.6434 3.6434 0 0 1-.004-4.8916zm7.664 7.4235c-1.38 1.3816-3.5863 1.411-5.0168.1134l-2.397 2.395c2.4693 2.3328 6.263 2.5753 9.0072.5455l.1368-.1115z"/></svg></span>User guide &amp; documentation</h3>
      <div class="sub" style="margin-bottom:var(--s4)">
        New to Pyllmits? The interactive Google Colab notebook is the full user guide - it
        walks you through this Studio step by step, from setup to reading your first results.
      </div>
      <div class="pypi-row" style="flex-wrap:nowrap">
        <!-- flex-shrink + ellipsis (instead of the row's usual wrap) so the
             long Colab URL gives way and the button stays on the same row,
             matching the PyPI and GitHub cards. -->
        <pre style="flex:0 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis">colab.research.google.com/drive/1FRfuSSkJzP3bWz3_0Yi2PcraNPBK10_J</pre>
        <a class="btn-primary btn-sm" href="https://colab.research.google.com/drive/1FRfuSSkJzP3bWz3_0Yi2PcraNPBK10_J?usp=sharing" target="_blank" rel="noopener noreferrer" style="flex-shrink:0">Open in Colab &#8594;</a>
      </div>
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
      First things first: add API keys for the providers whose models you actually want to
      test - you don't need all three. Keys are saved locally and never shown back to you in
      plain text, and you can add, remove, or check them at any point later from the
      <b>Providers</b> page, without restarting anything.
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
    <button class="tab" data-tab="compare" role="tab">Compare</button>
    <button class="tab" data-tab="confusion" role="tab">Confusion</button>
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
        <button class="btn-primary" id="runStartBtn" onclick="runStart()">&#9654;&nbsp;Start</button>
        <button class="btn-secondary" id="runPauseBtn" onclick="runPause()">&#10073;&#10073;&nbsp;Pause</button>
        <button class="btn-danger" id="runStopBtn" onclick="runStop()">&#9632;&nbsp;Stop</button>
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
      <div class="flex" style="align-items:center">
        <select id="pfSetupPick" onchange="pfPickSetupRun(this.value)" style="flex:1;text-overflow:ellipsis">
          <option value="">-- start a new run --</option>
        </select>
        <button class="btn-secondary btn-sm" style="padding:0 var(--s4)" onclick="pfDuplicateSetup()" title="Copy the setup below (trials, folds, direction mode, model list) into a new run name - no trial data carries over, and nothing is written until you Save setup or Start">Duplicate</button>
        <button class="btn-secondary btn-sm" style="padding:0 var(--s4)" onclick="pfSaveSetup()" title="Save this setup to disk without running any trials - handy for reserving a name and model list you'll come back to">Save setup</button>
        <button class="btn-danger btn-sm" style="padding:0 var(--s4)" onclick="pfDeleteRun('pfSetupPick')">Delete</button>
        <span class="pill danger hidden" id="pfDirty" title="You have changes that haven't been saved yet">&#9679; Unsaved changes</span>
      </div>

      <div id="pfSetupFields">
        <div class="row" style="margin-top:var(--s4)">
          <div><label for="pf_name">Run name</label><input id="pf_name" placeholder="my_paperfold_run" oninput="pfUpdateNameHint()"></div>
          <div><label for="pf_trials">Trials per fold count</label><input id="pf_trials" type="number" min="1" value="30" oninput="pfUpdateFoldHint()"></div>
          <div><label for="pf_folds_min">Folds from</label><input id="pf_folds_min" type="number" min="1" max="8" value="3" oninput="pfUpdateFoldHint()"></div>
          <div><label for="pf_folds_max">Folds to</label><input id="pf_folds_max" type="number" min="1" max="8" value="3" oninput="pfUpdateFoldHint()"></div>
        </div>
        <div id="pfNameHint" class="hidden"></div>
        <!-- Says what the fold range adds up to: how many puzzles per model,
             and how big the paper gets at each end of the range. -->
        <div id="pfFoldHint" class="sub" style="margin-top:var(--s2)"></div>

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
    </div>

    <div class="card"><h3>Run</h3>
      <div class="flex" style="margin-bottom:var(--s4)">
        <button class="btn-primary" id="pfStartBtn" onclick="pfRunStart()">&#9654;&nbsp;Start</button>
        <button class="btn-secondary" id="pfPauseBtn" onclick="pfRunPause()">&#10073;&#10073;&nbsp;Pause</button>
        <button class="btn-danger" id="pfStopBtn" onclick="pfRunStop()">&#9632;&nbsp;Stop</button>
      </div>
      <div class="live-chips">
        <div class="chip"><div class="k">State</div><div class="v" id="pfState">idle</div></div>
        <div class="chip"><div class="k">Model</div><div class="v" id="pfModel">&ndash;</div></div>
        <div class="chip"><div class="k">Trial</div><div class="v" id="pfTrial">&ndash;</div></div>
        <div class="chip"><div class="k">Folds</div><div class="v" id="pfFolds">&ndash;</div></div>
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
          <button class="btn-secondary" id="pfDownloadAllBtn" onclick="pfDownloadAllGraphs()" disabled
            title="Saves every graph into one folder in your Downloads, named after the run">Download all</button>
          <button class="btn-danger" onclick="pfDeleteRun('pfRunPick')">Delete run</button>
        </div>
      </div>
      <div id="pfPlots"></div>
    </div>
  </section>

  <!-- COMPARE - paper-folding runs against each other. Every other tab looks
       inside one experiment; this one looks between them, which is where the
       actual research question lives: the puzzle never changes, only what the
       four directions are called, so the gap between two runs is the finding. -->
  <section id="tab-compare" class="hidden">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Compare</h2><div class="sub">Put paper-folding runs side by side: accuracy, token spend and thinking time, per run and per model. Pick two or more runs, choose which one is the baseline, and everything below is measured against it.</div></div>
    </div>

    <div class="card"><h3>Runs to compare</h3>
      <div class="sub" style="margin-bottom:var(--s4)">Tick the runs you want on the page. The order you tick them in is the order every chart reads, left to right.</div>
      <div class="flex" style="margin-bottom:var(--s3)">
        <button class="btn-secondary btn-sm" onclick="cmpSelectAll(true)">Select all</button>
        <button class="btn-secondary btn-sm" onclick="cmpSelectAll(false)">Clear</button>
        <span class="pill" id="cmpCount">0 selected</span>
      </div>
      <div id="cmpRunList"></div>

      <div class="row" style="margin-top:var(--s4);max-width:840px">
        <div>
          <label for="cmpBaseline">Baseline (everything is measured against this run)</label>
          <select id="cmpBaseline" onchange="cmpMaybeRerun()"></select>
        </div>
        <div>
          <label for="cmpRestrict">Scope</label>
          <select id="cmpRestrict" onchange="cmpMaybeRerun()">
            <option value="1">Compare like for like (only shared models and folds)</option>
            <option value="0">Use everything each run has</option>
          </select>
        </div>
      </div>
      <div class="sub" id="cmpScopeHint">Like for like trims every run to the models and fold counts they all have in common, so a run that stopped early - or one that swept extra folds - can't tilt the comparison with a different mixture underneath it.</div>

      <div class="flex" style="margin-top:var(--s4)">
        <button class="btn-primary" id="cmpRunBtn" onclick="cmpRun()">&#8635;&nbsp;Compare</button>
        <button class="btn-secondary" id="cmpCsvBtn" onclick="cmpDownloadCsv()" disabled
          title="Every number on this page as a CSV: one row per model per run, plus the run totals">Download CSV</button>
        <button class="btn-secondary" id="cmpDownloadAllBtn" onclick="cmpDownloadAllGraphs()" disabled
          title="Saves every comparison chart into one folder in your Downloads">Download all charts</button>
      </div>
    </div>

    <div id="cmpBody"></div>
  </section>

  <!-- CONFUSION - one experiment, nothing but confusion matrices. Accuracy
       cannot tell a model that reasoned and got unlucky from one that answered
       "C" to everything; a grid that keeps what was asked and what was answered
       on separate axes can, and that is the only thing this page shows. -->
  <section id="tab-confusion" class="hidden">
    <div class="between" style="margin-bottom:var(--s4)">
      <div><h2>Confusion</h2><div class="sub">Pick one experiment and read its confusion matrices: everyone together, then each provider family, then each model on its own. Rows are what the answer actually was, columns are what the model said, and the diagonal is where they agree &mdash; so an error stops being a tally and becomes a shape.</div></div>
    </div>

    <div class="card"><h3>Experiment</h3>
      <div class="sub" style="margin-bottom:var(--s3)">One run at a time. Every matrix below is built from this run and nothing else.</div>
      <div class="flex" style="align-items:flex-end">
        <div style="flex:1;min-width:0">
          <label for="cfmRun">Which experiment</label>
          <select id="cfmRun" onchange="cfmRun()" style="width:100%;text-overflow:ellipsis"></select>
        </div>
        <button class="btn-secondary" id="cfmCsvBtn" onclick="cfmDownloadCsv()" disabled
          title="Every cell of every matrix as one CSV: the count, the share of its row, and the column marginals underneath">Download CSV</button>
        <button class="btn-secondary" id="cfmDownloadAllBtn" onclick="cfmDownloadAllGraphs()" disabled
          title="Saves every matrix into one folder in your Downloads">Download all</button>
      </div>
      <div class="sub" id="cfmRunHint"></div>
    </div>

    <div id="cfmBody"></div>
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
      <button class="btn-ghost btn-sm" id="termClear" onclick="clearTerminal()"
        title="Clear the lines shown here - output from this point on still appears">Clear</button>
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
// Errors explain why something didn't happen and are often several lines long
// (name clashes, "stop the run first", config-mismatch refusals) - they stay
// until dismissed rather than sliding away in 3.2s, which is how a refused
// save reads as "it just silently didn't save". Successes still auto-dismiss.
function toast(msg,kind){const t=document.createElement('div');t.className='toast'+(kind?' '+kind:'');
  t.textContent=msg;
  if(kind=='err'){const x=document.createElement('span');x.className='toast-x';x.textContent='×';
    x.title='Dismiss';t.appendChild(x);t.title='Click to dismiss';
    // Since these wait to be dismissed, keep only the most recent few rather
    // than letting a burst of failures climb off the top of the screen.
    const open=$('toasts').querySelectorAll('.toast.err');
    for(let i=0;i<=open.length-3;i++)open[i].remove();}
  t.onclick=()=>t.remove();
  $('toasts').appendChild(t);
  if(kind!='err')setTimeout(()=>t.remove(),3200);}
function go(t){document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.dataset.tab==t));
  ['configs','editor','run','graphs','videos','paperfold','compare','confusion','providers'].forEach(s=>$('tab-'+s).classList.toggle('hidden',s!=t));
  if(t=='configs')loadConfigs(); if(t=='graphs')loadRuns(); if(t=='videos')loadRuns(); if(t=='run')loadRunConfigs();
  if(t=='providers')loadEnvStatus(); if(t=='paperfold')pfLoadRuns(); if(t=='compare')cmpLoadRuns();
  if(t=='confusion')cfmLoadRuns();}
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
// OpenAIModel._is_reasoning_model in llmits/models/openai_api.py, so the editor
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
let RUNPATH=null, lastRunState=null, lvFrameKey=null;
async function loadRunConfigs(){const r=await api('/api/configs');
  const sel=$('runConfigPick');
  sel.innerHTML='<option value="">-- select a config --</option>'+
    (r.configs||[]).map(c=>`<option value="${c.path}" ${c.path==RUNPATH?'selected':''}>${c.name||c.path}</option>`).join('');
}
function pickRunConfig(path){RUNPATH=path||null;}
function selectRun(path){RUNPATH=path;go('run');}
// Three buttons, no more: Start, Pause, Stop. Start doubles as Resume - a
// paused run continues from exactly where it stopped instead of starting the
// config over, which is what pressing "play" on a paused thing should do.
// syncRunButtons() keeps the trio honest about which one is live right now.
async function runStart(){
  if((LAST_CRAFTER_STATUS.state||'idle')=='paused'){
    await api('/api/run/resume','POST');toast('Continuing','ok');return;}
  if(!RUNPATH){toast('Pick a config to run first','err');return;}
  const r=await api('/api/run/start','POST',{path:RUNPATH});
  if(!r.ok){toast(r.error,'err');return;}
  toast('Experiment started','ok');}
function runPause(){api('/api/run/pause','POST');toast('Paused \u2014 press Start to continue','ok');}
function runStop(){api('/api/run/stop','POST');toast('Stopping\u2026');}

// Start is meaningless while a run is going, Pause only applies to a running
// one, and Stop needs something to stop - so each button says so rather than
// firing a request the server will just refuse. Start says "Continue" while
// paused, so the doubled-up behaviour is visible before you press it.
function syncRunButtons(ids,s){
  const st=s.state||'idle', paused=st=='paused', stopping=st=='stopping';
  const start=$(ids.start);
  start.innerHTML=paused?'&#9654;&nbsp;Continue':'&#9654;&nbsp;Start';
  start.disabled=!!s.running&&!paused;
  $(ids.pause).disabled=!(st=='running'&&s.running);
  $(ids.stop).disabled=!s.running||stopping;
}

// ---------- Header status dot (reflects Crafter AND Paper Folding - whichever
// is more "active" drives the dot's colour/label; the detail line shows both
// at once if both happen to be running/paused, since they're fully
// independent and can be going simultaneously) ----------
let LAST_CRAFTER_STATUS={state:'idle'}, LAST_PAPERFOLD_STATUS={state:'idle'};
const STATUS_RANK={running:0,stopping:0,paused:1,error:2,stopped:3,finished:4,idle:5};
function oneStatusMeta(s){
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
  const cMeta=oneStatusMeta(c), pMeta=oneStatusMeta(p);
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
  syncRunButtons({start:'runStartBtn',pause:'runPauseBtn',stop:'runStopBtn'},s);
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
// Saves each URL through the browser's own download machinery: a temporary
// <a> click per file, staggered so the browser registers every one. With more
// than one URL the browser may, on first use, ask permission to download
// multiple files.
async function triggerDownloads(urls){
  for(const u of urls){
    const a=document.createElement('a');
    a.href=u; a.download='';
    document.body.appendChild(a); a.click(); a.remove();
    await new Promise(res=>setTimeout(res,300));
  }
}
// Download-all: regenerate the graphs so they're current, then download each
// PNG separately - the plots land in Downloads as plain image files, named
// after their run. (The paper-folding side collects them into one folder
// instead, see pfDownloadAllGraphs.)
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
    toast(`Downloading ${r.plots.length} graphs\u2026`,'ok');
    await triggerDownloads(r.plots.map(f=>
      '/api/plot?run='+encodeURIComponent(name)+'&file='+encodeURIComponent(f)+'&download=1'));
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

// ---------- Paper folding: unsaved-changes tracking ----------
// Same idea as Crafter's DIRTY/markDirty/clearDirty (edDirty pill), scoped to
// just the Setup fields (not the picker/buttons above them, or the Run/Graphs
// cards) via event delegation on #pfSetupFields, so picking a different run
// from the dropdown doesn't itself count as "you made a change".
// PF_LOADED_NAME is the run this form was loaded from - null means "saving
// creates a new run". PF_TRIALS is {model name: trials already recorded} for
// that run, so the model cards can show what's on disk and Remove can warn
// before a save throws those trials away.
let PF_DIRTY=false, PF_LOADED_NAME=null, PF_TRIALS={};
function pfMarkDirty(){PF_DIRTY=true;$('pfDirty').classList.remove('hidden');}
function pfClearDirty(){PF_DIRTY=false;$('pfDirty').classList.add('hidden');}
document.getElementById('pfSetupFields').addEventListener('input',pfMarkDirty);
document.getElementById('pfSetupFields').addEventListener('change',pfMarkDirty);

// Says up front what pressing Save setup / Start will do to disk - creating a
// run, renaming one, or continuing one - so a name clash is visible while
// you're typing instead of only as a refusal after you press Save.
function pfUpdateNameHint(){
  const el=$('pfNameHint'); if(!el)return;
  const name=($('pf_name').value||'').trim();
  const exists=(window._pfRuns||[]).some(r=>r.name==name);
  let msg='', cls='sub';
  if(!name){msg='';}
  else if(PF_LOADED_NAME==name){msg=`Saving updates the existing run '${name}'.`;}
  else if(PF_LOADED_NAME&&!exists){msg=`Saving renames '${PF_LOADED_NAME}' to '${name}' (its results move with it).`;}
  else if(exists){msg=`A run named '${name}' already exists - saving will be refused. Pick it from the dropdown above to continue it, or choose another name.`;cls='sub pf-hint-warn';}
  else{msg=`Saving creates a new run named '${name}'.`;}
  el.textContent=msg; el.className=msg?cls:'hidden';
}

// ---------- Paper folding: the fold range ----------
// A run can test one fold count (from == to, the classic setup) or a whole
// increasing range: "Trials per fold count" puzzles at 3 folds, then the same
// number at 4, at 5, ... Every trial records the fold count it was answered
// at, and the accuracy-by-folds graph plots them as a difficulty curve.
//
// Paper size follows the fold count instead of being a fixed 16x16: each fold
// halves one side, so a 6-fold puzzle needs a far bigger sheet than a 2-fold
// one or the last folds would have nothing left to halve. The formula mirrors
// paperfold.cognitive_test.paper_size_for_folds - folds are split across both
// axes, so the sheet doubles every second fold. PF_MAX_FOLDS mirrors
// studio.server.MAX_FOLDS; the server re-validates either way, this just
// keeps the field from offering something it would refuse.
const PF_MAX_FOLDS=8, PF_MIN_FOLDED_SIDE=4;
function pfPaperSide(folds){return PF_MIN_FOLDED_SIDE*Math.pow(2,Math.ceil(folds/2));}
function pfPaperLabel(folds){const s=pfPaperSide(folds);return s+'x'+s;}
function pfFoldRange(){
  const lo=Math.max(1,+$('pf_folds_min').value||1);
  const hi=Math.max(1,+$('pf_folds_max').value||1);
  return {lo,hi};
}
function pfUpdateFoldHint(){
  const el=$('pfFoldHint'); if(!el)return;
  const {lo,hi}=pfFoldRange(), per=Math.max(1,+$('pf_trials').value||1);
  if(hi<lo){el.textContent=`'Folds to' (${hi}) is below 'Folds from' (${lo}) - a run folds from fewer to more.`;
    el.className='sub pf-hint-warn';return;}
  if(hi>PF_MAX_FOLDS){el.textContent=`At most ${PF_MAX_FOLDS} folds - past that the paper, and the prompt carrying six copies of it, gets impractically large.`;
    el.className='sub pf-hint-warn';return;}
  el.className='sub';
  if(lo==hi){el.textContent=`${per} puzzles per model, all at ${lo} fold${lo==1?'':'s'} on a ${pfPaperLabel(lo)} paper. `
    +`Raise 'Folds to' to sweep a range instead and get the accuracy-vs-folds curve.`;return;}
  const counts=[];for(let f=lo;f<=hi;f++)counts.push(f);
  el.textContent=`${per} puzzles at each of ${counts.join(', ')} folds = ${per*counts.length} per model. `
    +`The paper grows with the folds, ${pfPaperLabel(lo)} at ${lo} up to ${pfPaperLabel(hi)} at ${hi}, `
    +`so the later trials send much longer prompts. Graphed as accuracy by number of folds.`;
}

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
  <div class="model" data-index="${i}"
       ondragover="pfDragOver(event,${i})" ondragleave="pfDragLeave(event)" ondrop="pfDrop(event,${i})">
    <div class="between" style="margin-bottom:var(--s2)">
      <div class="flex" style="gap:var(--s2)">
        <span class="model-drag-handle" draggable="true" title="Drag to reorder - models run top to bottom"
              ondragstart="pfDragStart(event,${i})" ondragend="pfDragEnd(event)">&#9776;</span>
        <span class="muted" style="font:12px var(--mono)">#${i+1}</span>
        ${readyIcon}<b>${m.name||'model '+(i+1)}</b>
        ${pfTrialsOf(m.name)?`<span class="trials-pill" title="Already recorded in this run's results.json - removing this model discards them">${pfTrialsOf(m.name)} trials recorded</span>`:''}
      </div>
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
function pfTrialsOf(name){return (name&&PF_TRIALS[name])||0;}
function pfAddModel(){PFCFG.models.push(pfDefaultModel());pfRenderModels();pfMarkDirty();}
// Saving a setup rewrites results.json's model list to exactly what's in the
// form, so a model dropped here loses the trials it had already recorded -
// irreversibly, and only once you save. Say so before it happens rather than
// after.
function pfDelModel(i){
  const m=PFCFG.models[i]||{}, done=pfTrialsOf(m.name);
  if(done&&!confirm(`Remove ${m.name}?\n\nIt has ${done} recorded trial(s) in '${PF_LOADED_NAME}'. `
                    +`Saving or starting this setup afterwards permanently discards them.`))return;
  PFCFG.models.splice(i,1);pfRenderModels();pfMarkDirty();}

// ---------- Paper folding: reorder models by dragging ----------
// Models run top to bottom in this list order (PaperfoldRunner just iterates
// model_specs as given), so dragging a card up or down directly controls
// which model Start reaches first/last - no separate "run order" concept to
// keep in sync.
let PF_DRAG_INDEX=null;
function pfDragStart(e,i){
  PF_DRAG_INDEX=i;
  e.dataTransfer.effectAllowed='move';
  e.dataTransfer.setData('text/plain',String(i));
  const card=e.target.closest('.model');
  if(card){card.classList.add('dragging'); e.dataTransfer.setDragImage(card,20,20);}
}
function pfDragEnd(e){
  const card=e.target.closest('.model');
  if(card)card.classList.remove('dragging');
  document.querySelectorAll('#pfModels .model.drag-over').forEach(el=>el.classList.remove('drag-over'));
  PF_DRAG_INDEX=null;
}
function pfDragOver(e,i){
  if(PF_DRAG_INDEX===null||PF_DRAG_INDEX===i)return;
  e.preventDefault();
  e.dataTransfer.dropEffect='move';
  e.currentTarget.classList.add('drag-over');
}
function pfDragLeave(e){e.currentTarget.classList.remove('drag-over');}
function pfDrop(e,i){
  e.preventDefault();
  e.currentTarget.classList.remove('drag-over');
  if(PF_DRAG_INDEX===null||PF_DRAG_INDEX===i)return;
  const arr=PFCFG.models;
  const [moved]=arr.splice(PF_DRAG_INDEX,1);
  arr.splice(i,0,moved);
  PF_DRAG_INDEX=null;
  pfRenderModels();
  pfMarkDirty();
}

// ---------- Paper folding: run controls ----------
// Shared by Start and Save setup, so both send the exact same shape and
// validate the same way - the only difference is which route gets it.
function pfBuildRunBody(){
  const name=($('pf_name').value||'').trim();
  if(!name)return{error:'Enter a run name'};
  const models=PFCFG.models||[];
  if(!models.length)return{error:'Add at least one model (with a model id picked)'};
  // Switching a card's backend clears its model id on purpose (ids rarely
  // carry across providers). Those cards used to be filtered out here and
  // saved as if they'd never been added - say what's missing instead of
  // quietly dropping it.
  const blank=models.map((m,i)=>m.name?null:i+1).filter(n=>n);
  if(blank.length)return{error:`Pick a model id for card #${blank.join(', #')}, or remove it.`};
  const dupes=[...new Set(models.map(m=>m.name).filter((n,i,a)=>a.indexOf(n)!=i))];
  if(dupes.length)return{error:`${dupes.join(', ')} listed more than once - each model can only appear once in a run.`};
  const direction_mode=$('pf_dirmode').value;
  let direction_labels=null;
  if(direction_mode=='fixed'){
    direction_labels={north:$('pf_dir_north').value.trim(),south:$('pf_dir_south').value.trim(),
                       east:$('pf_dir_east').value.trim(),west:$('pf_dir_west').value.trim()};
    const vals=Object.values(direction_labels);
    if(vals.some(v=>!v))return{error:'Fill in all four direction placeholder names, or switch to Real/Random'};
    if(new Set(vals.map(v=>v.toLowerCase())).size<4)return{error:'Direction placeholder names must all be different'};
  }
  const {lo,hi}=pfFoldRange();
  if(hi<lo)return{error:`Fold range runs backwards: 'Folds to' (${hi}) is below 'Folds from' (${lo})`};
  if(hi>PF_MAX_FOLDS)return{error:`At most ${PF_MAX_FOLDS} folds - the paper (and the prompt) gets impractically large past that`};
  return{body:{name, num_trials:+$('pf_trials').value||30, fold_min:lo, fold_max:hi, models,
    direction_mode, direction_labels, old_name:PF_LOADED_NAME}};
}
let pfLastState=null;
// Both Start and Save setup land here once the server has accepted the setup:
// the form is now editing a real run under body.name, and every picker that
// might still be pointing at the name it had before a rename has to follow it.
async function pfAfterSaved(body){
  const renamedFrom=PF_LOADED_NAME&&PF_LOADED_NAME!=body.name?PF_LOADED_NAME:null;
  PF_LOADED_NAME=body.name;
  pfClearDirty();
  await pfLoadRuns();
  $('pfSetupPick').value=body.name;
  if(renamedFrom&&$('pfRunPick').value!=body.name&&
     !(window._pfRuns||[]).some(r=>r.name==$('pfRunPick').value)){
    $('pfRunPick').value=body.name; pfShowRun();
  }
  const run=(window._pfRuns||[]).find(r=>r.name==body.name);
  PF_TRIALS={}; ((run&&run.models)||[]).forEach(m=>{if(m.trials)PF_TRIALS[m.name]=m.trials;});
  pfRenderModels();
  pfUpdateNameHint();
}
// Start doubles as Resume here too: while paused it continues the run in
// flight rather than re-reading the Setup form, so edits made to the form
// mid-pause can't quietly restart the run under a different setup.
async function pfRunStart(){
  if((LAST_PAPERFOLD_STATUS.state||'idle')=='paused'){
    await api('/api/paperfold/run/resume','POST');toast('Continuing','ok');return;}
  const {body,error}=pfBuildRunBody();
  if(error){toast(error,'err');return;}
  const r=await api('/api/paperfold/run/start','POST',body);
  if(!r.ok){toast(r.error,'err');return;}
  toast('Paper-folding run started','ok');
  await pfAfterSaved(body);
}
function pfRunPause(){api('/api/paperfold/run/pause','POST');toast('Paused — press Start to continue','ok');}
function pfRunStop(){api('/api/paperfold/run/stop','POST');toast('Stopping…');}
// Writes the current Setup form to disk - no models built, no API calls - so
// a model list/config can be reserved and come back exactly as left, and so
// a run that later crashes partway through still has every configured model
// on record (not just the ones it got to before the crash). If the Run name
// field was edited since this setup was loaded (old_name != the new name),
// the server renames the run in place rather than leaving the old name
// behind as an orphan.
async function pfSaveSetup(){
  const {body,error}=pfBuildRunBody();
  if(error){toast(error,'err');return;}
  const r=await api('/api/paperfold/setup/save','POST',body);
  if(!r.ok){toast(r.error,'err');return;}
  toast('Saved '+body.name,'ok');
  await pfAfterSaved(body);
}
// Copies whatever is in the Setup form right now (including edits you haven't
// saved) into a new, unsaved run under a free "<name>_copy" name.
//
// Deliberately touches nothing on disk. This used to POST to the server, which
// wrote a real "<name>_copy" folder immediately - so every time you duplicated
// and then renamed before saving, or duplicated and changed your mind, a run
// you never asked for was left sitting in the list, and the next duplicate of
// the same source would collide with it and refuse the save. Now the copy only
// becomes a folder when you press Save setup or Start, under the name you
// actually chose.
function pfCopyName(base){
  const taken=new Set((window._pfRuns||[]).map(r=>r.name));
  let n=1, name=base+'_copy';
  while(taken.has(name)){n++; name=base+'_copy'+n;}
  return name;
}
function pfDuplicateSetup(){
  const base=($('pf_name').value||'').trim()||$('pfSetupPick').value;
  if(!base){toast('Nothing to duplicate - load a run, or fill in the setup first','err');return;}
  const name=pfCopyName(base);
  $('pf_name').value=name;
  // No longer editing the run it was copied from: a save must create this as a
  // new run, never rename or overwrite the original.
  PF_LOADED_NAME=null;
  PF_TRIALS={};           // a copy starts with no trial history of its own
  $('pfSetupPick').value='';
  pfRenderModels();
  pfUpdateNameHint();
  pfMarkDirty();
  toast(`Copied into a new setup named '${name}'. Rename it if you like, then Save setup or Start - nothing is written until you do.`,'ok');
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
  // Which rung of the fold range this trial is on, and the sheet that rung
  // uses - both change as a sweep works its way up.
  $('pfFolds').textContent=(s.model&&s.num_folds!=null)
    ?`${s.num_folds}${s.paper_size?' ('+s.paper_size+')':''}`:'–';
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
  syncRunButtons({start:'pfStartBtn',pause:'pfPauseBtn',stop:'pfStopBtn'},s);
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
  $('pfDownloadAllBtn').disabled=!$('pfRunPick').value;
  window._pfRuns=r.runs;
  pfUpdateNameHint();}   // which names are taken just changed
function pfShowRun(){const name=$('pfRunPick').value;const run=(window._pfRuns||[]).find(r=>r.name==name);const bust=Date.now();
  $('pfDownloadAllBtn').disabled=!name;
  if(!name){$('pfPlots').innerHTML='<div class="empty"><b>No run selected</b>Pick a run above to see its plots.</div>';return;}
  if(!run||!run.plots.length){$('pfPlots').innerHTML='<div class="empty"><b>No plots yet</b>Run this test, or press Regenerate graphs.</div>';return;}
  $('pfPlots').innerHTML=run.plots.map(f=>`<div>
    <img class="plot" alt="${f}" src="/api/paperfold/plot?run=${encodeURIComponent(name)}&file=${encodeURIComponent(f)}&_=${bust}"></div>`).join('');}
async function pfRegenGraphs(){const name=$('pfRunPick').value;
  if(!name){toast('Pick a run first','err');return;}
  toast('Regenerating…');const r=await api('/api/paperfold/analyze','POST',{run:name});
  if(!r.ok){toast('Error: '+r.error,'err');return;}
  await pfLoadRuns(); $('pfRunPick').value=name; pfShowRun(); toast('Graphs regenerated','ok');}
// "Download all" leaves ONE folder in Downloads, named after the run, with
// every graph inside it - not a pile of loose PNGs and not a zip. Regenerate
// so the graphs are current, then ask the server to write that folder:
// browsers can't create one (the <a download> attribute ignores any path in
// its value), but the Studio server runs on this same machine, so it can.
// Colab is the exception - the kernel is a remote VM there - and answers with
// fallback:true, which drops back to downloading each PNG on its own.
async function pfDownloadAllGraphs(){
  const name=$('pfRunPick').value;
  if(!name){toast('Pick a run first','err');return;}
  const btn=$('pfDownloadAllBtn'); btn.disabled=true;
  try{
    toast('Regenerating…');
    const r=await api('/api/paperfold/analyze','POST',{run:name});
    if(!r.ok){toast('Error: '+r.error,'err');return;}
    await pfLoadRuns(); $('pfRunPick').value=name; pfShowRun();
    if(!r.plots||!r.plots.length){toast('No graphs to download','err');return;}
    const s=await api('/api/paperfold/plots/save','POST',{run:name});
    if(s.ok){toast(`Saved ${s.count} graphs to ${s.short}`,'ok');return;}
    if(!s.fallback){toast('Error: '+s.error,'err');return;}
    toast(`Downloading ${r.plots.length} graphs…`,'ok');
    await triggerDownloads(r.plots.map(f=>
      '/api/paperfold/plot?run='+encodeURIComponent(name)+'&file='+encodeURIComponent(f)+'&download=1'));
  } finally {
    btn.disabled=!$('pfRunPick').value;
  }
}

// ---------- Paper folding: resume/edit a previous run from Setup ----------
// Loads a past run's settings into the form so Start continues it: raising
// Trials makes already-complete models do just the difference (each model
// resumes from however many trials it already has - see
// PaperfoldRunner._run_model), and a newly added model runs in full since it
// has none yet. Per-model tuning options (max_tokens, temperature, ...) are
// persisted in results.json and restored here too; only runs saved before
// that was added fall back to the defaults below.
function pfApplyRunToSetup(run){
  $('pf_name').value=run.name;
  if(run.num_trials!=null)$('pf_trials').value=run.num_trials;
  // fold_min/fold_max come from the run's recorded fold counts; a run saved
  // before fold ranges existed reports its single num_folds as both ends.
  const lo=run.fold_min!=null?run.fold_min:run.num_folds, hi=run.fold_max!=null?run.fold_max:run.num_folds;
  if(lo!=null)$('pf_folds_min').value=lo;
  if(hi!=null)$('pf_folds_max').value=hi;
  pfUpdateFoldHint();
  $('pf_dirmode').value=run.direction_mode||'real';
  // Always overwrite the four placeholder inputs, even when this run doesn't
  // use them - otherwise the previous run's words linger in the hidden fields
  // and reappear the moment the mode is switched back to "fixed".
  const dl=(run.direction_mode=='fixed'&&run.direction_labels)||{};
  $('pf_dir_north').value=dl.north||'';
  $('pf_dir_south').value=dl.south||'';
  $('pf_dir_east').value=dl.east||'';
  $('pf_dir_west').value=dl.west||'';
  pfUpdateDirMode();
  PFCFG.models=(run.models||[]).map(m=>({name:m.name,backend:m.backend||'openai',max_tokens:4096,...(m.options||{})}));
  PF_TRIALS={}; (run.models||[]).forEach(m=>{if(m.trials)PF_TRIALS[m.name]=m.trials;});
  pfRenderModels();
}
function pfResetSetup(){
  $('pf_name').value='';
  $('pf_trials').value=30;
  $('pf_folds_min').value=3;
  $('pf_folds_max').value=3;
  pfUpdateFoldHint();
  $('pf_dirmode').value='real';
  ['north','south','east','west'].forEach(d=>{$('pf_dir_'+d).value='';});
  pfUpdateDirMode();
  PFCFG.models=[pfDefaultModel()];
  PF_TRIALS={};
  pfRenderModels();
  PF_LOADED_NAME=null;
  $('pfSetupPick').value='';
  pfUpdateNameHint();
  pfClearDirty();
}
function pfPickSetupRun(name){
  // Loading replaces everything in the form, so don't do it silently on top of
  // edits that were never saved.
  if(PF_DIRTY&&!confirm('Discard the unsaved changes to this setup and load '
                        +(name?"'"+name+"'":'a blank setup')+'?')){
    $('pfSetupPick').value=PF_LOADED_NAME||'';
    return;
  }
  if(!name){pfResetSetup();return;}
  const run=(window._pfRuns||[]).find(r=>r.name==name);
  if(!run){toast('Could not find that run','err');return;}
  pfApplyRunToSetup(run);
  PF_LOADED_NAME=name;
  pfUpdateNameHint();
  pfClearDirty();
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
  if($('pfSetupPick').value==name||PF_LOADED_NAME==name)pfResetSetup();
  await pfLoadRuns(); pfShowRun();
}

// ---------- Compare: paper-folding runs against each other ----------
// The Paper Folding tab answers "which model is best in this run". This one
// answers "what did changing the prompt do", which needs whole runs put beside
// each other rather than models inside one. Everything numeric is worked out
// server-side (paperfold/comparison.py) so the tables here and the charts it
// draws can never disagree; this file only decides how it is laid out and what
// is comparable to what by eye.
let CMP_RUNS=[];             // every paper-folding run on disk
let CMP_PICKED=[];           // the names ticked, in the order they were ticked
let CMP=null;                // the last summary the server sent back
let CMP_METRIC='accuracy';   // which measure the per-model matrix is showing
let CMP_MODE='delta';        // 'value' (raw numbers) or 'delta' (vs baseline)
let CMP_SORT={table:null,col:null,asc:false};
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cmpNice=n=>String(n).replace(/_/g,' ').trim();

// Formatting mirrors comparison.MEASURES exactly - same rounding, same units -
// so a number read off this page and the same number read off a chart are the
// same number, not two roundings of it.
const CMP_FMT={
  accuracy:v=>v==null?'–':v.toFixed(0)+'%',
  tokens:v=>v==null?'–':Math.round(v).toLocaleString(),
  time:v=>v==null?'–':v.toFixed(1)+'s',
};
const CMP_DFMT={
  accuracy:d=>(d>=0?'+':'')+d.toFixed(1)+' pp',
  tokens:d=>(d>=0?'+':'')+Math.round(d).toLocaleString(),
  time:d=>(d>=0?'+':'')+d.toFixed(1)+'s',
};
const CMP_HIGHER_BETTER={accuracy:true,tokens:false,time:false};
// Whether a change was in the direction you wanted, which is not the same as
// whether the number went up: more accuracy is a win, more tokens is a bill.
function cmpDir(delta,metric){
  if(delta==null||Math.abs(delta)<0.05)return 'flat';
  return (delta>0)==CMP_HIGHER_BETTER[metric]?'up':'down';
}
function cmpDeltaHtml(delta,metric,pct){
  if(delta==null)return '<span class="flat">–</span>';
  const cls=cmpDir(delta,metric);
  const extra=(pct!=null&&metric!='accuracy'&&isFinite(pct))?` (${pct>=0?'+':''}${pct.toFixed(0)}%)`:'';
  return `<span class="${cls}">${esc(CMP_DFMT[metric](delta))}${extra}</span>`;
}

async function cmpLoadRuns(){
  const r=await api('/api/paperfold/runs');
  CMP_RUNS=r.runs||[];
  // Drop anything ticked that has since been deleted, so a stale name can't
  // sit in the selection waiting to fail the next Compare.
  CMP_PICKED=CMP_PICKED.filter(n=>CMP_RUNS.some(x=>x.name==n));
  cmpRenderRunList(); cmpSyncControls();
  if(!CMP)$('cmpBody').innerHTML='<div class="empty"><b>Nothing compared yet</b>'
    +'Tick two or more runs above and press Compare. Start with the run whose direction '
    +'names were left alone as the baseline, and the rest read as what each change did to it.</div>';
}
// Changing the baseline or the scope redraws a comparison that already exists,
// but doesn't start one - those two controls sit above the Compare button, and
// touching them before picking any runs shouldn't fire off a request.
function cmpMaybeRerun(){ if(CMP)cmpRun(); }

function cmpRenderRunList(){
  const el=$('cmpRunList');
  if(!CMP_RUNS.length){
    el.innerHTML='<div class="empty"><b>No paper-folding runs yet</b>Run something on the Paper Folding tab first - this page compares finished runs against each other.</div>';
    return;
  }
  el.innerHTML='<div class="cmp-runs">'+CMP_RUNS.map(r=>{
    const on=CMP_PICKED.includes(r.name);
    const folds=r.fold_min==r.fold_max?`${r.fold_min} folds`:`${r.fold_min}-${r.fold_max} folds`;
    const mode={real:'real names',fixed:'custom words',random:'random words'}[r.direction_mode]||r.direction_mode;
    const labels=r.direction_labels
      ? 'north = '+(r.direction_labels.north||'?')
      : (r.direction_mode=='random'?'a fresh set of words every trial':'north means north');
    return `<label class="cmp-run${on?' on':''}" data-run="${esc(r.name)}">
      <input type="checkbox" ${on?'checked':''} data-run="${esc(r.name)}" onchange="cmpToggleRun(this.dataset.run)">
      <div style="min-width:0">
        <div class="n">${esc(cmpNice(r.name))}</div>
        <div class="m">${esc(mode)} · ${esc(folds)} · ${r.models.length} model${r.models.length==1?'':'s'} · ${r.num_trials??'?'} trials each</div>
        <div class="labels">${esc(labels)}</div>
      </div></label>`;
  }).join('')+'</div>';
}

function cmpToggleRun(name){
  const i=CMP_PICKED.indexOf(name);
  if(i<0)CMP_PICKED.push(name); else CMP_PICKED.splice(i,1);
  cmpRenderRunList(); cmpSyncControls();
}
function cmpSelectAll(on){
  CMP_PICKED=on?CMP_RUNS.map(r=>r.name):[];
  cmpRenderRunList(); cmpSyncControls();
}
function cmpSyncControls(){
  const n=CMP_PICKED.length;
  $('cmpCount').textContent=n+' selected';
  // The baseline has to be one of the ticked runs, and keeping whichever was
  // already chosen (when it survives) means re-ticking a run doesn't silently
  // move the thing everything else is measured against.
  const prev=$('cmpBaseline').value;
  $('cmpBaseline').innerHTML=CMP_PICKED.map(x=>`<option value="${esc(x)}">${esc(cmpNice(x))}</option>`).join('');
  $('cmpBaseline').value=CMP_PICKED.includes(prev)?prev:(CMP_PICKED[0]||'');
  $('cmpRunBtn').disabled=n<2;
  $('cmpRunBtn').title=n<2?'Tick at least two runs to compare':'';
}

async function cmpRun(){
  if(CMP_PICKED.length<2){toast('Tick at least two runs to compare','err');return;}
  const btn=$('cmpRunBtn'); btn.disabled=true;
  $('cmpBody').innerHTML='<div class="empty">Comparing '+CMP_PICKED.length+' runs and drawing the charts&hellip;</div>';
  try{
    const r=await api('/api/paperfold/compare','POST',{
      runs:CMP_PICKED, baseline:$('cmpBaseline').value,
      restrict:$('cmpRestrict').value=='1', plots:true});
    if(!r.ok){
      CMP=null; cmpSyncButtons();
      $('cmpBody').innerHTML=`<div class="empty"><b>Nothing to compare</b>${esc(r.error||'unknown error')}</div>`;
      return;
    }
    CMP=r; CMP_SORT={table:null,col:null,asc:false};
    cmpRender(); cmpSyncButtons();
  } finally { btn.disabled=CMP_PICKED.length<2; }
}
function cmpSyncButtons(){
  $('cmpCsvBtn').disabled=!CMP;
  $('cmpDownloadAllBtn').disabled=!(CMP&&CMP.plots&&CMP.plots.length);
}

// ---------- Compare: rendering ----------
function cmpRender(){
  $('cmpBody').innerHTML=
    cmpScopeCard()+cmpCardsSection()+cmpFindingsSection()+
    cmpSummarySection()+cmpMatrixSection()+cmpPlotsSection();
  cmpBindSort();
}

function cmpScopeCard(){
  const s=CMP.scope, base=CMP.runs.find(r=>r.name==CMP.baseline);
  const folds=s.folds_used.length?s.folds_used.join(', '):'none in common';
  const droppedFolds=Object.entries(s.folds_dropped||{});
  let notes='';
  if(s.models_dropped.length)
    notes+=`<div class="sub"><b>${s.models_dropped.length} model${s.models_dropped.length==1?'':'s'} left out</b> - not every selected run has scored trials for ${esc(s.models_dropped.slice(0,4).join(', '))}${s.models_dropped.length>4?', …':''}. Averages here cover only the models all of these runs share.</div>`;
  if(droppedFolds.length)
    notes+=`<div class="sub"><b>Fold counts left out</b> - ${droppedFolds.map(([n,f])=>esc(cmpNice(n))+' also ran at '+f.join(', ')+' folds').join('; ')}. Those trials are excluded everywhere except the difficulty-curve chart, which is the one place the fold count is the point.</div>`;
  return `<div class="card">
    <h3>What is being compared</h3>
    <div class="sub" style="margin-bottom:var(--s3)">
      ${CMP.runs.length} runs · baseline <b>${esc(cmpNice(CMP.baseline))}</b> ·
      ${s.models_used.length} model${s.models_used.length==1?'':'s'} ·
      ${folds==('none in common')?'no shared fold count':folds+' fold'+(s.folds_used.length==1?'':'s')} ·
      ${CMP.restricted?'like for like':'each run on everything it has'}
    </div>
    ${notes||'<div class="sub">Every selected run has the same models and the same fold counts, so nothing had to be left out.</div>'}
    <div class="sub">Baseline accuracy is ${esc(CMP_FMT.accuracy(base.metrics.accuracy.value))} with a 95% margin of about ±${base.accuracy_ci.toFixed(1)} points. Differences smaller than that are noise.</div>
  </div>`;
}

function cmpCardsSection(){
  const base=CMP.runs.find(r=>r.name==CMP.baseline);
  const cards=CMP.runs.map(r=>{
    const isBase=r.name==CMP.baseline;
    const metrics=['accuracy','tokens','time'].map(k=>{
      const v=r.metrics[k].value, d=v-base.metrics[k].value;
      const pct=base.metrics[k].value?100*d/base.metrics[k].value:null;
      return `<div class="metric"><span class="k">${k=='accuracy'?'Accuracy':k=='tokens'?'Tokens / trial':'Seconds / trial'}</span>
        <span>${esc(CMP_FMT[k](v))} <span class="d">${isBase?'<span class="flat">baseline</span>':cmpDeltaHtml(d,k,pct)}</span></span></div>`;
    }).join('');
    const dir=isBase?'flat':cmpDir(r.metrics.accuracy.value-base.metrics.accuracy.value,'accuracy');
    return `<div class="cmp-card${isBase?' base':''}" style="${isBase?'':'border-top-color:var(--'+(dir=='flat'?'line2':dir)+')'}">
      <div class="t">${esc(cmpNice(r.name))}</div>
      <div class="kindpill"><span class="pill${isBase?'':' accent'}">${esc(r.label.kind)}</span></div>
      <div class="metrics">${metrics}</div>
      <div class="sub" style="font-size:11.5px">${r.model_count} models · ${r.trials.toLocaleString()} scored trials · spread ${esc(CMP_FMT.accuracy(r.metrics.accuracy.min))}–${esc(CMP_FMT.accuracy(r.metrics.accuracy.max))}</div>
    </div>`;
  }).join('');
  return `<div class="card"><h3>Each run at a glance</h3>
    <div class="sub" style="margin-bottom:var(--s4)">The three measures together. Accuracy alone hides the case that matters most: a wording that scores the same but costs half as much again did not leave the models unbothered.</div>
    <div class="cmp-cards">${cards}</div></div>`;
}

function cmpFindingsSection(){
  return `<div class="card"><h3>What stands out</h3>
    <div class="sub" style="margin-bottom:var(--s4)">Read straight off the numbers above: how big each change was, whether it clears the noise floor, and whether the whole field moved or one model did.</div>
    ${CMP.findings.map(f=>`<div class="finding ${esc(f.kind)}">
      <div class="ft">${esc(f.title)}</div><div class="fx">${esc(f.text)}</div></div>`).join('')}</div>`;
}

function cmpSummarySection(){
  const base=CMP.runs.find(r=>r.name==CMP.baseline);
  const head=['Run','Wording','Words','Models','Trials','Accuracy','vs base','Tokens','vs base','Time','vs base','Letter skew'];
  const rows=CMP.runs.map(r=>{
    const d=k=>r.metrics[k].value-base.metrics[k].value;
    const pct=k=>base.metrics[k].value?100*d(k)/base.metrics[k].value:null;
    const isBase=r.name==CMP.baseline;
    return {sort:[cmpNice(r.name),r.label.kind,r.label.words,r.model_count,r.trials,
                  r.metrics.accuracy.value,d('accuracy'),r.metrics.tokens.value,d('tokens'),
                  r.metrics.time.value,d('time'),r.letters.skew],
      html:`<tr>
      <td class="name${isBase?' base':''}" title="${esc(r.name)}">${esc(cmpNice(r.name))}${isBase?' <span class="pill">baseline</span>':''}</td>
      <td style="text-align:left">${esc(r.label.kind)}</td>
      <td>${r.label.words.toFixed(0)}</td>
      <td>${r.model_count}</td>
      <td>${r.trials.toLocaleString()}</td>
      <td>${esc(CMP_FMT.accuracy(r.metrics.accuracy.value))}<div class="sub-v">${esc(CMP_FMT.accuracy(r.metrics.accuracy.min))}–${esc(CMP_FMT.accuracy(r.metrics.accuracy.max))}</div></td>
      <td>${isBase?'<span class="flat">–</span>':cmpDeltaHtml(d('accuracy'),'accuracy')}</td>
      <td>${esc(CMP_FMT.tokens(r.metrics.tokens.value))}</td>
      <td>${isBase?'<span class="flat">–</span>':cmpDeltaHtml(d('tokens'),'tokens',pct('tokens'))}</td>
      <td>${esc(CMP_FMT.time(r.metrics.time.value))}</td>
      <td>${isBase?'<span class="flat">–</span>':cmpDeltaHtml(d('time'),'time',pct('time'))}</td>
      <td>${r.letters.skew.toFixed(0)}%<div class="sub-v">${esc(r.letters.top_letter)} ${r.letters.top_share.toFixed(0)}%</div></td></tr>`};
  });
  return `<div class="card"><h3>Run by run</h3>
    <div class="sub" style="margin-bottom:var(--s4)">Click any column to sort. "Letter skew" is how far the answers drifted from an even spread across A-E - a run leaning hard on one letter has stopped answering the puzzle and started guessing.</div>
    ${cmpTable('summary',head,rows)}</div>`;
}

function cmpMatrixSection(){
  const metric=CMP_METRIC, base=CMP.runs.find(r=>r.name==CMP.baseline);
  const delta=CMP_MODE=='delta';
  const cell=(r,m)=>{
    const v=r.per_model[m]?r.per_model[m][metric]:null;
    if(v==null)return null;
    if(!delta)return v;
    const b=base.per_model[m]?base.per_model[m][metric]:null;
    if(b==null)return null;
    return metric=='accuracy'?v-b:(b?100*(v-b)/b:null);
  };
  // One pass to fix the color scale, so a shade means the same thing in every
  // column. In change mode the scale stops at the 90th percentile of the
  // changes rather than the largest one: a single model that spent four times
  // what it did on the baseline would otherwise set the contrast for the whole
  // grid and leave every other cell the same washed-out neutral. Values past it
  // share the end shade and are still printed in full. The baseline's own
  // column is left out of the calculation - it is zeros by construction.
  let lo=Infinity, hi=-Infinity;
  const mags=[];
  CMP.models.forEach(m=>CMP.runs.forEach(r=>{
    const v=cell(r,m); if(v==null)return;
    lo=Math.min(lo,v); hi=Math.max(hi,v);
    if(r.name!=CMP.baseline)mags.push(Math.abs(v));
  }));
  mags.sort((a,b)=>a-b);
  const biggest=mags.length?mags[mags.length-1]:0;
  const peak=(mags.length?mags[Math.min(mags.length-1,Math.floor(0.9*mags.length))]:0)||biggest;
  const saturated=biggest>1.05*peak;

  const head=['Model'].concat(CMP.runs.map(r=>cmpNice(r.name))).concat(['Swing']);
  const rows=CMP.models.map(m=>{
    const raw=CMP.runs.map(r=>r.per_model[m]?r.per_model[m][metric]:null).filter(v=>v!=null);
    const swing=raw.length>1?Math.max(...raw)-Math.min(...raw):null;
    const tds=CMP.runs.map(r=>{
      const v=cell(r,m), shown=r.per_model[m]?r.per_model[m][metric]:null;
      if(shown==null)return '<td class="flat">–</td>';
      // In change mode the baseline's own column would be a stripe of "+0.0"
      // saying nothing, so it carries the starting value instead - the row then
      // reads as "began here, then moved by this much, and this much".
      if(delta&&r.name==CMP.baseline)
        return `<td class="base heat flat" title="baseline">${esc(CMP_FMT[metric](shown))}</td>`;
      const text=delta
        ?(v==null?'–':(metric=='accuracy'?CMP_DFMT.accuracy(v):(v>=0?'+':'')+v.toFixed(0)+'%'))
        :CMP_FMT[metric](shown);
      return `<td class="heat${!delta&&r.name==CMP.baseline?' base':''}" style="background:${cmpHeat(v,{delta,metric,peak,lo,hi})}"
        title="${esc(cmpNice(r.name))}: ${esc(CMP_FMT[metric](shown))}">${esc(text)}</td>`;
    }).join('');
    // Sort keys follow what each cell actually shows, so the baseline column -
    // which shows starting values rather than a column of zeros - sorts by
    // those values.
    return {sort:[m].concat(CMP.runs.map(r=>{
        const v=(delta&&r.name==CMP.baseline)
          ? (r.per_model[m]?r.per_model[m][metric]:null) : cell(r,m);
        return v==null?-Infinity:v;})).concat([swing==null?-Infinity:swing]),
      html:`<tr><td class="name" title="${esc(m)}">${esc(m)}</td>${tds}
        <td>${swing==null?'–':esc(CMP_FMT[metric](swing))}</td></tr>`};
  });

  const peakText=metric=='accuracy'?CMP_DFMT.accuracy(peak):Math.round(peak)+'%';
  // The swatch strip always runs from the most negative change on the left to
  // the most positive on the right, but green always means "the way you wanted"
  // - so which end is which depends on the measure. More accuracy is a win;
  // more tokens is a bill.
  const leftEnd=CMP_HIGHER_BETTER[metric]?'worse':'better',
        rightEnd=CMP_HIGHER_BETTER[metric]?'better':'worse';
  const legend=delta
    ?`<div class="cmp-legend"><span>Change against ${esc(cmpNice(CMP.baseline))}:</span>
       <span class="swatches">${[-1,-0.6,-0.25,0,0.25,0.6,1].map(t=>
         `<span class="sw" style="background:${cmpHeat(t*peak,{delta:true,metric,peak,lo,hi})}"></span>`).join('')}</span>
       <span>${leftEnd} &larr; unchanged &rarr; ${rightEnd}${saturated
         ?`, colour running out at ${esc(peakText)} - bigger changes share the end shade, so read those cells' numbers`
         :` (up to ${esc(peakText)})`}</span></div>`
    :`<div class="cmp-legend"><span>${esc(metric=='accuracy'?'0% to 100% correct':'from '+CMP_FMT[metric](lo)+' to '+CMP_FMT[metric](hi))}</span></div>`;

  return `<div class="card"><h3>Every model, every run</h3>
    <div class="between" style="margin-bottom:var(--s3)">
      <div class="sub" style="max-width:640px">A row that stays flat across the columns is a model the wording didn't reach. A row that lurches is one whose answer was leaning on the words - the puzzle underneath never changed. "Swing" is that row's lowest to highest, which is the same ranking the sensitivity chart draws.</div>
      <div class="flex">
        <select onchange="CMP_METRIC=this.value;cmpRender()" aria-label="Measure to show">
          <option value="accuracy"${CMP_METRIC=='accuracy'?' selected':''}>Accuracy</option>
          <option value="tokens"${CMP_METRIC=='tokens'?' selected':''}>Tokens per trial</option>
          <option value="time"${CMP_METRIC=='time'?' selected':''}>Seconds per trial</option>
        </select>
        <select onchange="CMP_MODE=this.value;cmpRender()" aria-label="Values or change">
          <option value="delta"${CMP_MODE=='delta'?' selected':''}>Change vs baseline</option>
          <option value="value"${CMP_MODE=='value'?' selected':''}>Raw values</option>
        </select>
      </div>
    </div>
    ${cmpTable('matrix',head,rows)}
    ${legend}</div>`;
}

// Cell shading. Two scales, both anchored so that "no color" means "nothing to
// report": a change grid fades out at zero and deepens either side of it, a raw
// grid runs from the lowest value on the page to the highest. Alpha over the
// surface rather than solid fills, so the text on top stays the same readable
// color in every cell instead of needing its own contrast rule.
function cmpHeat(v,{delta,metric,peak,lo,hi}){
  if(v==null)return 'transparent';
  if(delta){
    const m=peak?Math.min(1,Math.abs(v)/peak):0;
    if(m<0.02)return 'transparent';
    const good=(v>0)==CMP_HIGHER_BETTER[metric];
    return `rgba(${good?'63,178,127':'224,113,107'},${(0.10+0.55*m).toFixed(3)})`;
  }
  if(metric=='accuracy'){
    if(v<=20)return 'rgba(224,113,107,.42)';        // at or below the 20% chance line
    return `rgba(63,178,127,${(0.08+0.50*Math.min(1,(v-20)/80)).toFixed(3)})`;
  }
  const span=(hi-lo)||1, t=Math.min(1,Math.max(0,(v-lo)/span));
  return `rgba(232,134,60,${(0.06+0.44*t).toFixed(3)})`;   // more spend = warmer
}

// ---------- Compare: sortable tables ----------
// Rows carry their own sort keys alongside their HTML, so sorting never has to
// parse the numbers back out of the markup it just formatted.
function cmpTable(id,head,rows){
  const s=CMP_SORT.table==id?CMP_SORT:null;
  if(s&&s.col!=null){
    rows=rows.slice().sort((a,b)=>{
      const x=a.sort[s.col],y=b.sort[s.col];
      const c=(typeof x=='string'||typeof y=='string')
        ?String(x).localeCompare(String(y)):(x-y);
      return s.asc?c:-c;
    });
  }
  const ths=head.map((h,i)=>{
    const on=s&&s.col==i;
    return `<th class="${i==0?'name ':''}${on?'sorted '+(s.asc?'asc':''):''}"
      data-table="${id}" data-col="${i}">${esc(h)}</th>`;
  }).join('');
  return `<div class="cmp-scroll"><table class="cmp"><thead><tr>${ths}</tr></thead>
    <tbody>${rows.map(r=>r.html).join('')}</tbody></table></div>`;
}
function cmpBindSort(){
  document.querySelectorAll('#cmpBody table.cmp th[data-col]').forEach(th=>{
    th.onclick=()=>{
      const table=th.dataset.table, col=+th.dataset.col;
      // First click on a column sorts it descending (biggest first, which is
      // what you want from every column here); clicking the same one again
      // flips it.
      CMP_SORT=(CMP_SORT.table==table&&CMP_SORT.col==col)
        ? {table,col,asc:!CMP_SORT.asc} : {table,col,asc:false};
      cmpRender();
    };
  });
}

// ---------- Compare: charts ----------
// Each chart gets a caption saying what to look for in it - the charts are
// worth nothing if it isn't obvious which question each one answers. The three
// by-experiment bar charts carry their own explanation in their subtitles, so
// they are left out here rather than saying it twice.
const CMP_CAPTIONS={
  'accuracy_matrix.png':'Every model against every run. Look for whole rows that go dark (a model the wording broke) and whole columns that do (a wording that broke everyone).',
  'tokens_matrix.png':'The same grid in tokens per trial. Most of the contrast here is between models rather than between wordings - one reasoning model can spend five times what the rest of the field does - so read along each row before comparing columns.',
  'time_matrix.png':'And in seconds per trial. Read it beside the token grid: a row that got slower without getting more expensive was a model thinking for longer, not writing more.',
  'accuracy_change_matrix.png':'The same grid as change from the baseline. Green gained, red lost; a column of one color is the field moving together.',
  'tokens_change_matrix.png':'What that change cost per model. A red column here beside a colorless one in the chart above is the "paid more, got nothing" case.',
  'time_change_matrix.png':'And what it cost in waiting. Green got faster, red got slower, each against that model’s own baseline rather than against the field.',
  'model_slopes.png':'One line per model. Parallel lines mean the wording did the same thing to everybody; lines that cross mean it suits some models and not others, and those need different follow-ups.',
  'sensitivity_by_model.png':'Ranked by how much each model swung across the whole selection. Top of this chart is where the words were doing the work; the bottom is what reading the geometry looks like.',
  'accuracy_vs_tokens_by_experiment.png':'Accuracy against token spend, with an arrow from the baseline to each run. Straight up bought accuracy, straight right only bought a bill.',
  'accuracy_vs_time_by_experiment.png':'The same trade-off measured in seconds rather than tokens.',
  'label_complexity.png':'Both measures against how many words each direction name was given. Bigger markers mean the labels themselves contained real direction words, which tests interference rather than unfamiliarity.',
  'accuracy_by_folds_by_experiment.png':'Difficulty curves, one per run, models averaged. The only chart that keeps each run’s full fold range - where a line reaches the chance level is how much folding that wording could carry.',
  'letter_bias_by_experiment.png':'Which of the five letters the answers went to. Answers piling onto one letter are a fallback, not a wrong answer to the puzzle.',
};
function cmpPlotsSection(){
  if(!CMP.plots||!CMP.plots.length)
    return '<div class="card"><h3>Charts</h3><div class="empty">No charts were produced for this selection.</div></div>';
  const bust=Date.now();
  return `<div class="card"><h3>Charts</h3>
    <div class="sub" style="margin-bottom:var(--s4)">Drawn fresh for this exact selection, baseline and scope - change any of them and press Compare again.</div>
    <div class="cmp-plots">${CMP.plots.map(f=>`<figure>
      <img class="plot" alt="${esc(f)}" src="/api/paperfold/compare/plot?slug=${encodeURIComponent(CMP.slug)}&file=${encodeURIComponent(f)}&_=${bust}">
      ${CMP_CAPTIONS[f]?`<figcaption>${esc(CMP_CAPTIONS[f])}</figcaption>`:''}</figure>`).join('')}</div></div>`;
}

// ---------- Compare: exports ----------
// The CSV is the long-form version of both tables: one row per model per run
// plus a row per run total, so the whole comparison can go into a notebook or a
// spreadsheet without being retyped off the screen.
function cmpDownloadCsv(){
  if(!CMP){toast('Run a comparison first','err');return;}
  const base=CMP.runs.find(r=>r.name==CMP.baseline);
  const q=v=>{const s=v==null?'':String(v);
    return /[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;};
  const lines=[['run','wording','words_per_label','spatial_words_in_labels','scope',
                'model','trials','accuracy_pct','accuracy_change_vs_baseline_pp',
                'tokens_per_trial','tokens_change_pct','seconds_per_trial',
                'seconds_change_pct'].join(',')];
  const scope=CMP.restricted?'shared models and folds only':'everything each run has';
  for(const r of CMP.runs){
    const row=(model,acc,tok,sec,trials)=>{
      const b=model=='ALL MODELS'
        ? {accuracy:base.metrics.accuracy.value,tokens:base.metrics.tokens.value,time:base.metrics.time.value}
        : (base.per_model[model]||{});
      const pct=(v,bv)=>(v==null||!bv)?'':(100*(v-bv)/bv).toFixed(2);
      lines.push([r.name,r.label.kind,r.label.words,r.label.spatial_words,scope,model,trials,
        acc==null?'':acc.toFixed(2),
        (acc==null||b.accuracy==null)?'':(acc-b.accuracy).toFixed(2),
        tok==null?'':tok.toFixed(1), pct(tok,b.tokens),
        sec==null?'':sec.toFixed(2), pct(sec,b.time),
      ].map(q).join(','));
    };
    row('ALL MODELS',r.metrics.accuracy.value,r.metrics.tokens.value,r.metrics.time.value,r.trials);
    for(const m of CMP.models){
      const pm=r.per_model[m]; if(!pm)continue;
      row(m,pm.accuracy,pm.tokens,pm.time,pm.trials);
    }
  }
  const blob=new Blob([lines.join('\n')],{type:'text/csv'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='paperfold_comparison_'+CMP.runs.length+'_runs.csv';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href),4000);
  toast('CSV downloaded','ok');
}

// Same deal as the Paper Folding tab's "Download all": the server writes one
// folder into Downloads because a browser can't, and falls back to downloading
// each PNG on its own where it can't (Colab).
async function cmpDownloadAllGraphs(){
  if(!CMP||!CMP.plots||!CMP.plots.length){toast('Run a comparison first','err');return;}
  const btn=$('cmpDownloadAllBtn'); btn.disabled=true;
  try{
    const s=await api('/api/paperfold/compare/plots/save','POST',{slug:CMP.slug});
    if(s.ok){toast(`Saved ${s.count} charts to ${s.short}`,'ok');return;}
    if(!s.fallback){toast('Error: '+s.error,'err');return;}
    toast(`Downloading ${CMP.plots.length} charts…`,'ok');
    await triggerDownloads(CMP.plots.map(f=>
      '/api/paperfold/compare/plot?slug='+encodeURIComponent(CMP.slug)+
      '&file='+encodeURIComponent(f)+'&download=1'));
  } finally { cmpSyncButtons(); }
}

// ---------- Confusion: one experiment, nothing but matrices ----------
// The Paper Folding and Compare tabs both read one bit off each trial - right
// or wrong - and that bit is where a bias hides: on a five-way choice a model
// that reasoned and got unlucky scores the same 20% as one that answers "C" to
// everything. This page never collapses the two halves of a trial, and it shows
// nothing else. Every number is worked out server-side (paperfold/confusion.py)
// so the tables here and the charts it draws can never disagree.
let CFM_RUNS=[];             // every paper-folding run on disk
let CFM=null;                // the last analysis the server sent back
let CFM_MODE='share';        // how a cell prints itself: share | count

// The three levels, in reading order, each with what it is for. Everything on
// the page is one of these.
const CFM_LEVELS=[
  ['overall','Everyone together',
   'The experiment\'s own matrix, every model pooled. A lean here is a fact about the prompt rather than about any one model - a bias shared by the whole field is unlikely to be a coincidence repeated seventeen times.'],
  ['families','By provider family',
   'The same matrix per family. Providers train on their own data with their own answer-formatting conventions, so a fallback letter is very often a family trait, and grouping is the only way to see that.'],
  ['models','Model by model',
   'Where the habit actually lives. One model with a favourite letter disappears into a field average; here it is a matrix with a column running all the way down it.'],
];

const cfmNice=n=>String(n).replace(/_/g,' ').trim();
const cfmPct=v=>v==null?'&ndash;':v.toFixed(0)+'%';

// ---------- Confusion: picking the experiment ----------
async function cfmLoadRuns(){
  const r=await api('/api/paperfold/runs');
  CFM_RUNS=r.runs||[];
  const sel=$('cfmRun'), previous=sel.value;
  if(!CFM_RUNS.length){
    sel.innerHTML='<option value="">no paper-folding runs yet</option>';
    $('cfmRunHint').textContent='';
    $('cfmBody').innerHTML='<div class="empty"><b>No paper-folding runs yet</b>'
      +'Run something on the Paper Folding tab first - this page reads a finished run.</div>';
    return;
  }
  sel.innerHTML=CFM_RUNS.map(x=>
    `<option value="${esc(x.name)}">${esc(cfmNice(x.name))}</option>`).join('');
  // Keep whatever was being looked at across a refresh, so reloading the run
  // list doesn't silently move the page to a different experiment.
  sel.value=CFM_RUNS.some(x=>x.name==previous)?previous:CFM_RUNS[0].name;
  if(!CFM||CFM.experiment.name!=sel.value)cfmRun();
}

function cfmRunHint(){
  const r=CFM_RUNS.find(x=>x.name==$('cfmRun').value);
  if(!r){$('cfmRunHint').textContent='';return;}
  const folds=r.fold_min==r.fold_max?`${r.fold_min} folds`:`${r.fold_min}-${r.fold_max} folds`;
  const mode={real:'real direction names',fixed:'custom placeholder words',
              random:'a fresh set of random words every trial'}[r.direction_mode]||r.direction_mode;
  $('cfmRunHint').textContent=`${mode} · ${folds} · ${r.models.length} model`
    +`${r.models.length==1?'':'s'} · ${r.num_trials??'?'} trials each`;
}

async function cfmRun(){
  const name=$('cfmRun').value;
  cfmRunHint();
  if(!name)return;
  $('cfmBody').innerHTML='<div class="empty">Building the matrices for '
    +esc(cfmNice(name))+' and drawing the charts&hellip;</div>';
  const r=await api('/api/paperfold/confusion','POST',{run:name,plots:true});
  if(!r.ok){
    CFM=null; cfmSyncButtons();
    $('cfmBody').innerHTML=`<div class="empty"><b>Nothing to show</b>${esc(r.error||'unknown error')}</div>`;
    return;
  }
  CFM=r; cfmRender(); cfmSyncButtons();
}
function cfmSyncButtons(){
  $('cfmCsvBtn').disabled=!CFM;
  $('cfmDownloadAllBtn').disabled=!(CFM&&CFM.plots&&CFM.plots.length);
}

// ---------- Confusion: one matrix as a table ----------
// Cells are shaded by their share of the row, the standard confusion-matrix
// reading: across a row is "when the answer was this, here is what came back".
// The bias reads down a column instead, which is what the marginal under the
// grid is for.
function cfmHeat(share){
  if(share==null)return 'transparent';
  if(share<2)return 'transparent';
  return `rgba(58,124,196,${(0.08+0.62*Math.min(1,share/100)).toFixed(3)})`;
}

function cfmMatrix(m){
  const cols=m.cols;
  const head=`<tr><th class="name"></th>`
    +cols.map(c=>`<th>${c=='?'?'no letter':esc(c)}</th>`).join('')+'</tr>';

  const body=m.rows.map((letter,i)=>{
    const tds=cols.map((c,j)=>{
      const share=m.row_share[i][j], count=m.counts[i][j];
      if(share==null)return '<td class="cell">&ndash;</td>';
      const main=CFM_MODE=='count'?count.toLocaleString():share.toFixed(0)+'%';
      const sub=CFM_MODE=='count'?share.toFixed(0)+'%':count.toLocaleString();
      return `<td class="cell${letter==c?' diag':''}" style="background:${cfmHeat(share)}"
        title="The answer was ${esc(letter)}, the model said ${esc(c)}: ${count.toLocaleString()} trials, ${share.toFixed(1)}% of that row"
        >${main}<span class="n">${sub}</span></td>`;
    }).join('');
    return `<tr><td class="name"><b>${esc(letter)}</b><span class="n">`
      +`${m.row_totals[i].toLocaleString()} trials</span></td>${tds}</tr>`;
  }).join('');

  // The column marginal: how often each letter was given as the answer against
  // how often it was the right one. Those two matching is what no bias looks
  // like, and the gap between them is the lean in percentage points.
  const marg=(cls,label,cellFor)=>`<tr class="marg ${cls}">`
    +`<td class="name">${label}</td>`
    +cols.map(c=>cellFor(c)).join('')+'</tr>';
  const strong=g=>Math.abs(g)>=5;
  const marginal=
     marg('first given','given as the answer',c=>
       `<td class="given">${m.answered_share[c]==null?'&ndash;':m.answered_share[c].toFixed(0)+'%'}</td>`)
    +marg('','was the correct answer',c=>
       `<td>${m.correct_share[c]==null?'&ndash;':m.correct_share[c].toFixed(0)+'%'}</td>`)
    +marg('','difference',c=>{
       const g=m.lean[c];
       if(g==null)return '<td class="gap">&ndash;</td>';
       return `<td class="gap${strong(g)?(g>0?' over':' under'):''}">${g>=0?'+':''}${g.toFixed(0)}</td>`;});

  return `<div class="cfm-wrap">
      <div class="cfm-ycap"><b>What the answer actually was</b><br>the letter matching the paper once it is unfolded</div>
      <div class="cmp-scroll" style="max-height:none">
        <table class="cfm"><thead>${head}</thead><tbody>${body}${marginal}</tbody></table>
      </div>
    </div>
    <div class="cfm-xcap"><b>What the model answered</b>the letter it picked out of the five candidates it was shown</div>`;
}

function cfmMatrixCard(m){
  const models=m.level=='family'
    ? `${m.models.length} model${m.models.length==1?'':'s'}: ${esc(m.models.join(', '))}`
    : m.level=='all' ? `all ${m.models.length} models pooled together` : 'on its own';
  return `<div class="cfm-matrix">
    <div class="mt">${esc(m.level=='model'?m.name:m.name)}</div>
    <div class="ms">${m.n.toLocaleString()} trials &middot; ${cfmPct(m.accuracy)} correct
      &middot; ${models}${m.no_answer?` &middot; ${m.no_answer} with no readable letter`:''}</div>
    ${cfmMatrix(m)}
    <div class="cfm-verdict ${esc(m.status)}">${esc(m.verdict)}</div>
  </div>`;
}

// ---------- Confusion: rendering ----------
function cfmRender(){
  const e=CFM.experiment;
  const mode=`<select onchange="CFM_MODE=this.value;cfmRender()" aria-label="What each cell shows">
      <option value="share"${CFM_MODE=='share'?' selected':''}>Cells: share of the row</option>
      <option value="count"${CFM_MODE=='count'?' selected':''}>Cells: trial counts</option>
    </select>`;
  const header=`<div class="card">
    <div class="between" style="margin-bottom:var(--s3)">
      <h3 style="margin:0">${esc(e.display)}</h3>
      <div class="flex">${mode}</div>
    </div>
    <div class="sub">${e.trials.toLocaleString()} answered trials &middot;
      ${e.models.length} model${e.models.length==1?'':'s'} in
      ${Object.keys(e.families).length} famil${Object.keys(e.families).length==1?'y':'ies'} &middot;
      ${e.fold_counts.join(', ')} fold${e.fold_counts.length==1?'':'s'} &middot;
      ${e.accuracy}% correct against 20% for guessing</div>
    <div class="sub">Read a row for "when the answer was this letter, here is what came back".
      Read a column for what the model reaches for &ndash; that is where a bias sits, and the
      three lines under each grid measure it: how often a letter was given as the answer,
      how often it was the right one, and the gap between them.</div>
  </div>`;

  const sections=CFM_LEVELS.map(([key,title,blurb])=>{
    const list=key=='overall'?[CFM.overall]:CFM[key];
    if(!list||!list.length)return '';
    if(key=='families'&&list.length<2)return '';   // one family is the overall matrix again
    return `<div class="card"><div class="cfm-level">
      <div class="lt">${esc(title)}</div>
      <div class="lc">${esc(blurb)}</div>
      ${list.map(cfmMatrixCard).join('')}</div></div>`;
  }).join('');

  $('cfmBody').innerHTML=header+sections+cfmPlotsSection();
}

function cfmPlotsSection(){
  if(!CFM.plots||!CFM.plots.length)return '';
  const bust=Date.now();
  // The two sheets first: a bias is a difference between panels, and that is
  // only visible with the panels side by side.
  const order=CFM.plots.slice().sort((a,b)=>
    (a.startsWith('sheet_')?0:1)-(b.startsWith('sheet_')?0:1));
  const caption=f=>
    f=='sheet_by_model.png'?'Every model on one page. A vertical stripe is a model with a favourite letter, and it is unmistakable next to the panels that do not have one.'
    :f=='sheet_by_family.png'?'Every provider family on one page. Green rings the diagonal, so colour anywhere else in one column is a letter that family reaches for.'
    :'';
  return `<div class="card"><h3>The same matrices as charts</h3>
    <div class="sub" style="margin-bottom:var(--s4)">Drawn fresh for this experiment. These are the version to put in a write-up &ndash; each one names the experiment it came from and carries its own reading underneath.</div>
    <div class="cfm-plots">${order.map(f=>`<figure>
      <img class="plot" alt="${esc(f)}" src="/api/paperfold/confusion/plot?slug=${encodeURIComponent(CFM.slug)}&file=${encodeURIComponent(f)}&_=${bust}">
      ${caption(f)?`<figcaption>${esc(caption(f))}</figcaption>`:''}</figure>`).join('')}</div></div>`;
}

// ---------- Confusion: exports ----------
// One row per cell of every matrix, plus the column marginals, so a claim made
// on this page can be re-checked in a notebook without retyping it off screen.
function cfmDownloadCsv(){
  if(!CFM){toast('Pick an experiment first','err');return;}
  const q=v=>{const s=v==null?'':String(v);
    return /[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;};
  const lines=[['experiment','level','matrix','models','trials','accuracy_pct',
                'correct_answer','model_answer','count','share_of_row_pct',
                'letter_given_pct','letter_was_correct_pct','difference_pts',
                'status','skew','bias_p'].join(',')];
  for(const m of [CFM.overall,...CFM.families,...CFM.models]){
    const p=m.bias_test?m.bias_test.p:'';
    m.rows.forEach((truth,i)=>m.cols.forEach((given,j)=>{
      lines.push([CFM.experiment.name,m.level,m.name,m.models.join(' '),m.n,m.accuracy,
        truth,given,m.counts[i][j],m.row_share[i][j],
        m.answered_share[given]??'',m.correct_share[given]??'',m.lean[given]??'',
        m.status,m.skew,p].map(q).join(','));
    }));
  }
  const blob=new Blob([lines.join('\n')],{type:'text/csv'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='confusion_'+CFM.experiment.name+'.csv';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href),4000);
  toast('CSV downloaded','ok');
}

// Same deal as the other tabs' "Download all": the server writes one folder
// into Downloads because a browser can't, and falls back to downloading each
// PNG on its own where it can't (Colab).
async function cfmDownloadAllGraphs(){
  if(!CFM||!CFM.plots||!CFM.plots.length){toast('Pick an experiment first','err');return;}
  const btn=$('cfmDownloadAllBtn'); btn.disabled=true;
  try{
    const s=await api('/api/paperfold/confusion/plots/save','POST',{slug:CFM.slug});
    if(s.ok){toast(`Saved ${s.count} matrices to ${s.short}`,'ok');return;}
    if(!s.fallback){toast('Error: '+s.error,'err');return;}
    toast(`Downloading ${CFM.plots.length} matrices…`,'ok');
    await triggerDownloads(CFM.plots.map(f=>
      '/api/paperfold/confusion/plot?slug='+encodeURIComponent(CFM.slug)+
      '&file='+encodeURIComponent(f)+'&download=1'));
  } finally { cfmSyncButtons(); }
}

// ---------- Terminal (mirrors the real process's stdout/stderr/logging) ----------
let TERM_SEQ=0;
function toggleTerminal(){const t=$('terminal'),collapsed=t.classList.toggle('collapsed');
  $('termToggle').innerHTML=collapsed?'&#9650;':'&#9660;';
  $('termToggle').setAttribute('aria-label',collapsed?'Expand terminal':'Collapse terminal');}
// Empties the panel without touching the server's buffer or TERM_SEQ: polling
// only ever asks for lines after the last one it saw, so nothing cleared here
// comes back on the next tick, and output from this point on still arrives.
// Leaves the panel genuinely blank rather than swapping in a "cleared"
// placeholder - Clear is self-explanatory, and a line of text sitting where
// the output used to be reads like output.
function clearTerminal(){
  $('termOut').innerHTML='';
}
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
  PFCFG.models=[pfDefaultModel()];pfRenderModels();pfUpdateFoldHint();pfLoadRuns();pfPollStatus();})();
</script>
</body></html>
"""