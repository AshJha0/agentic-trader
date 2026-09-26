"""Check every link in the documentation.

    python scripts/check_links.py [--external]

Relative Markdown links must point at an existing file (and heading anchor);
``blob/main`` links in docs/index.html must point at files in the repository.
``--external`` also requests every external URL (not run in CI: third-party sites
rate-limit and go down independently of this repository). Exit status is the
number of broken internal links.
"""
import argparse
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", "build", ".pytest_cache", ".git", "node_modules"}


def anchors(md_text: str) -> set[str]:
    """Heading slugs the way GitHub makes them: fenced code is not a heading, and a
    repeated heading gets -1, -2, ... suffixes."""
    out: set[str] = set()
    seen: dict[str, int] = {}
    text_no_code = re.sub(r"```.*?```", "", md_text, flags=re.S)
    for h in re.findall(r"^#{1,6} (.+)$", text_no_code, flags=re.M):
        text = re.sub(r"`", "", h.strip())
        slug = re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        out.add(slug if n == 0 else f"{slug}-{n}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--external", action="store_true")
    args = ap.parse_args()
    bad, external = [], set()
    docs = [p for p in ROOT.rglob("*.md") if not SKIP_DIRS & set(p.parts) and "egg-info" not in str(p)]
    for md in docs:
        text = re.sub(r"```.*?```", "", md.read_text(encoding="utf-8"), flags=re.S)
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:")):
                external.add(target)
                continue
            path, _, frag = target.partition("#")
            dest = (md.parent / path).resolve() if path else md
            if not dest.exists():
                bad.append(f"{md.relative_to(ROOT)} -> {target} (missing file)")
            elif frag and dest.suffix == ".md" and frag not in anchors(dest.read_text(encoding="utf-8")):
                bad.append(f"{md.relative_to(ROOT)} -> {target} (missing anchor)")
    html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    for href in re.findall(r'href="([^"]+)"', html):
        m = re.match(r"https://github.com/AshJha0/agentic-trader/blob/main/(.+?)(#.*)?$", href)
        if m and not (ROOT / m.group(1)).exists():
            bad.append(f"docs/index.html -> {m.group(1)} (missing in repo)")
        elif href.startswith("http") and not m:
            external.add(href)
    if args.external:
        for url in sorted(external):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 link-check"})
                code = urllib.request.urlopen(req, timeout=20).status
            except Exception as e:  # noqa: BLE001 - report, do not fail
                code = getattr(e, "code", repr(e)[:60])
            print(f"{code}  {url}")
    print(f"checked {len(docs)} markdown files and docs/index.html; {len(external)} external URLs"
          + ("" if args.external else " (not requested)"))
    print("PROBLEMS:" if bad else "no broken internal links", *bad, sep="\n  ")
    return len(bad)


if __name__ == "__main__":
    sys.exit(main())
