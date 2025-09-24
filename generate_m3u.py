#!/usr/bin/env python3
# generate_m3u.py — call exptv_find.py and write Exp.m3u as a Live TV channel

import subprocess
import sys
import pathlib

def main():
    repo = pathlib.Path(__file__).resolve().parent
    finder = repo / "exptv_find.py"

    proc = subprocess.run(
        [sys.executable, str(finder)],
        capture_output=True,
        text=True,
        timeout=180
    )

    if proc.returncode != 0:
        print("Finder failed, not updating M3U.")
        print(proc.stdout)
        print(proc.stderr)
        sys.exit(1)

    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        print("No URL returned by finder.")
        sys.exit(1)

    mp4_plain = lines[0]

    # EXTINF metadata tuned for Live TV
    m3u = f"""#EXTM3U
#EXTINF:-1 tvg-id="exptv" tvg-name="EXPTV" tvg-logo="https://exptv.org/favicon.ico" group-title="TV",EXPTV
#EXTVLCOPT--http-reconnect=true
#EXTVLCOPT--http-continuous
{mp4_plain}
"""

    out = repo / "Exp.m3u"
    old = out.read_text(encoding="utf-8", errors="ignore") if out.exists() else ""
    if old.strip() == m3u.strip():
        print("M3U unchanged.")
        return 0

    out.write_text(m3u, encoding="utf-8")
    print("M3U updated with Live TV tags.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
