"""Render a playback page in headless Chrome and report what it drew.

PROGRESS.md has listed "a headless smoke test of the rendered page" as the
obvious next hardening step since the web replay landed: `tests/test_viz_web.py`
pins the Python payload, and nothing at all checks the ~1,400 lines of
JavaScript that turn it into a map. Every bug found in that layer so far was
found by a person driving the page by hand.

This is the smallest thing that closes the gap without a new dependency. It uses
whatever Chrome or Edge is already installed -- no Playwright, no browser
download -- and it patches two things out of the page first:

* the **GSAP CDN script**, replaced by a stub that applies each tween's end
  state immediately. The page cannot run without `gsap` defined, and a sandbox
  without network cannot fetch it. Applying end states rather than animating is
  also what you want from a smoke test: it renders the settled frame.
* the **Google Fonts stylesheet**, which is cosmetic and would otherwise stall
  the load.

What it then asserts is deliberately structural -- the SVG layers exist, the
right number of stop markers and route paths were drawn, the console logged no
errors -- because a screenshot cannot be diffed reliably but "the page threw and
drew nothing" is exactly the failure that keeps happening.

Usage::

    python tools/headless_check.py flight.html [--png out.png]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

GSAP_STUB = """<script>
/* Minimal GSAP stand-in: applies end states at once, animates nothing. */
(function(){
  function applyVars(target, vars){
    if (!target || !vars) return;
    var list = (target.length !== undefined && !target.tagName) ? target : [target];
    for (var i = 0; i < list.length; i++){
      var el = list[i];
      if (!el || !el.setAttribute) continue;
      if (vars.attr) for (var k in vars.attr) el.setAttribute(k, vars.attr[k]);
      for (var p in vars){
        if (["attr","duration","ease","repeat","yoyo","delay","stagger",
             "onComplete","onUpdate","repeatDelay","overwrite","paused",
             "onStart","immediateRender","transformOrigin","onRepeat"].indexOf(p) >= 0) continue;
        if (el.style && ["opacity","x","y","scale","rotation"].indexOf(p) >= 0){
          if (p === "opacity") el.style.opacity = vars[p];
          continue;
        }
        if (el.setAttribute && typeof vars[p] !== "object") {
          try { el.setAttribute(p, vars[p]); } catch (e) {}
        }
      }
    }
  }
  function handle(){
    var h = {kill:function(){return h;}, pause:function(){return h;},
             play:function(){return h;}, restart:function(){return h;},
             progress:function(){return h;}, seek:function(){return h;},
             eventCallback:function(){return h;}, then:function(){return h;},
             to:function(t,v){applyVars(t,v); return h;},
             from:function(){return h;},
             fromTo:function(t,a,b){applyVars(t,b); return h;},
             set:function(t,v){applyVars(t,v); return h;},
             add:function(){return h;}, call:function(){return h;}};
    return h;
  }
  var tickers = [];
  window.gsap = {
    to: function(t,v){ applyVars(t,v); if (v && v.onComplete) v.onComplete(); return handle(); },
    from: function(){ return handle(); },
    fromTo: function(t,a,b){ applyVars(t,b); return handle(); },
    set: function(t,v){ applyVars(t,v); return handle(); },
    timeline: function(){ return handle(); },
    delayedCall: function(d,f){ if (typeof f === "function") f(); return handle(); },
    matchMedia: function(){ return {add:function(){}, revert:function(){}}; },
    ticker: {add:function(f){tickers.push(f);}, remove:function(f){
               var i = tickers.indexOf(f); if (i>=0) tickers.splice(i,1);},
             lagSmoothing:function(){}, fps:function(){}},
    killTweensOf: function(){},
    utils: {clamp:function(a,b,c){return Math.max(a,Math.min(b,c));}},
  };
  window.__gsapTickers = tickers;
})();
</script>"""

PROBE = """
(() => {
  const q = s => document.querySelectorAll(s);
  const svg = document.getElementById("map");
  const layer = id => document.getElementById(id);
  const count = id => { const el = layer(id); return el ? el.querySelectorAll("*").length : -1; };
  return {
    title: document.title,
    hasSvg: !!svg,
    viewBox: svg ? svg.getAttribute("viewBox") : null,
    ground: count("lyrGround"),
    zones: count("lyrZones"),
    routes: count("lyrRoutes"),
    stops: count("lyrStops"),
    drones: count("lyrDrones"),
    groundPaths: layer("lyrGround") ? layer("lyrGround").querySelectorAll("path").length : -1,
    groundTexts: layer("lyrGround") ? layer("lyrGround").querySelectorAll("text").length : -1,
    scaleBar: (document.getElementById("scaleTxt") || {}).textContent || null,
    readout: (document.getElementById("readout") || {}).textContent || null,
    stat: (document.getElementById("stDeliv") || {}).textContent || null,
  };
})()
"""


def page_console(stderr: str) -> List[str]:
    """The lines the *page* logged, separated from the browser's own noise.

    `--enable-logging=stderr` puts both in one stream, and only the page's are
    tagged CONSOLE::

        [..:INFO:CONSOLE:6] "Uncaught ReferenceError: f is not defined", source: ...
        [..:ERROR:dbus/bus.cc:405] Failed to connect to the bus: ...

    The second line is Chrome complaining about the machine it is running on. A
    GitHub Ubuntu runner emits a wall of those -- D-Bus, GPU, sandbox -- and an
    earlier version of this file matched any line containing "ERROR", so the
    suite passed on a laptop and failed on CI while both pages rendered
    perfectly. Match the tag, not the word.
    """
    return [ln.strip() for ln in stderr.splitlines() if ":CONSOLE" in ln]


def console_errors(stderr: str) -> List[str]:
    """Page console lines that mean the page broke.

    Chrome logs every console message at INFO severity, `console.error`
    included, so severity cannot separate them -- but an exception that reaches
    the top level is always rendered as "Uncaught ...", which covers thrown
    errors and rejected promises alike. That is the failure this harness exists
    to catch.
    """
    return [ln for ln in page_console(stderr) if "Uncaught" in ln]


def find_browser(explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit if Path(explicit).exists() else None
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return shutil.which("google-chrome") or shutil.which("chromium")


def patch_page(source: Path, target: Path) -> Path:
    """Copy the page with the CDN script and web font swapped for local stubs."""
    html = source.read_text(encoding="utf-8")
    html = re.sub(r'<script src="https://cdnjs\.cloudflare\.com[^"]*"></script>',
                  GSAP_STUB, html, count=1)
    html = re.sub(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com[^"]*">',
                  "", html, count=1)
    target.write_text(html, encoding="utf-8")
    return target


def run(page: Path, browser: str, png: Optional[Path] = None,
        timeout: float = 60.0) -> Dict[str, Any]:
    """Load the page in headless Chrome; return the probe's findings."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        patched = patch_page(page, tmp_dir / "page.html")
        profile = tmp_dir / "profile"
        dump = tmp_dir / "dump.txt"

        cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
               f"--user-data-dir={profile}", "--window-size=1600,1000",
               "--virtual-time-budget=6000", "--run-all-compositor-stages-before-draw",
               "--dump-dom", "--enable-logging=stderr", "--v=0"]
        if png:
            cmd.append(f"--screenshot={png}")
        cmd.append(patched.as_uri())

        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, cwd=tmp_dir)
        dom = proc.stdout
        dump.write_text(dom, encoding="utf-8")

        # --dump-dom gives the rendered DOM; count what the page actually built.
        findings = {
            "exit_code": proc.returncode,
            "dom_bytes": len(dom),
            "stop_markers": dom.count('class="stop"'),
            "route_paths": dom.count('class="route"'),
            "svg_present": "<svg" in dom and 'id="map"' in dom,
            "console_messages": page_console(proc.stderr),
            "console_errors": console_errors(proc.stderr),
        }
        for layer in ("lyrGround", "lyrZones", "lyrRoutes", "lyrStops", "lyrDrones"):
            block = _layer_block(dom, layer)
            findings[layer] = block.count("<") if block else 0
        return findings


def _layer_block(dom: str, layer_id: str) -> str:
    """The markup of one SVG layer group, crudely but adequately extracted."""
    start = dom.find(f'id="{layer_id}"')
    if start < 0:
        return ""
    nxt = dom.find('<g id="lyr', start + 1)
    return dom[start:nxt if nxt > 0 else start + 200000]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", help="a rendered playback .html")
    ap.add_argument("--png", help="also save a screenshot here")
    ap.add_argument("--browser", help="path to Chrome/Edge (autodetected)")
    ap.add_argument("--expect-stops", type=int,
                    help="fail unless this many stop markers were drawn")
    args = ap.parse_args(argv)

    browser = find_browser(args.browser)
    if browser is None:
        print("no Chrome or Edge found -- skipping", file=sys.stderr)
        return 0

    findings = run(Path(args.page), browser,
                   Path(args.png) if args.png else None)
    print(json.dumps(findings, indent=2))

    ok = findings["svg_present"] and findings["lyrGround"] > 20
    if args.expect_stops is not None and findings["stop_markers"] != args.expect_stops:
        print(f"expected {args.expect_stops} stop markers, "
              f"drew {findings['stop_markers']}", file=sys.stderr)
        ok = False
    if findings["console_errors"]:
        print("console errors:", *findings["console_errors"], sep="\n  ",
              file=sys.stderr)
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
