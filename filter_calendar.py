import re
import os
import datetime
import hashlib
from itertools import combinations
from icalendar import Calendar, Event
import recurring_ical_events

SRC = "basic.ics"
OUT_DIR = os.path.join("site", "calendars")
TOKENS = ["K", "1", "2", "3", "4", "5", "6", "7", "8"]
LABELS = ["Kindergarten"] + [f"Grade {i}" for i in range(1, 9)]

today = datetime.date.today()
year = today.year if today.month >= 8 else today.year - 1
START = datetime.date(year, 8, 1)
END = datetime.date(year + 1, 8, 1)

ORD = r"(\d{1,2})(?:st|nd|rd|th)"
RANGE = re.compile(
    r"(?<![A-Za-z0-9])(PS|DK|K|" + ORD + r")\s*[-\u2013]\s*(?:" + ORD + r"|(\d{1,2}))(?![A-Za-z0-9])",
    re.I,
)
SINGLE = re.compile(r"(?<![A-Za-z0-9])" + ORD + r"(?![A-Za-z0-9])", re.I)


def start_val(tok):
    t = tok.upper()
    if t == "PS":
        return -2
    if t == "DK":
        return -1
    if t == "K":
        return 0
    return int(re.match(r"\d+", t).group())


def classify(s):
    if re.search(r"\bAll[- ]School\b", s, re.I):
        return "all"
    if re.search(r"preschool", s, re.I) or re.search(r"\bECC\b", s):
        return "other"
    g = set()
    for m in RANGE.finditer(s):
        a = start_val(m.group(1))
        b = int(m.group(3) or m.group(4))
        g.update(range(max(a, 0), min(b, 12) + 1))
    for m in SINGLE.finditer(s):
        g.add(int(m.group(1)))
    if re.search(r"DK\s*/\s*K\b", s) or re.search(r"\bKindergarten\b", s, re.I):
        g.add(0)
    if not g and re.search(r"Middle School", s, re.I):
        g |= {6, 7, 8}
    if g:
        g = {x for x in g if 0 <= x <= 8}
        if not g:
            return "other"
        if g == set(range(9)):
            return "all"
        return g
    if re.search(r"(?<![A-Za-z])DK(?![A-Za-z])", s):
        return "other"
    return "all"


def sort_key(e):
    v = e["DTSTART"].dt
    if isinstance(v, datetime.datetime):
        if v.tzinfo:
            return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v
    return datetime.datetime.combine(v, datetime.time())


def copy_event(e):
    n = Event()
    for p in ["SUMMARY", "DESCRIPTION", "LOCATION", "STATUS", "TRANSP", "DTSTART", "DTEND", "DURATION", "CREATED", "LAST-MODIFIED", "URL"]:
        if p in e:
            n.add(p, e[p].dt if hasattr(e[p], "dt") else e[p])
    ds = e["DTSTART"].dt
    dkey = ds.strftime("%Y%m%dT%H%M%S") if isinstance(ds, datetime.datetime) else ds.strftime("%Y%m%d")
    uid = str(e.get("UID", hashlib.md5(str(e.get("SUMMARY")).encode()).hexdigest())).split("@")[0]
    n.add("UID", f"{uid}-{dkey}@wns-split")
    stamp = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    for p in ("LAST-MODIFIED", "CREATED"):
        if p in e:
            stamp = e[p].dt
            break
    n.add("DTSTAMP", stamp)
    n.add("SEQUENCE", 0)
    return n


src = Calendar.from_ical(open(SRC, "rb").read())
timezones = list(src.walk("VTIMEZONE"))

seen = set()
items = []  # (component, classification)
for e in sorted(recurring_ical_events.of(src).between(START, END), key=sort_key):
    if str(e.get("STATUS", "")).upper() == "CANCELLED":
        continue
    c = classify(str(e.get("SUMMARY", "")))
    if c == "other":
        continue
    sig = (
        str(e.get("SUMMARY")),
        str(e["DTSTART"].dt),
        str(e["DTEND"].dt if e.get("DTEND") else ""),
        str(e.get("LOCATION", "")),
        str(e.get("DESCRIPTION", "")),
    )
    if sig in seen:
        continue
    seen.add(sig)
    items.append((copy_event(e), c))

os.makedirs(OUT_DIR, exist_ok=True)
written = 0
for r in range(0, 10):
    for subset in combinations(range(9), r):
        chosen = set(subset)
        cal = Calendar()
        cal.add("PRODID", "-//WNS calendar split//EN")
        cal.add("VERSION", "2.0")
        cal.add("CALSCALE", "GREGORIAN")
        cal.add("METHOD", "PUBLISH")
        if chosen:
            name = "WNS " + ", ".join(LABELS[i] for i in subset) + " + All School"
        else:
            name = "WNS All School"
        cal.add("X-WR-CALNAME", name)
        cal.add("X-WR-TIMEZONE", "America/Los_Angeles")
        cal.add("X-PUBLISHED-TTL", "PT12H")
        cal.add("REFRESH-INTERVAL", datetime.timedelta(hours=12), parameters={"VALUE": "DURATION"})
        for tz in timezones:
            cal.add_component(tz)
        for comp, c in items:
            if c == "all" or (isinstance(c, set) and c & chosen):
                cal.add_component(comp)
        fname = "_".join(TOKENS[i] for i in subset) if chosen else "all"
        with open(os.path.join(OUT_DIR, fname + ".ics"), "wb") as f:
            f.write(cal.to_ical())
        written += 1

print(len(items), "events classified;", written, "calendar files written to", OUT_DIR)
