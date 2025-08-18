#!/usr/bin/env python3
"""
Helios Block Scheduler v1 — Personal-aware (Motion-style)

Generates contextual work blocks between fixed commitments and writes them to the
"Helios Flexible Suggestions" calendar.

Key behavior:
- Work buckets placed in core hours (Mon–Fri only)
- PERSONAL bucket placed inside configurable personal windows (any day)
- Weekly weights are interpreted as "per week" and auto-scale to --window-days
- Duration bands, placement preferences, caps, and hard rules enforced
- Idempotent writes via extendedProperties.private metadata
"""

from __future__ import annotations
import argparse
import dataclasses
import datetime as dt
import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple, Optional

from dotenv import load_dotenv
load_dotenv()

# Use the centralized ClickUp client that returns plain dicts
from core_py.integrations.clickup_client import ClickUpClient as RealClickUpClient

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

FIXED_CALENDAR_ID = os.getenv("FIXED_CALENDAR_ID")
FLEXIBLE_CALENDAR_ID = os.getenv("FLEXIBLE_CALENDAR_ID")

# =========================
# Domain model
# =========================

class BlockType(str, Enum):
    CLIENT_DEEP_WORK = "client_deep_work"
    SYSTEMS_DEVELOPMENT = "systems_development"
    MARKETING_CREATIVE = "marketing_creative"
    ADMIN_PROCESSING = "admin_processing"
    PERSONAL = "personal"

@dataclass
class BlockRule:
    duration_min: int
    duration_max: int
    placements: List[str]  # e.g., ["morning","late_afternoon","gaps"] or ["personal_window"]

@dataclass
class HardRules:
    min_contiguous_minutes_for_systems: int = 120
    cap_blocks_per_day: Dict[BlockType, int] = dataclasses.field(default_factory=lambda: {
        BlockType.SYSTEMS_DEVELOPMENT: 1,
        BlockType.ADMIN_PROCESSING: 2,
        BlockType.PERSONAL: 2,
    })

@dataclass
class PersonalWindows:
    """Personal windows per weekday (0=Mon..6=Sun), list of [HH:MM, HH:MM)."""
    by_weekday: Dict[int, List[Tuple[dt.time, dt.time]]] = dataclasses.field(default_factory=dict)

@dataclass
class SchedulerConfig:
    # Work core hours
    core_start: dt.time = dt.time(9, 0)
    core_end: dt.time = dt.time(18, 0)

    # Overflow (optional work extension; not used in placement by default)
    overflow_enabled: bool = False
    overflow_start: dt.time = dt.time(18, 0)
    overflow_end: dt.time = dt.time(21, 0)

    weekly_weights: Dict[BlockType, int] = dataclasses.field(default_factory=lambda: {
        BlockType.CLIENT_DEEP_WORK: 7,
        BlockType.SYSTEMS_DEVELOPMENT: 3,
        BlockType.MARKETING_CREATIVE: 2,
        BlockType.ADMIN_PROCESSING: 5,
        BlockType.PERSONAL: 4,
    })
    rules: Dict[BlockType, BlockRule] = dataclasses.field(default_factory=lambda: {
        BlockType.CLIENT_DEEP_WORK:    BlockRule(90, 120, ["morning"]),
        BlockType.SYSTEMS_DEVELOPMENT: BlockRule(120, 180, ["mid_morning","early_afternoon"]),
        BlockType.MARKETING_CREATIVE:  BlockRule(60, 90, ["afternoon"]),
        BlockType.ADMIN_PROCESSING:    BlockRule(30, 60, ["late_afternoon","gaps"]),
        BlockType.PERSONAL:            BlockRule(30, 90, ["personal_window"]),
    })
    hard: HardRules = HardRules()
    personal_windows: PersonalWindows = dataclasses.field(default_factory=PersonalWindows)

@dataclass
class Task:
    id: str
    title: str
    block_type: BlockType
    remaining_minutes: int
    due: Optional[dt.datetime] = None
    priority: Optional[int] = None  # lower is higher

@dataclass
class Event:
    start: dt.datetime
    end: dt.datetime
    summary: str
    description: str
    block_type: BlockType
    task_ids: List[str]
    task_titles: List[str]

# =========================
# Config loading
# =========================

DEFAULT_YAML = """
core_hours:
  start: "09:00"
  end:   "18:00"

overflow_hours:
  enabled: false
  start: "18:00"
  end:   "21:00"

weights:
  client_deep_work: 7
  systems_development: 3
  marketing_creative: 2
  admin_processing: 5
  personal: 4

durations:
  client_deep_work: [90, 120]
  systems_development: [120, 180]
  marketing_creative: [60, 90]
  admin_processing: [30, 60]
  personal: [30, 90]

placement:
  client_deep_work:     ["morning"]
  systems_development:  ["mid_morning","early_afternoon"]
  marketing_creative:   ["afternoon"]
  admin_processing:     ["late_afternoon","gaps"]
  # 'personal' uses special placement 'personal_window'

hard_rules:
  min_contiguous_minutes_for_systems: 120
  cap_blocks_per_day:
    systems_development: 1
    admin_processing: 2
    personal: 2

# Personal windows per weekday (0=Mon..6=Sun)
personal_windows:
  0: [["07:00","08:30"], ["12:30","13:30"], ["17:30","20:00"]]
  1: [["07:00","08:30"], ["12:30","13:30"], ["17:30","20:00"]]
  2: [["07:00","08:30"], ["12:30","13:30"], ["17:30","20:00"]]
  3: [["07:00","08:30"], ["12:30","13:30"], ["17:30","20:00"]]
  4: [["07:00","08:30"], ["12:30","13:30"], ["17:30","20:00"]]
  5: [["08:00","12:00"], ["16:00","20:00"]]
  6: [["09:00","12:00"], ["16:00","19:00"]]
"""

def parse_time(hhmm: str) -> dt.time:
    h, m = [int(x) for x in hhmm.split(":")]
    return dt.time(h, m)

def _parse_windows(raw: Dict[str, List[List[str]]]) -> PersonalWindows:
    out: Dict[int, List[Tuple[dt.time, dt.time]]] = {}
    for k, arr in (raw or {}).items():
        try:
            wd = int(k)
        except Exception:
            continue
        spans: List[Tuple[dt.time, dt.time]] = []
        for span in arr or []:
            if not span or len(span) != 2:  # defensive
                continue
            s, e = parse_time(span[0]), parse_time(span[1])
            spans.append((s, e))
        out[wd] = spans
    return PersonalWindows(by_weekday=out)

def load_config(path: Optional[str]) -> SchedulerConfig:
    if path and os.path.exists(path) and yaml:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    else:
        data = yaml.safe_load(DEFAULT_YAML) if yaml else None

    cfg = SchedulerConfig()
    if not data:
        return cfg

    core = data.get("core_hours", {})
    if "start" in core: cfg.core_start = parse_time(core["start"])
    if "end" in core: cfg.core_end = parse_time(core["end"])

    of = data.get("overflow_hours", {})
    cfg.overflow_enabled = bool(of.get("enabled", False))
    if "start" in of: cfg.overflow_start = parse_time(of["start"])
    if "end" in of: cfg.overflow_end = parse_time(of["end"])

    w = data.get("weights", {})
    if w:
        cfg.weekly_weights.update({
            BlockType.CLIENT_DEEP_WORK: int(w.get("client_deep_work", cfg.weekly_weights[BlockType.CLIENT_DEEP_WORK])),
            BlockType.SYSTEMS_DEVELOPMENT: int(w.get("systems_development", cfg.weekly_weights[BlockType.SYSTEMS_DEVELOPMENT])),
            BlockType.MARKETING_CREATIVE: int(w.get("marketing_creative", cfg.weekly_weights[BlockType.MARKETING_CREATIVE])),
            BlockType.ADMIN_PROCESSING: int(w.get("admin_processing", cfg.weekly_weights[BlockType.ADMIN_PROCESSING])),
            BlockType.PERSONAL: int(w.get("personal", cfg.weekly_weights[BlockType.PERSONAL])),
        })

    durations = data.get("durations", {})
    placements = data.get("placement", {})
    def mk_rule(bt: BlockType, d_key: str, p_key: str) -> BlockRule:
        dvals = durations.get(d_key)
        if dvals:
            dmin, dmax = int(dvals[0]), int(dvals[1])
        else:
            r = cfg.rules[bt]; dmin, dmax = r.duration_min, r.duration_max
        pvals = placements.get(p_key, cfg.rules[bt].placements)
        return BlockRule(dmin, dmax, list(pvals))
    cfg.rules = {
        BlockType.CLIENT_DEEP_WORK:    mk_rule(BlockType.CLIENT_DEEP_WORK, "client_deep_work", "client_deep_work"),
        BlockType.SYSTEMS_DEVELOPMENT: mk_rule(BlockType.SYSTEMS_DEVELOPMENT, "systems_development", "systems_development"),
        BlockType.MARKETING_CREATIVE:  mk_rule(BlockType.MARKETING_CREATIVE, "marketing_creative", "marketing_creative"),
        BlockType.ADMIN_PROCESSING:    mk_rule(BlockType.ADMIN_PROCESSING, "admin_processing", "admin_processing"),
        BlockType.PERSONAL:            mk_rule(BlockType.PERSONAL, "personal", "personal"),
    }

    hr = data.get("hard_rules", {})
    cap_map = hr.get("cap_blocks_per_day", {})
    cfg.hard = HardRules(
        min_contiguous_minutes_for_systems=int(hr.get("min_contiguous_minutes_for_systems", cfg.hard.min_contiguous_minutes_for_systems)),
        cap_blocks_per_day={
            BlockType.SYSTEMS_DEVELOPMENT: int(cap_map.get("systems_development", cfg.hard.cap_blocks_per_day[BlockType.SYSTEMS_DEVELOPMENT])),
            BlockType.ADMIN_PROCESSING: int(cap_map.get("admin_processing", cfg.hard.cap_blocks_per_day[BlockType.ADMIN_PROCESSING])),
            BlockType.PERSONAL: int(cap_map.get("personal", cfg.hard.cap_blocks_per_day[BlockType.PERSONAL])),
        }
    )

    cfg.personal_windows = _parse_windows(data.get("personal_windows", {}))
    return cfg

# =========================
# Time utilities
# =========================

@dataclass
class Interval:
    start: dt.datetime
    end: dt.datetime
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)
    def split(self, minutes: int) -> Tuple["Interval", Optional["Interval"]]:
        take = min(self.minutes(), minutes)
        first = Interval(self.start, self.start + dt.timedelta(minutes=take))
        rest = None
        if self.end > first.end:
            rest = Interval(first.end, self.end)
        return first, rest

def as_utc(d: dt.datetime) -> dt.datetime:
    return d if d.tzinfo is not None else d.replace(tzinfo=dt.timezone.utc)

def clamp(day: dt.date, start: dt.time, end: dt.time) -> Interval:
    return Interval(as_utc(dt.datetime.combine(day, start)), as_utc(dt.datetime.combine(day, end)))

def subtract_busy(free: Interval, busies: List[Interval]) -> List[Interval]:
    pieces = [free]
    for b in sorted(busies, key=lambda x: x.start):
        nxt: List[Interval] = []
        for p in pieces:
            if b.end <= p.start or b.start >= p.end:
                nxt.append(p); continue
            if b.start > p.start:
                nxt.append(Interval(p.start, b.start))
            if b.end < p.end:
                nxt.append(Interval(b.end, p.end))
        pieces = [x for x in nxt if x.end > x.start]
    return pieces

def bucket_for_time(t: dt.time) -> str:
    if t < dt.time(11, 0): return "morning" if t < dt.time(10, 30) else "mid_morning"
    if t < dt.time(14, 30): return "early_afternoon"
    if t < dt.time(16, 30): return "afternoon"
    return "late_afternoon"

def in_personal_window(cfg: SchedulerConfig, day: dt.date, iv: Interval) -> bool:
    spans = cfg.personal_windows.by_weekday.get(day.weekday(), [])
    if not spans:
        return True  # if not configured, allow
    st, en = iv.start.time(), iv.end.time()
    for s, e in spans:
        if st >= s and en <= e:
            return True
    return False

# =========================
# Scheduling core
# =========================

@dataclass
class Demand:
    minutes_by_block: Dict[BlockType, int]
    tasks_by_block: Dict[BlockType, List[Task]]

def _to_dt_utc_from_ms(ms: int | None) -> Optional[dt.datetime]:
    if not ms: return None
    try: return dt.datetime.fromtimestamp(int(ms)/1000, tz=dt.timezone.utc)
    except Exception: return None

def _coerce_bucket(key: str) -> Optional[BlockType]:
    k = (key or "").lower()
    if k in ("client_deep_work","clients","client"): return BlockType.CLIENT_DEEP_WORK
    if k in ("systems_development","systems","dev","efkaristo"): return BlockType.SYSTEMS_DEVELOPMENT
    if k in ("marketing_creative","marketing","creative"): return BlockType.MARKETING_CREATIVE
    if k in ("admin_processing","admin","ops"): return BlockType.ADMIN_PROCESSING
    if k in ("personal",): return BlockType.PERSONAL
    return None

def _adapt_grouped_for_scheduler(grouped_plain: dict) -> Dict[BlockType, List[Task]]:
    out: Dict[BlockType, List[Task]] = {bt: [] for bt in BlockType}
    for k, arr in (grouped_plain or {}).items():
        bt = _coerce_bucket(k)
        if not bt: continue
        for d in (arr or []):
            rid = str(d.get("id",""))
            title = d.get("name") or d.get("title") or "(Untitled)"
            due = _to_dt_utc_from_ms(d.get("due_date"))
            pr = d.get("priority")
            try: pr = None if pr is None else int(pr)
            except Exception: pr = None
            rem = d.get("remaining_minutes")
            if rem is None:
                est = d.get("time_estimate") or 0
                spent = d.get("time_spent") or 0
                try: rem = max(0, int((int(est) - int(spent)) / 60000))
                except Exception: rem = 30
            out[bt].append(Task(id=rid, title=title, block_type=bt, remaining_minutes=int(rem), due=due, priority=pr))
        out[bt].sort(key=lambda t: (t.priority or 99, t.due or dt.datetime.max.replace(tzinfo=dt.timezone.utc)))
    return out

def compute_demand(tasks_grouped: Dict[BlockType, List[Task]]) -> Demand:
    out = {bt: sum(max(0, t.remaining_minutes) for t in lst) for bt, lst in tasks_grouped.items()}
    return Demand(minutes_by_block=out, tasks_by_block=tasks_grouped)

@dataclass
class PlanDay:
    date: dt.date
    blocks: List[Event]
    counts: Dict[BlockType, int]

@dataclass
class Plan:
    days: List[PlanDay]

def plan_week(
    start_date: dt.date,
    num_days: int,
    cfg: SchedulerConfig,
    fixed_events_fetcher,
    clickup_grouped_tasks: Dict[BlockType, List[Task]],
) -> Plan:
    """Compute a plan of blocks across a window starting at start_date.
    - Work buckets (client/systems/marketing/admin) are placed in core hours on weekdays.
    - PERSONAL is placed only within configured personal windows (any day).
    - Weekly weights are scaled to the requested window length.
    """
    import math

    demand = compute_demand(clickup_grouped_tasks)

    # Scale weekly weights to the planning window length (e.g., 14d ≈ 2x)
    scale = max(1.0, float(num_days) / 7.0)
    scaled_weekly: Dict[BlockType, int] = {
        bt: int(math.ceil(cfg.weekly_weights.get(bt, 0) * scale)) for bt in BlockType
    }

    days: List[PlanDay] = []
    scheduled_counts: Dict[BlockType, int] = {bt: 0 for bt in BlockType}
    dtmax_utc = dt.datetime.max.replace(tzinfo=dt.timezone.utc)

    for i in range(num_days):
        day = start_date + dt.timedelta(days=i)

        # Build fixed events once per day
        fixed = [Interval(ev["start"], ev["end"]) for ev in fixed_events_fetcher(day)]

        # Weekdays: place work in core; weekends: skip work buckets
        work_free: List[Interval] = []
        if day.weekday() < 5:  # 0=Mon .. 4=Fri
            core = clamp(day, cfg.core_start, cfg.core_end)
            work_free = subtract_busy(core, fixed)
            work_free.sort(key=lambda x: x.start)

        day_blocks: List[Event] = []
        cap_today: Dict[BlockType, int] = {bt: 0 for bt in BlockType}

        def can_place(bt: BlockType, interval: Interval, minutes: int) -> bool:
            # caps
            cap = cfg.hard.cap_blocks_per_day.get(bt, 99)
            if cap_today[bt] >= cap:
                return False
            # systems min contiguous
            if bt == BlockType.SYSTEMS_DEVELOPMENT and minutes < cfg.hard.min_contiguous_minutes_for_systems:
                return False
            # placement buckets
            bucket = bucket_for_time(interval.start.time())
            rule = cfg.rules[bt]
            if bt == BlockType.PERSONAL:
                # must be inside an explicit personal window
                return "personal_window" in rule.placements and in_personal_window(cfg, day, interval)
            # otherwise honor placement list, allow "gaps" as wildcard
            return (bucket in rule.placements) or ("gaps" in rule.placements)

        def allocate(bt: BlockType, iv: Interval, minutes: int) -> Tuple[Optional[Event], Optional[Interval]]:
            tasks = sorted(
                demand.tasks_by_block.get(bt, []),
                key=lambda t: (t.priority or 99, t.due or dtmax_utc),
            )
            if not tasks:
                return None, iv

            take_iv, rest_iv = iv.split(minutes)

            # Accumulate unique task IDs and titles, decrement remaining_minutes
            task_ids: List[str] = []
            task_titles: List[str] = []
            remaining = take_iv.minutes()
            seen: set[str] = set()

            for tsk in tasks:
                if remaining <= 0:
                    break
                if tsk.remaining_minutes <= 0:
                    continue

                use = min(remaining, tsk.remaining_minutes)
                tsk.remaining_minutes -= use
                remaining -= use

                if tsk.id not in seen:
                    task_ids.append(tsk.id)
                    task_titles.append(tsk.title)
                    seen.add(tsk.id)

            if not task_ids:
                return None, iv

            ev = Event(
                start=take_iv.start,
                end=take_iv.end,
                summary=summary_for(bt, take_iv, task_titles),
                description=description_for(bt, task_ids, task_titles),
                block_type=bt,
                task_ids=task_ids,
                task_titles=task_titles,
            )
            cap_today[bt] += 1
            scheduled_counts[bt] += 1
            demand.minutes_by_block[bt] = max(0, demand.minutes_by_block[bt] - take_iv.minutes())
            return ev, rest_iv

        def prefer_list_for_bucket(bucket: str) -> List[BlockType]:
            if bucket in ("morning","mid_morning"):
                return [BlockType.CLIENT_DEEP_WORK, BlockType.SYSTEMS_DEVELOPMENT, BlockType.ADMIN_PROCESSING]
            if bucket in ("early_afternoon","afternoon"):
                return [BlockType.MARKETING_CREATIVE, BlockType.CLIENT_DEEP_WORK, BlockType.ADMIN_PROCESSING]
            return [BlockType.ADMIN_PROCESSING, BlockType.CLIENT_DEEP_WORK]

        # 1) Place work blocks (weekdays, in core)
        for iv in list(work_free):
            cursor = iv
            while cursor and cursor.minutes() >= 30:
                bucket = bucket_for_time(cursor.start.time())
                prefs = prefer_list_for_bucket(bucket)
                placed = False

                for bt in prefs:
                    weekly_target = scaled_weekly.get(bt, 999)
                    if scheduled_counts.get(bt, 0) >= weekly_target:
                        continue
                    rule = cfg.rules[bt]
                    candidate = min(rule.duration_max, cursor.minutes())
                    candidate = max(candidate, rule.duration_min)
                    candidate = min(candidate, cursor.minutes())
                    if candidate < rule.duration_min:
                        continue
                    if demand.minutes_by_block.get(bt, 0) <= 0:
                        continue
                    if not can_place(bt, cursor, candidate):
                        continue

                    ev, rest = allocate(bt, cursor, candidate)
                    if ev:
                        day_blocks.append(ev)
                        cursor = rest
                        placed = True
                        break

                if not placed:
                    # Gap filler: ADMIN if there is demand
                    if cursor.minutes() >= 30 and demand.minutes_by_block.get(BlockType.ADMIN_PROCESSING, 0) > 0:
                        bt = BlockType.ADMIN_PROCESSING
                        rule = cfg.rules[bt]
                        mins = min(rule.duration_max, max(rule.duration_min, cursor.minutes()))
                        mins = min(mins, cursor.minutes())
                        if can_place(bt, cursor, mins):
                            ev, rest = allocate(bt, cursor, mins)
                            if ev:
                                day_blocks.append(ev)
                                cursor = rest
                                continue
                    break  # no placement made; stop consuming this interval

        # 2) PERSONAL inside configured windows (any day), subtracting fixed events
        p_spans = cfg.personal_windows.by_weekday.get(day.weekday(), [])
        if p_spans and demand.minutes_by_block.get(BlockType.PERSONAL, 0) > 0:
            personal_free: List[Interval] = []
            for s, e in p_spans:
                base = clamp(day, s, e)
                personal_free += subtract_busy(base, fixed)
            personal_free.sort(key=lambda x: x.start)

            for iv in list(personal_free):
                cursor = iv
                while cursor and cursor.minutes() >= cfg.rules[BlockType.PERSONAL].duration_min:
                    bt = BlockType.PERSONAL
                    weekly_target = scaled_weekly.get(bt, 999)
                    if scheduled_counts.get(bt, 0) >= weekly_target:
                        break
                    rule = cfg.rules[bt]
                    mins = min(rule.duration_max, max(rule.duration_min, cursor.minutes()))
                    mins = min(mins, cursor.minutes())
                    if demand.minutes_by_block.get(bt, 0) <= 0:
                        break
                    if not can_place(bt, cursor, mins):
                        break
                    ev, rest = allocate(bt, cursor, mins)
                    if not ev:
                        break
                    day_blocks.append(ev)
                    cursor = rest

        days.append(PlanDay(day, day_blocks, cap_today))

    return Plan(days)


# =========================
# Rendering & GCal payloads
# =========================

def summary_for(bt: BlockType, iv: Interval, task_titles: List[str]) -> str:
    label = {
        BlockType.CLIENT_DEEP_WORK: "[BLOCK] Client Deep Work",
        BlockType.SYSTEMS_DEVELOPMENT: "[BLOCK] Systems Development",
        BlockType.MARKETING_CREATIVE: "[BLOCK] Marketing Creative",
        BlockType.ADMIN_PROCESSING: "[BLOCK] Admin Processing",
        BlockType.PERSONAL: "[BLOCK] Personal",
    }[bt]
    mins = iv.minutes()
    hours = mins // 60
    rem = mins % 60
    dur = f"{hours}h" + (f" {rem}m" if rem else "")
    if task_titles:
        if len(task_titles) == 1:
            title = task_titles[0]
        else:
            title = f"{task_titles[0]} +{len(task_titles)-1} more"
        return f"{label}: {title} ({dur})"
    return f"{label} ({dur})"

def description_for(bt: BlockType, task_ids: List[str], task_titles: List[str]) -> str:
    lines = ["Auto-generated contextual block.", f"Block Type: {bt}"]
    if task_titles:
        # Show names (and keep IDs for traceability)
        shown = []
        for i, (tid, name) in enumerate(zip(task_ids, task_titles)):
            shown.append(f"- {name}  [id:{tid}]")
        lines.append("Tasks:\n" + "\n".join(shown))
    else:
        lines.append(f"Tasks: {', '.join(task_ids[:10])}{'...' if len(task_ids) > 10 else ''}")
    return "\n".join(lines)
def to_gcal_event(ev: Event) -> dict:
    start_utc = ev.start.astimezone(dt.timezone.utc)
    end_utc = ev.end.astimezone(dt.timezone.utc)
    return {
        "summary": ev.summary,
        "description": ev.description,
        "start": {"dateTime": start_utc.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_utc.isoformat(), "timeZone": "UTC"},
        "extendedProperties": {"private": {
            "helios_block_type": ev.block_type.value,
            "helios_task_ids": ",".join(ev.task_ids),
            "helios_generated": "true",
            "helios_version": "v1",
        }},
    }

# =========================
# CLI glue
# =========================

def main():
    ap = argparse.ArgumentParser(description="Helios contextual block scheduler (personal-aware)")
    ap.add_argument("--config", type=str, default=None, help="Path to block_rules.yaml (optional)")
    ap.add_argument("--window-days", type=int, default=14)
    ap.add_argument("--apply", action="store_true", help="Write to calendar; otherwise dry-run")
    ap.add_argument("--count-only", action="store_true", help="Print per-day block counts")
    ap.add_argument("--respect-existing-suggestions", action="store_true")
    ap.add_argument("--start-date", type=str, default=None, help="YYYY-MM-DD; default=today")
    ap.add_argument("--fixed-calendar-id", type=str, required=False)
    ap.add_argument("--suggestions-calendar-id", type=str, required=False)
    args = ap.parse_args()

    fixed_id = args.fixed_calendar_id or FIXED_CALENDAR_ID
    sugg_id = args.suggestions_calendar_id or FLEXIBLE_CALENDAR_ID
    if not fixed_id or not sugg_id:
        raise SystemExit("Missing calendar IDs. Set FIXED_CALENDAR_ID/FLEXIBLE_CALENDAR_ID or pass CLI flags.")

    cfg = load_config(args.config)

    # ---- Calendar integration ----
    cal = CalendarClient(fixed_id, sugg_id)

    def fixed_events_fetcher(day: dt.date) -> List[Dict[str, dt.datetime]]:
        time_min = as_utc(dt.datetime.combine(day, dt.time(0, 0)))
        time_max = as_utc(dt.datetime.combine(day, dt.time(23, 59)))
        raw = cal.list_events(cal.fixed_id, time_min, time_max)
        out: List[Dict[str, dt.datetime]] = []
        for e in raw:
            try:
                s = e["start"]; en = e["end"]
                if isinstance(s, str):  s = dt.datetime.fromisoformat(s.replace("Z","+00:00"))
                if isinstance(en, str): en = dt.datetime.fromisoformat(en.replace("Z","+00:00"))
                out.append({"start": as_utc(s), "end": as_utc(en)})
            except Exception:
                continue
        return out

    # ---- ClickUp integration ----
    cu = RealClickUpClient()
    grouped_plain = cu.fetch_tasks_grouped()  # returns dict[str, list[dict]]
    tasks_grouped = _adapt_grouped_for_scheduler(grouped_plain)

    # ---- Plan & render/apply ----
    start = dt.date.fromisoformat(args.start_date) if args.start_date else dt.date.today()
    plan = plan_week(start, args.window_days, cfg, fixed_events_fetcher, tasks_grouped)

    if args.count_only:
        per_day = []
        for d in plan.days:
            counts = {bt.value: 0 for bt in BlockType}
            for ev in d.blocks:
                counts[ev.block_type.value] += 1
            per_day.append({"date": d.date.isoformat(), **counts})
        print(json.dumps(per_day, indent=2))
        return

    if not args.apply:
        for d in plan.days:
            if not d.blocks: continue
            print(f"# {d.date.isoformat()}")
            for ev in d.blocks:
                print(f"- {ev.start.time()}–{ev.end.time()} :: {ev.summary}")
        return

    if not args.respect_existing_suggestions:
        cal.clear_suggestions(
            as_utc(dt.datetime.combine(start, dt.time(0,0))),
            as_utc(dt.datetime.combine(start + dt.timedelta(days=args.window_days), dt.time(23,59))),
        )

    for d in plan.days:
        for ev in d.blocks:
            cal.upsert_event(cal.suggestions_id, to_gcal_event(ev), idempotency_key=f"{ev.block_type.value}:{ev.start.isoformat()}")

    print("Applied suggestions to calendar.")

# =========================
# Google Calendar Client
# =========================

class CalendarClient:
    def __init__(self, fixed_calendar_id: str, suggestions_calendar_id: str):
        self.fixed_id = fixed_calendar_id
        self.suggestions_id = suggestions_calendar_id
        self._svc = None

    def _service(self):
        if self._svc is not None:
            return self._svc
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request as GoogleRequest
        token_candidates = [
            os.environ.get("HELIOS_GCAL_TOKEN_FILE") or "",
            os.path.join(os.path.dirname(__file__), "..", "helios_token_rw.json"),
            os.path.join(os.path.dirname(__file__), "..", "core_py", "helios_token_rw.json"),
            os.path.join(os.path.dirname(__file__), "helios_token_rw.json"),
        ]
        token_file = next((p for p in token_candidates if p and os.path.exists(p)), None)
        if not token_file:
            raise RuntimeError("Google token not found; set HELIOS_GCAL_TOKEN_FILE or place helios_token_rw.json nearby")
        scopes = ["https://www.googleapis.com/auth/calendar"]
        creds = Credentials.from_authorized_user_file(token_file, scopes)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(GoogleRequest()); open(token_file, "w").write(creds.to_json())
            else:
                raise RuntimeError("Invalid/expired Google credentials; refresh token required")
        self._svc = build("calendar", "v3", credentials=creds)
        return self._svc

    def list_events(self, calendar_id, time_min, time_max):
        import datetime as _dt
        svc = self._service()
        def _rfc3339(d: _dt.datetime) -> str:
            if d.tzinfo is None: d = d.replace(tzinfo=_dt.timezone.utc)
            return d.isoformat().replace("+00:00","Z")
        events, page_token = [], None
        while True:
            res = svc.events().list(
                calendarId=calendar_id, timeMin=_rfc3339(time_min), timeMax=_rfc3339(time_max),
                singleEvents=True, orderBy="startTime", pageToken=page_token,
            ).execute()
            events.extend(res.get("items", []))
            page_token = res.get("nextPageToken")
            if not page_token: break
        # normalize start/end
        norm = []
        for e in events:
            s = e.get("start"); en = e.get("end")
            if isinstance(s, dict) and "dateTime" in s: s = s["dateTime"]
            elif isinstance(s, dict) and "date" in s:   s = s["date"] + "T00:00:00Z"
            if isinstance(en, dict) and "dateTime" in en: en = en["dateTime"]
            elif isinstance(en, dict) and "date" in en:   en = en["date"] + "T00:00:00Z"
            try:
                s_dt = _dt.datetime.fromisoformat(s.replace("Z","+00:00")) if isinstance(s,str) else s
                e_dt = _dt.datetime.fromisoformat(en.replace("Z","+00:00")) if isinstance(en,str) else en
                e["start"], e["end"] = s_dt, e_dt
            except Exception:
                pass
            norm.append(e)
        return norm

    def upsert_event(self, calendar_id, event, idempotency_key=None):
        svc = self._service()
        body = dict(event)
        if idempotency_key:
            body.setdefault("extendedProperties", {}).setdefault("private", {})["helios_idem"] = idempotency_key
        return svc.events().insert(calendarId=calendar_id, body=body).execute()

    def clear_suggestions(self, time_min, time_max):
        svc = self._service()
        items = self.list_events(self.suggestions_id, time_min, time_max)
        for e in items:
            ev_id = e.get("id")
            if not ev_id: continue
            try:
                svc.events().delete(calendarId=self.suggestions_id, eventId=ev_id).execute()
            except Exception:
                pass

if __name__ == "__main__":
    main()
