import re
import datetime
import hashlib
from icalendar import Calendar, Event
import recurring_ical_events

GRADES = [6, 8]  # 0 = Kindergarten, 1-8 = grades
SRC = "basic.ics"
OUT = "WNS_6th_8th_All_School.ics"
CAL_NAME = "WNS 6th, 8th and All School"

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
    n.add("DTSTAMP", datetime.datetime.now(datetime.timezone.utc))
    n.add("SEQUENCE", 0)
    return n


src = Calendar.from_ical(open(SRC, "rb").read())
out = Calendar()
out.add("PRODID", "-//WNS calendar split//EN")
out.add("VERSION", "2.0")
out.add("CALSCALE", "GREGORIAN")
out.add("METHOD", "PUBLISH")
out.add("X-WR-CALNAME", CAL_NAME)
out.add("X-WR-TIMEZONE", "America/Los_Angeles")
for tz in src.walk("VTIMEZONE"):
    out.add_component(tz)

seen = set()
keep = []
for e in recurring_ical_events.of(src).between(START, END):
    if str(e.get("STATUS", "")).upper() == "CANCELLED":
        continue
    c = classify(str(e.get("SUMMARY", "")))
    if not (c == "all" or (isinstance(c, set) and c & set(GRADES))):
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
    keep.append(e)

for e in sorted(keep, key=sort_key):
    out.add_component(copy_event(e))

open(OUT, "wb").write(out.to_ical())
print(len(keep), "events written to", OUT)
