import os, json, time, re, requests
from pathlib import Path

ALLOWLIST_URL = os.getenv("ALLOWLIST_URL", "http://127.0.0.1:3333/api/allowlist")
CACHE_FILE    = Path(os.getenv("ALLOWLIST_CACHE", "allowlist_cache.json"))
CACHE_TTL_SEC = int(os.getenv("ALLOWLIST_TTL_SEC", str(6*3600)))

_email_re = re.compile(r'^\s*([^@]+)@([^@]+)\s*$')

def _normalize_email(addr: str) -> str:
    if not addr: return ""
    addr = addr.strip().lower()
    m = _email_re.match(addr)
    if not m: return addr
    local, dom = m.group(1), m.group(2)
    local = local.split('+', 1)[0]
    return f"{local}@{dom}"

def _domain_of(addr: str) -> str:
    m = _email_re.match(addr or "")
    return (m.group(2) if m else "").lower().strip()

def _read_cache():
    if not CACHE_FILE.exists(): return None
    try:
        st = CACHE_FILE.stat()
        if time.time() - st.st_mtime > CACHE_TTL_SEC: return None
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except: return None

def _write_cache(data: dict):
    try: CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except: pass

def fetch_allowlist() -> dict:
    cached = _read_cache()
    params = {}
    if cached and "etag" in cached:
        params["ifNoneMatch"] = cached["etag"]
    try:
        r = requests.get(ALLOWLIST_URL, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        if data.get("not_modified"):
            return cached or data
        _write_cache(data)
        return data
    except Exception:
        if cached: return cached
        raise

def build_checker(allowlist: dict):
    emails = set(_normalize_email(e) for e in allowlist.get("emails", []))
    exact, wild = set(), set()
    for d in allowlist.get("domains", []):
        dom = (d.get("domain") or "").lower().strip()
        if not dom: continue
        (wild if d.get("wildcard") else exact).add(dom)

    def is_allowed(sender_email: str) -> bool:
        e = _normalize_email(sender_email)
        if not e: return False
        if e in emails: return True
        dom = _domain_of(e)
        return dom in exact or any(dom == wd or dom.endswith("." + wd) for wd in wild)

    return is_allowed
