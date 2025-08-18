# core_py/utils/contacts_norm.py
import re, uuid

EMAIL_RE = re.compile(r'^\s*([^@]+)@([^@]+)\s*$')

def uuid4() -> str:
    import uuid as _uuid
    return str(_uuid.uuid4())

def normalize_email(addr: str) -> str:
    if not addr: return ""
    addr = addr.strip().lower()
    m = EMAIL_RE.match(addr)
    if not m: return addr
    local, domain = m.group(1), m.group(2)
    local = local.split("+", 1)[0]  # strip +tag
    return f"{local}@{domain}"

def normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower()
