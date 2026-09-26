"""Check that every Mermaid diagram in docs/DIAGRAMS.md parses and renders.

    python scripts/check_mermaid.py            # uses `mmdc` (npm i -g @mermaid-js/mermaid-cli)
    python scripts/check_mermaid.py --html     # writes build/mermaid_check.html for a browser instead

With ``mmdc`` each block is rendered to SVG in a temp dir; the exit status is the
number of diagrams that failed. Without it (and without ``--html``) the script
exits 0 with a notice, so a machine without node does not fail for that reason.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "docs" / "DIAGRAMS.md"

HTML = """<!DOCTYPE html><html><body><pre id="r">running...</pre><div id="render"></div>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
mermaid.initialize({startOnLoad:false});
const blocks = %s;
const res = [];
for (let i = 0; i < blocks.length; i++) {
  try { await mermaid.parse(blocks[i]);
        const {svg} = await mermaid.render("d"+i, blocks[i]);
        document.getElementById("render").insertAdjacentHTML("beforeend", svg);
        res.push((i+1) + ": ok"); }
  catch (e) { res.push((i+1) + ": ERROR " + String(e.message || e).slice(0, 300)); }
}
document.getElementById("r").textContent = res.join("\\n");
window.__mermaid = res;
</script></body></html>"""


def blocks() -> list[str]:
    return re.findall(r"```mermaid\n(.*?)```", MD.read_text(encoding="utf-8"), flags=re.S)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", action="store_true", help="write build/mermaid_check.html instead of using mmdc")
    args = ap.parse_args()
    diagrams = blocks()
    if args.html:
        out = ROOT / "build" / "mermaid_check.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(HTML % json.dumps(diagrams), encoding="utf-8")
        print(f"{len(diagrams)} diagrams -> {out} (open it; window.__mermaid holds the results)")
        return 0
    mmdc = shutil.which("mmdc") or shutil.which("mmdc.cmd")
    if mmdc is None:
        print(f"{len(diagrams)} diagrams found; mmdc not installed (npm i -g @mermaid-js/mermaid-cli) -- not checked")
        return 0
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "puppeteer.json"
        cfg.write_text(json.dumps({"args": ["--no-sandbox", "--disable-setuid-sandbox"]}), encoding="utf-8")
        for i, d in enumerate(diagrams, 1):
            src, dst = Path(tmp) / f"d{i}.mmd", Path(tmp) / f"d{i}.svg"
            src.write_text(d, encoding="utf-8")
            p = subprocess.run([mmdc, "-i", str(src), "-o", str(dst), "-p", str(cfg), "-q"],
                               capture_output=True, text=True, timeout=120)
            ok = p.returncode == 0 and dst.exists()
            fails += not ok
            print(f"{'ok  ' if ok else 'FAIL'} diagram {i}" + ("" if ok else f": {p.stderr.strip()[-300:]}"))
    print(f"{len(diagrams)} diagrams, {fails} failures")
    return fails


if __name__ == "__main__":
    sys.exit(main())
