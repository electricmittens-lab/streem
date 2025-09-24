#!/usr/bin/env python3
# exptv_find.py — Find the current playing MP4 on exptv.org
import re
import sys
import datetime
import concurrent.futures
import urllib.parse
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

HOME_URL     = "https://exptv.org/"
CONTENT_BASE = "https://exptv.org/content2/"
UA           = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Safari/537.36"
TIMEOUT      = 12
MAX_JS       = 80
MAX_CSS      = 80
MAX_WORKERS  = 16
PROBE_MAX_N  = 96

sess = requests.Session()
sess.headers.update({"User-Agent": UA})

SCHEDULE_VAR_RX = re.compile(r'\b((?:sun|mon|tue|wed|thu|fri|sat)_[0-2]\d_b[12])\s*=\s*\{([^}]*)\}', re.I)
FILE_RX         = re.compile(r'\b["\']?file["\']?\s*:\s*["\']([^"\']+)["\']', re.I)

MP4_ANY_RX = re.compile(r'https?://exptv\.org/content2/[^\s"\'<>]+?\.mp4(?:#[^\s"\'<>]*)?', re.I)
URL_RX     = re.compile(r'https?://[^\s"\'<>]+', re.I)
CSS_URL_RX    = re.compile(r'url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)', re.I)
CSS_IMPORT_RX = re.compile(r'@import\s+(?:url\(\s*)?[\'"]?([^\'")]+)[\'"]?\s*\)?', re.I)

def fetch_text(url):
    try:
        r = sess.get(url, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        return r.text, r.url, r.headers
    except Exception:
        return "", url, {}

def absolutize(base, src):
    return urllib.parse.urljoin(base, src)

def parse_schedule(text):
    schedule = {}
    for m in SCHEDULE_VAR_RX.finditer(text or ""):
        varname = m.group(1).lower()
        obj = m.group(2)
        f = FILE_RX.search(obj)
        if f:
            schedule[varname] = {"file": f.group(1)}
    return schedule

def find_mp4s(text):
    if not text:
        return set()
    return {u.split("#")[0] for u in MP4_ANY_RX.findall(text)}

def find_candidate_endpoints(text):
    urls = set(URL_RX.findall(text or ""))
    keep = set()
    for u in urls:
        low = u.lower()
        if "exptv.org" not in low:
            continue
        if low.endswith((".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico")):
            continue
        keep.add(u)
    return keep

def extract_urls_from_css(css_text, base_url):
    css_links, mp4_links = set(), set()
    if not css_text: return css_links, mp4_links
    for m in CSS_URL_RX.findall(css_text) + CSS_IMPORT_RX.findall(css_text):
        u = absolutize(base_url, m.strip())
        if u.lower().endswith(".css"): css_links.add(u)
        if u.lower().endswith(".mp4") and "exptv.org/content2/" in u: mp4_links.add(u.split("#")[0])
    for u in URL_RX.findall(css_text):
        uu = absolutize(base_url, u.strip())
        if uu.lower().endswith(".css"): css_links.add(uu)
        if uu.lower().endswith(".mp4") and "exptv.org/content2/" in uu: mp4_links.add(uu.split("#")[0])
    return css_links, mp4_links

def parse_last_modified(headers):
    lm = headers.get("Last-Modified") or headers.get("last-modified")
    if not lm: return None
    try:
        dt = parsedate_to_datetime(lm)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def head_or_range(url):
    try:
        r = sess.head(url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code == 200 and "text/html" not in r.headers.get("content-type","").lower():
            return True, parse_last_modified(r.headers)
    except Exception: pass
    try:
        r = sess.get(url, headers={"Range": "bytes=0-0"}, timeout=TIMEOUT, stream=True, allow_redirects=True)
        if r.status_code in (200, 206):
            return True, parse_last_modified(r.headers)
    except Exception: pass
    return False, None

def choose_best(mp4s):
    if not mp4s: return None
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(head_or_range, u): u for u in mp4s}
        for fut in concurrent.futures.as_completed(futs):
            u = futs[fut]
            try: ok, lm = fut.result()
            except Exception: ok, lm = False, None
            if ok: results[u] = lm
    if not results:
        def trailing_num(u): 
            m = re.search(r'(\d+)\.mp4', u); return int(m.group(1)) if m else -1
        return sorted(mp4s, key=trailing_num, reverse=True)[0]
    def trailing_num(u): m = re.search(r'(\d+)\.mp4', u); return int(m.group(1)) if m else -1
    def sort_key(u):
        lm = results[u] or datetime.datetime.fromtimestamp(0, tz=timezone.utc)
        return (lm, trailing_num(u))
    return sorted(results.keys(), key=sort_key, reverse=True)[0]

def seconds_into_half_hour(now=None):
    if now is None: now = datetime.datetime.now()
    return (now.minute % 30) * 60 + now.second

def compute_schedule_key_and_tz():
    now = datetime.datetime.now()
    weekdays = ["mon","tue","wed","thu","fri","sat","sun"]
    wd = weekdays[now.weekday()]
    hour = f"{now.hour:02d}"
    minute, second = now.minute, now.second
    if minute < 30:
        block, tz, pre_key = "b1", second + minute * 60, None
    else:
        block, tz, pre_key = "b2", second + minute * 60 - 1800, f"{wd}_{hour}_b1"
    key = f"{wd}_{hour}_{block}"
    return key, pre_key, tz

def main():
    all_mp4s, schedule, endpoints = set(), {}, set()

    html, final, _ = fetch_text(HOME_URL)
    if not html:
        return 2
    soup = BeautifulSoup(html, "html.parser")
    all_mp4s |= find_mp4s(html)
    schedule.update(parse_schedule(html))

    js_urls = [absolutize(final, s.get("src","").strip())
               for s in soup.find_all("script", src=True) if s.get("src","").strip()][:MAX_JS]
    css_queue = [absolutize(final, l.get("href","").strip())
                 for l in soup.find_all("link", href=True)
                 if "stylesheet" in " ".join(l.get("rel", [])).lower()][:MAX_CSS]
    seen_css = set()

    for url in js_urls:
        body, _, _ = fetch_text(url)
        if not body: continue
        all_mp4s |= find_mp4s(body)
        schedule.update(parse_schedule(body))
        endpoints |= find_candidate_endpoints(body)

    while css_queue and len(seen_css) < MAX_CSS:
        css_url = css_queue.pop(0)
        if css_url in seen_css: continue
        seen_css.add(css_url)
        css_text, css_final, _ = fetch_text(css_url)
        if not css_text: continue
        css_links, mp4_links = extract_urls_from_css(css_text, css_final)
        all_mp4s |= mp4_links
        for u in css_links:
            if u not in seen_css and len(seen_css) + len(css_queue) < MAX_CSS:
                css_queue.append(u)

    for ep in sorted(endpoints):
        body, _, _ = fetch_text(ep)
        if not body: continue
        all_mp4s |= find_mp4s(body)
        schedule.update(parse_schedule(body))

    key, pre_key, tz = compute_schedule_key_and_tz()
    line = schedule.get(key)
    if (not line or not line.get("file")) and pre_key:
        pre_line = schedule.get(pre_key)
        if pre_line and pre_line.get("file"):
            tz += 1800
            line = pre_line

    if line and line.get("file"):
        plain = CONTENT_BASE + line["file"]
        with_fragment = f"{plain}#t={tz}"
        print(plain)
        print(with_fragment)
        return 0

    if all_mp4s:
        best_asset = choose_best(all_mp4s)
        if best_asset:
            plain = best_asset
            with_fragment = f"{plain}#t={seconds_into_half_hour()}"
            print(plain)
            print(with_fragment)
            return 0

    probe_set = {f"{CONTENT_BASE}VIDEOBREAKS{n}.mp4" for n in range(1, PROBE_MAX_N+1)}
    best_probe = choose_best(probe_set)
    if best_probe:
        plain = best_probe
        with_fragment = f"{plain}#t={seconds_into_half_hour()}"
        print(plain)
        print(with_fragment)
        return 0

    return 2

if __name__ == "__main__":
    raise SystemExit(main())
