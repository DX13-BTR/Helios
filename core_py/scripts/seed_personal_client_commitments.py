
# core_py/scripts/seed_personal_client_commitments.py (updated)
"""
Seed remaining fixed commitments into task_meta via /api/task-meta/bulk-upsert.

Adds school calendar exceptions (holidays, INSET days, additional closures, early finishes)
for 2025–26 and 2026–27, using static data extracted from Collingwood College PDFs.
- School runs (term-time weekdays) are suppressed on closed days.
- On early-finish days, morning run is emitted as normal; afternoon pickup is moved to the early finish time.
- Exceptions are also emitted as commitments with deadline_type = "school_exception".

Usage (Windows CMD):
  (venv) C:\\Helios> set PYTHONPATH=%CD%
  (venv) C:\\Helios> pip install tzdata requests python-dotenv
  # Preview (print sample, no DB writes)
  (venv) C:\\Helios> python -m core_py.scripts.seed_personal_client_commitments --preview
  # Apply (POST to API)
  (venv) C:\\Helios> python -m core_py.scripts.seed_personal_client_commitments --apply
  # Options
  --window-days 540      Only emit items in next N days (default 540)
  --api-base http://localhost:3333
  --no-checkins          Skip daily check-ins
  --no-school            Skip school runs
  --no-school-exceptions Skip school exception commitments
  --no-payroll           Skip payroll series
  --no-client-blocks     Skip weekly client blocks
"""

from __future__ import annotations
import os, argparse, hashlib, requests
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Tuple, Set

# ---- Timezone (BST/GMT aware) ----
try:
    from zoneinfo import ZoneInfo
except Exception:  # py<3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

TZ = ZoneInfo("Europe/London")

# ---- ENV ----
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

API_BASE = os.getenv("API_BASE", "http://localhost:3333")

# ---- Client code mapping (adjust as needed) ----
CLIENT_CODE = {
    "Randalls": "RAND",
    "AoM": "AOM",
    "IRCM": "IRCM",
    "LPFA": "LPFA",
    "Ascend ADHD": "ASCEND",
    "Empower ADHD": "EMPOWER",
    "Fuller Times": "FULLER",
    "Larkspur": "LARK",
    "Efkaristo": "EFK",
    "Kasorb": "KASORB",
    "KC Swimmers": "KCSWIM",
    "Skills Blueprint": "SKILLS",
    "FAMILY": "FAMILY",
    "OPS": "OPS",
}

# ---- Helpers ----
def iso_local(d: date, t: time) -> str:
    """Return ISO with Europe/London offset for that date/time."""
    dt = datetime.combine(d, t).replace(tzinfo=TZ)
    return dt.isoformat()

def ymd(d: date) -> str:
    return d.strftime("%Y%m%d")

def hhmm(t: time) -> str:
    return f"{t.hour:02d}{t.minute:02d}"

def slug(s: str) -> str:
    out = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
    return "".join(out) or "x"

def task_id(*parts: str) -> str:
    base = ":".join(parts)
    # keep IDs short & deterministic
    if len(base) <= 64:
        return base
    return "fixed:" + hashlib.sha1(base.encode()).hexdigest()[:24]

def daterange(start: date, end: date) -> List[date]:
    d = start; out=[]
    while d <= end:
        out.append(d); d += timedelta(days=1)
    return out

def weekdays_only(dates: List[date]) -> List[date]:
    return [d for d in dates if d.weekday() < 5]

# ---- School calendar (static, from PDFs) ----

# Helper to build simple date sets/ranges
def d(y, m, day) -> date:
    return date(y, m, day)

def drange(a: date, b: date) -> Set[date]:
    return set(daterange(a, b))

# Term ranges are the actual student-in-session windows (excluding holidays).
# We split around half-terms; Christmas/Easter breaks are outside terms.
SCHOOL_TERMS: List[Tuple[date, date]] = [
    # 2025–26
    (d(2025,9,5),  d(2025,10,24)),  # Autumn part 1 (after 2x INSET on 3–4 Sep)
    (d(2025,11,3), d(2025,12,19)),  # Autumn part 2
    (d(2026,1,5),  d(2026,2,13)),   # Spring part 1
    (d(2026,2,23), d(2026,3,27)),   # Spring part 2 (contains INSET on 23 Feb & 27 Mar)
    (d(2026,4,13), d(2026,5,22)),   # Summer part 1
    (d(2026,6,1),  d(2026,7,22)),   # Summer part 2
    # 2026–27
    (d(2026,9,3),  d(2026,10,16)),  # Autumn part 1 (after 2x INSET on 1–2 Sep)
    (d(2026,11,2), d(2026,12,18)),  # Autumn part 2
    (d(2027,1,4),  d(2027,2,12)),   # Spring part 1
    (d(2027,2,22), d(2027,3,25)),   # Spring part 2 (INSET on 22 Feb; closure on 25 Mar)
    (d(2027,4,12), d(2027,5,28)),   # Summer part 1
    (d(2027,6,7),  d(2027,7,28)),   # Summer part 2
]

# Explicit closures (no students): INSET + additional closures
INSET_DAYS: Set[date] = set([
    # 2025–26
    d(2025,9,3), d(2025,9,4), d(2025,10,24), d(2026,2,23), d(2026,3,27),
    # 2026–27
    d(2026,9,1), d(2026,9,2), d(2027,2,22), d(2027,7,27), d(2027,7,28),
])
ADDITIONAL_CLOSURES: Set[date] = set([
    # 2025–26
    d(2025,10,3), d(2025,10,23), d(2025,11,24),
    # 2026–27
    d(2026,11,23), d(2027,3,25), d(2027,7,26),
])

# Early finishes (pickup earlier than normal). Map to specific finish time.
EARLY_FINISH: Dict[date, time] = {
    # 2025–26
    d(2025,9,17): time(13,25),
    d(2025,9,25): time(13,25),
    d(2025,10,2): time(12,20),
    d(2025,12,19): time(12,20),
    d(2026,3,26): time(12,20),
    d(2026,7,22): time(12,20),
    # 2026–27
    d(2026,9,16): time(13,25),
    d(2026,9,24): time(13,25),
    d(2026,10,1): time(12,20),
    d(2026,12,18): time(12,20),
    d(2027,3,24): time(12,20),
    d(2027,7,23): time(12,20),
}

# For visibility in the planner, we also emit "school_exception" commitments:
#  - For each INSET/closure day at 09:00 (info marker)
#  - For each early-finish day at the early pickup time
def build_closed_set() -> Set[date]:
    # Closed when either INSET or additional closure
    return set(INSET_DAYS) | set(ADDITIONAL_CLOSURES)

# ---- Generators ----
def school_term_weekdays(start: date, end: date) -> List[date]:
    out = []
    d0 = start
    while d0 <= end:
        if d0.weekday() < 5:
            out.append(d0)
        d0 += timedelta(days=1)
    return out

def emit_school_runs(window_end: date) -> List[Dict[str,Any]]:
    """
    Morning: 08:05–08:45, Afternoon: 14:55–15:30, Mon–Fri, term-time only.
    Suppressed on INSET/closures; afternoon moved to early-finish time when specified.
    """
    items: List[Dict[str,Any]] = []
    today = datetime.now(TZ).date()
    MORNING_START = time(8,5)
    NORMAL_AFTER_START = time(14,55)

    closed = build_closed_set()

    for start, end in SCHOOL_TERMS:
        rng_start = max(start, today)
        rng_end = min(end, window_end)
        if rng_start > rng_end:
            continue
        for d0 in school_term_weekdays(rng_start, rng_end):
            if d0 in closed:
                # no runs on closed days
                continue
            # morning run always (if term weekday and not closed)
            items.append({
                "task_id": task_id("fixed","schoolrun","morning", ymd(d0), hhmm(MORNING_START)),
                "task_type": "fixed_date",
                "deadline_type": "school_run",
                "fixed_date": iso_local(d0, MORNING_START),
                "client_code": "FAMILY",
                "recurrence_pattern": "term_time",
                "calendar_blocked": 1,
            })

            # afternoon run: early-finish if defined, else normal time
            after_t = EARLY_FINISH.get(d0, NORMAL_AFTER_START)
            items.append({
                "task_id": task_id("fixed","schoolrun","afternoon", ymd(d0), hhmm(after_t)),
                "task_type": "fixed_date",
                "deadline_type": "school_run",
                "fixed_date": iso_local(d0, after_t),
                "client_code": "FAMILY",
                "recurrence_pattern": "term_time",
                "calendar_blocked": 1,
            })
    return items

def emit_school_exceptions(window_end: date) -> List[Dict[str,Any]]:
    """
    Emit commitments to make exceptions visible in planning:
      - INSET/closures at 09:00 (info marker)
      - Early finishes at the early pickup time
    """
    items: List[Dict[str,Any]] = []
    today = datetime.now(TZ).date()
    INFO_TIME = time(9,0)

    # All relevant dates are within term windows or official school calendar,
    # but still clamp to window_end and future-only.
    def in_window(d0: date) -> bool:
        return today <= d0 <= window_end

    # INSET + closures
    for d0 in sorted(build_closed_set()):
        if in_window(d0):
            items.append({
                "task_id": task_id("fixed","schoolrun","exception","closure", ymd(d0), "0900"),
                "task_type": "fixed_date",
                "deadline_type": "school_exception",
                "fixed_date": iso_local(d0, INFO_TIME),
                "client_code": "FAMILY",
                "recurrence_pattern": "school_calendar",
                "calendar_blocked": 1,
            })

    # Early finishes
    for d0, t0 in sorted(EARLY_FINISH.items()):
        if in_window(d0):
            items.append({
                "task_id": task_id("fixed","schoolrun","exception","earlyfinish", ymd(d0), hhmm(t0)),
                "task_type": "fixed_date",
                "deadline_type": "school_exception",
                "fixed_date": iso_local(d0, t0),
                "client_code": "FAMILY",
                "recurrence_pattern": "school_calendar",
                "calendar_blocked": 1,
            })

    return items


def is_school_day(d0: date) -> bool:
    """True if a normal teaching weekday (Mon–Fri within a term) and not closed."""
    if d0.weekday() >= 5:
        return False
    for start, end in SCHOOL_TERMS:
        if start <= d0 <= end:
            return d0 not in build_closed_set()
    return False

def emit_bs_school_runs(window_end: date) -> List[Dict[str,Any]]:
    """
    Emit 'BS School Run' (authentic name) for weekdays that are NOT normal school days.
    Start from Mon 19 Aug 2025 onward, and apply through all future school holidays.
    """
    items: List[Dict[str,Any]] = []
    today = datetime.now(TZ).date()
    start_from = max(today, date(2025,8,19))
    end_on = window_end
    BS_TIME = time(8,5)

    d0 = start_from
    while d0 <= end_on:
        if d0.weekday() < 5 and not is_school_day(d0):
            items.append({
                "task_id": task_id("fixed","bs_school_run", ymd(d0), hhmm(BS_TIME)),
                "task_type": "fixed_date",
                "deadline_type": "bs_school_run",
                "fixed_date": iso_local(d0, BS_TIME),
                "client_code": "FAMILY",
                "recurrence_pattern": "school_holiday",
                "calendar_blocked": 1,
                "notes": "BS School Run (holiday routine)",
            })
        d0 += timedelta(days=1)
    return items

def emit_daily_checkins(window_end: date) -> List[Dict[str,Any]]:
    """ Daily check-ins (never move):
      09:00 (30m), 13:00 (15m), 17:30 (30m), every day.
    We store the start times; durations handled by calendar logic.
    """
    items: List[Dict[str,Any]] = []
    today = datetime.now(TZ).date()
    times = [
        ("morning", time(9,0)),
        ("midday",  time(13,0)),
        ("eod",     time(17,30)),
    ]
    for d0 in daterange(today, window_end):
        for label, tt in times:
            items.append({
                "task_id": task_id("fixed","checkin",label, ymd(d0), hhmm(tt)),
                "task_type": "fixed_date",
                "deadline_type": "daily_checkin",
                "fixed_date": iso_local(d0, tt),
                "client_code": "OPS",
                "recurrence_pattern": "daily",
                "calendar_blocked": 1,
            })
    return items


def emit_health_routines(window_end: date) -> List[Dict[str,Any]]:
    """
    Daily health routines (fixed, non-negotiable).
    Emits fixed_date items with deadline_type='health_routine' and client_code='PERSONAL'.
    """
    items: List[Dict[str,Any]] = []
    today = datetime.now(TZ).date()
    times = [
        ("insulin_rybelsus_morning", time(6,45)),
        ("meds_morning",             time(7,30)),
        ("bsl_morning",              time(7,30)),
        ("bsl_lunch",                time(13,0)),
        ("bsl_predinner",            time(18,0)),
        ("meds_insulin_evening",     time(18,0)),
        ("bsl_bedtime",              time(21,45)),
    ]
    for d0 in daterange(today, window_end):
        for label, tt in times:
            items.append({
                "task_id": task_id("fixed","health",label, ymd(d0), hhmm(tt)),
                "task_type": "fixed_date",
                "deadline_type": "health_routine",
                "fixed_date": iso_local(d0, tt),
                "client_code": "PERSONAL",
                "recurrence_pattern": "daily",
                "calendar_blocked": 1,
                "notes": "Daily health routine (protected)",
            })
    return items

def emit_pet_care(window_end: date) -> List[Dict[str,Any]]:
    """
    Daily Loki pet care routines (fixed, non-negotiable).
    Emits fixed_date items with deadline_type='pet_care' and client_code='FAMILY'.
    """
    items: List[Dict[str,Any]] = []
    today = datetime.now(TZ).date()
    times = [
        ("loki_breakfast",      time(6,45)),
        ("loki_snack_1",        time(10,45)),
        ("loki_snack_2",        time(12,45)),
        ("loki_snack_3",        time(15,0)),
        ("loki_dinner",         time(17,45)),
        ("litter_tray_scoop",   time(19,0)),
    ]
    for d0 in daterange(today, window_end):
        for label, tt in times:
            items.append({
                "task_id": task_id("fixed","petcare",label, ymd(d0), hhmm(tt)),
                "task_type": "fixed_date",
                "deadline_type": "pet_care",
                "fixed_date": iso_local(d0, tt),
                "client_code": "FAMILY",
                "recurrence_pattern": "daily",
                "calendar_blocked": 1,
                "notes": "Daily Loki care (protected)",
            })
    return items

def emit_payroll_and_blocks(window_days: int) -> List[Dict[str,Any]]:
    """
    Payroll + weekly client blocks.
    - Randalls & AoM: every 4 weeks (28-day cadence) from anchors.
    - Others: true monthly series.
    - KC Swimmers & Skills Blueprint: last work-week of each month (chosen weekday).
    - Kasorb (Mon/Tue 13:00) & LPFA (Thu 13:00): weekly client blocks.
    """
    from calendar import monthrange

    items: List[Dict[str,Any]] = []
    now = datetime.now(TZ)
    today = now.date()
    window_end = today + timedelta(days=window_days)

    def monthly_dates(start_on: date, day_of_month: int) -> List[date]:
        out = []
        y, m = start_on.year, start_on.month
        while True:
            dmax = monthrange(y, m)[1]
            dd = date(y, m, min(day_of_month, dmax))
            if dd >= start_on and dd <= window_end:
                out.append(dd)
            if (y, m) >= (window_end.year, window_end.month):
                break
            m += 1
            if m == 13:
                m = 1
                y += 1
        return out

    def every_4_weeks(start_on: date) -> List[date]:
        """28-day cadence within the window, anchored at start_on."""
        d0 = start_on
        if d0 < today:
            delta = (today - d0).days
            steps = (delta + 27) // 28  # ceil
            d0 = d0 + timedelta(days=28 * steps)
        out = []
        while d0 <= window_end:
            out.append(d0)
            d0 = d0 + timedelta(days=28)
        return out

    def last_weekday_of_month(y: int, m: int, weekday: int) -> date:
        """
        Last given weekday (0=Mon..6=Sun) in y-m, moved back to Fri if it lands on weekend.
        """
        last_day = monthrange(y, m)[1]
        dd = date(y, m, last_day)
        delta = (dd.weekday() - weekday) % 7
        dd = dd - timedelta(days=delta)
        while dd.weekday() > 4:
            dd = dd - timedelta(days=1)
        return dd

    # ---- FOUR-WEEKLY PAYROLL ----
    FOURW = [
        ("Randalls", "RAND", date(2025, 8, 18), time(9, 0)),  # Mon anchor
        ("AoM",      "AOM",  date(2025, 8, 21), time(9, 0)),  # Thu anchor
    ]
    for name, code, start_on, tt in FOURW:
        for d0 in every_4_weeks(start_on):
            items.append({
                "task_id": task_id("fixed","payroll","4w", slug(name), ymd(d0)),
                "task_type": "fixed_date",
                "deadline_type": "payroll",
                "fixed_date": iso_local(d0, tt),
                "client_code": code,
                "recurrence_pattern": "every_4_weeks",
                "calendar_blocked": 1,
            })

    # ---- MONTHLY PAYROLL ----
    from calendar import monthrange as mr
    MONTHLY = [
        # name, code, day_of_month, first_due (anchor)
        ("IRCM",            "IRCM",    23, date(2025, 8, 23)),
        ("LPFA",            "LPFA",    24, date(2025, 8, 24)),
        ("Ascend ADHD",     "ASCEND",  31, date(2025, 8, 31)),
        ("Empower ADHD",    "EMPOWER", 31, date(2025, 8, 31)),
        ("Fuller Times",    "FULLER",  31, date(2025, 8, 31)),
        ("Larkspur",        "LARK",    31, date(2025, 8, 31)),
        ("Efkaristo",       "EFK",     15, date(2025, 9, 15)),
    ]
    for name, code, dom, start_from in MONTHLY:
        start = max(start_from, today)
        # compute monthly dates
        y, m = start.year, start.month
        while True:
            dmax = mr(y, m)[1]
            dd = date(y, m, min(dom, dmax))
            if dd >= start and dd <= window_end:
                items.append({
                    "task_id": task_id("fixed","payroll", slug(name), ymd(dd)),
                    "task_type": "fixed_date",
                    "deadline_type": "payroll",
                    "fixed_date": iso_local(dd, time(9,0)),
                    "client_code": code,
                    "recurrence_pattern": "monthly",
                    "calendar_blocked": 1,
                })
            if (y, m) >= (window_end.year, window_end.month):
                break
            m += 1
            if m == 13:
                m = 1
                y += 1

    # ---- LAST-WEEK-OF-MONTH PAYROLL ----
    LAST_WEEK = [
        ("KC Swimmers",      "KCSWIM", 1, time(9,0)),  # Tue of last work week
        ("Skills Blueprint", "SKILLS", 3, time(9,0)),  # Thu of last work week
    ]
    y, m = today.year, today.month
    end_y, end_m = window_end.year, window_end.month
    while (y, m) <= (end_y, end_m):
        for name, code, wd, tt in LAST_WEEK:
            dd = last_weekday_of_month(y, m, wd)
            if today <= dd <= window_end:
                items.append({
                    "task_id": task_id("fixed","payroll", slug(name), ymd(dd)),
                    "task_type": "fixed_date",
                    "deadline_type": "payroll",
                    "fixed_date": iso_local(dd, tt),
                    "client_code": code,
                    "recurrence_pattern": "last_week",
                    "calendar_blocked": 1,
                })
        m += 1
        if m == 13:
            m = 1
            y += 1

    # ---- WEEKLY CLIENT TIME BLOCKS ----
    for i in range(0, window_days + 1):
        d0 = today + timedelta(days=i)
        if d0.weekday() in (0, 1):  # Mon/Tue
            items.append({
                "task_id": task_id("fixed","clientblock","kasorb", ymd(d0), "1300"),
                "task_type": "fixed_date",
                "deadline_type": "client_block",
                "fixed_date": iso_local(d0, time(13,0)),
                "client_code": "KASORB",
                "recurrence_pattern": "weekly",
                "calendar_blocked": 1,
            })
        if d0.weekday() == 3:  # Thu
            items.append({
                "task_id": task_id("fixed","clientblock","lpfa", ymd(d0), "1300"),
                "task_type": "fixed_date",
                "deadline_type": "client_block",
                "fixed_date": iso_local(d0, time(13,0)),
                "client_code": "LPFA",
                "recurrence_pattern": "weekly",
                "calendar_blocked": 1,
            })

    # keep only inside window
    out = []
    for it in items:
        dt = datetime.fromisoformat(it["fixed_date"].replace("Z","+00:00"))
        if dt.date() <= window_end:
            out.append(it)
    return out

# ---- POST in batches ----
def chunked(seq: List[Dict[str,Any]], n: int) -> List[List[Dict[str,Any]]]:
    return [seq[i:i+n] for i in range(0, len(seq), n)]

def bulk_upsert(items: List[Dict[str,Any]], api_base: str, batch_size: int = 500) -> Dict[str, Any]:
    url = f"{api_base.rstrip('/')}/api/task-meta/bulk-upsert"
    total = 0
    for batch in chunked(items, batch_size):
        r = requests.post(url, json=batch, timeout=120)
        r.raise_for_status()
        try:
            resp = r.json()
        except Exception:
            resp = {"ok": True, "upserted": len(batch)}
        total += resp.get("upserted", len(batch))
    return {"ok": True, "upserted": total}

# ---- Main ----
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=540)
    ap.add_argument("--api-base", default=API_BASE)
    ap.add_argument("--apply", action="store_true", help="POST to /api/task-meta/bulk-upsert")
    ap.add_argument("--preview", action="store_true", help="Print sample and counts; no POST")
    ap.add_argument("--no-checkins", action="store_true")
    ap.add_argument("--no-school", action="store_true")
    ap.add_argument("--no-school-exceptions", action="store_true")
    ap.add_argument("--no-bs-school", action="store_true")
    ap.add_argument("--no-payroll", action="store_true")
    ap.add_argument("--no-client-blocks", action="store_true")
    ap.add_argument("--no-health", action="store_true")
    ap.add_argument("--no-pet", action="store_true")
    args = ap.parse_args()

    now = datetime.now(TZ)
    window_end = now.date() + timedelta(days=args.window_days)

    items: List[Dict[str,Any]] = []

    if not args.no_school:
        items += emit_school_runs(window_end)
        if not args.no_school_exceptions:
            items += emit_school_exceptions(window_end)
    # BS School Runs (holiday mornings)
    if not args.no_bs_school:
        items += emit_bs_school_runs(window_end)
    if not args.no_checkins:
        items += emit_daily_checkins(window_end)
    if not args.no_health:
        items += emit_health_routines(window_end)
    if not args.no_pet:
        items += emit_pet_care(window_end)
    if not args.no_payroll or not args.no_client_blocks:
        items += emit_payroll_and_blocks(args.window_days)

    # combine & dedupe by task_id
    by_id: Dict[str, Dict[str,Any]] = {}
    for it in items:
        by_id[it["task_id"]] = it
    items = list(by_id.values())

    # summary
    from collections import Counter
    by_type = Counter([it["deadline_type"] for it in items])
    print(f"• generated items (within {args.window_days}d): {len(items)}")
    for k,v in by_type.most_common():
        print(f"  - {k}: {v}")

    # preview or apply
    if args.preview or not args.apply:
        print("Sample:")
        for it in list(items)[:12]:
            print(it)
        if not args.apply:
            print("💡 Dry run only. Use --apply to POST to the API.")
            return

    # apply
    try:
        res = bulk_upsert(items, args.api_base, batch_size=500)
        print("✅ Upserted:", res)
    except Exception as e:
        print("❌ POST failed:", e)
        print("API:", f"{args.api_base}/api/task-meta/bulk-upsert")

if __name__ == "__main__":
    main()
