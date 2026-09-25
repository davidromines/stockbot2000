"""
Quarterly high/low prices from a 10-K's Item 5 (Stage M2b).

Dead companies have no price history in free data, but every 10-K reports the
high and low price of each quarter of its last two fiscal years. Those are real
price anchors for the synthetic dead companies (docs/STAGE_M_RESEARCH.md §4D).

A WRONG anchor is worse than none: it would pin a synthetic path to a price the
company never had. So the parser reads the table's own column header (High /
Low / Dividend, and the years when they head column groups), requires every row
to have exactly that many values, and returns [] for a table it cannot read.
Integers are never prices (they are years, days, counts); a dash is an empty
dividend cell.

Layouts handled (all from real filings, tests/fixtures/item5/):
  A  year, then quarter rows          "2011 First Quarter $ 14.80 $ 11.18 ..."
  B  years head column groups         "2014 2013 High Low High Low First Quarter $15.17 $10.06 $19.67 $11.35"
  C  quarters as columns              "Fourth Quarter ... First Quarter High Low ... Fiscal Year 2016 $9.26 ..."
  D  dated rows                       "December 31, 2018 $ 2.83 $ 2.01 $ —"
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import calendar
import re

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
PRICE = re.compile(r"^\(?(\d{1,3}(?:,\d{3})*|\d+)\.(\d+)\)?[*,;]?$")
YEAR = re.compile(r"^(19[89]\d|20[0-4]\d)[,.:;]?$")
DASH = {"—", "–", "-", "$—", "$–", "$-", "--"}
# Words that may sit inside a price table without ending it.
TABLE_WORDS = {"high", "low", "dividend", "dividends", "cash", "declared", "paid", "common", "stock", "price",
               "prices", "range", "quarter", "quarters", "ended", "fiscal", "year", "per", "share", "sales",
               "sale", "$", ":", "calendar", "period"}
SECTION = re.compile(r"market\s+for\s+(the\s+)?(registrant|company)", re.I)


def _w(tok: str) -> str:
    return tok.lower().strip(".,:;()*’'\"")


def _value(tok: str):
    """A price (float), an empty cell (None) or not a value (False)."""
    if tok in DASH:
        return None
    m = PRICE.match(tok[1:] if tok.startswith("$") else tok)
    if m and len(m.group(2)) >= 2:
        return float(m.group(1).replace(",", "") + "." + m.group(2))
    return False


def _fy(year: int, month: int, fye_month: int) -> int:
    return year if month <= fye_month else year + 1


def _q_of_month(m: int, fye_month: int) -> int:
    return ((m - fye_month - 1) % 12) // 3 + 1


def quarter_end(year: int, quarter: int, fye_month: int = 12) -> str:
    """The ISO date on which fiscal `quarter` of fiscal `year` ends."""
    m = (fye_month - 3 * (4 - quarter) - 1) % 12 + 1
    y = year if m <= fye_month else year - 1
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def _date_after(tok: list, j: int, m: int, fye_month: int) -> tuple:
    """Consume an optional day and year after a month name: (index, fiscal year or None, day)."""
    day = yr = None
    if j < len(tok) and re.match(r"^\d{1,2},?$", tok[j]):
        day = int(tok[j].rstrip(","))
        j += 1
    if j < len(tok) and YEAR.match(tok[j]):
        yr = _fy(int(YEAR.match(tok[j]).group(1)), m, fye_month)
        j += 1
    return j, yr, day


def _labels(tok: list, fye_month: int) -> list:
    """Quarter labels: (start, end, quarter, fiscal_year_or_None)."""
    out, i = [], 0
    while i < len(tok):
        w = _w(tok[i])
        q = yr = None
        j = i + 1
        nxt = _w(tok[j]) if j < len(tok) else ""
        if w in ORD and (nxt.startswith("quarter") or (nxt == "fiscal" and j + 1 < len(tok)
                                                       and _w(tok[j + 1]).startswith("quarter"))):
            q = ORD[w]
            j = j + 1 if nxt.startswith("quarter") else j + 2
            # "Fourth Quarter ended December 31, 2009": the date belongs to this label.
            if j + 1 < len(tok) and _w(tok[j]) == "ended" and _w(tok[j + 1]) in MONTHS:
                j, yr, _ = _date_after(tok, j + 2, MONTHS[_w(tok[j + 1])], fye_month)
        elif re.match(r"^q[1-4]$", w):
            q = int(w[1])
        elif w in MONTHS and (MONTHS[w] - fye_month) % 3 == 0:
            j2, yr2, day = _date_after(tok, j, MONTHS[w], fye_month)
            if day is None or day >= 28:
                q, yr, j = _q_of_month(MONTHS[w], fye_month), yr2, j2
        if q:
            out.append((i, j, q, yr))
            i = j
        else:
            i += 1
    return out


def _schema_of(words: list) -> list:
    return [{"high": "H", "low": "L"}.get(_w(t), "D") for t in words
            if _w(t) in ("high", "low", "dividend", "dividends")]


def _header(tok: list, first: int) -> tuple:
    """(schema, years) from the run of table words right before the first label."""
    i = first - 1
    # A token ending a sentence ("... of 2025 and 2024.") is prose, not header.
    while i >= 0 and (_w(tok[i]) in TABLE_WORDS or YEAR.match(tok[i])) and not tok[i].endswith("."):
        i -= 1
    head = tok[i + 1:first]
    return _schema_of(head), [int(YEAR.match(t).group(1)) for t in head if YEAR.match(t)]


def _row_values(tok: list, start: int, stop: int, year_ends: bool = False) -> tuple:
    """Values from start until a non-table word (or a year, when years start rows): (values, years seen)."""
    vals, years, i = [], [], start
    while i < stop:
        v = _value(tok[i])
        if v is not False:
            vals.append(v)
        elif YEAR.match(tok[i]):
            if year_ends:
                break
            years.append(int(YEAR.match(tok[i]).group(1)))
        elif _w(tok[i]) not in TABLE_WORDS and not re.match(r"^\(\d\)$", tok[i]):
            break
        i += 1
    return vals, years, i


def _hl(vals: list, schema: list):
    """(high, low, dividend column) for one row group, or None.

    Header word order does not say where the dividend column is: a two-line
    header ("Market Price / Dividends Declared" over "High Low") reads D-H-L
    while the cells run H-L-D (DGX, 2017). So the dividend is found from the
    values — the dash, else the smallest cell — and the callers require it to
    sit in the same column in every row. High and low are the other two cells.
    """
    if "D" not in schema:
        h, lo = vals[schema.index("H")], vals[schema.index("L")]
        return (h, lo, None) if h is not None and lo is not None else None
    if len(vals) != 3 or schema.count("D") != 1:
        return None
    nones = [i for i, v in enumerate(vals) if v is None]
    if len(nones) > 1:
        return None
    d = nones[0] if nones else min(range(3), key=lambda i: vals[i])
    a, b = [vals[i] for i in range(3) if i != d]
    return max(a, b), min(a, b), d


def _columns(tok: list, labels: list) -> list:
    """Layout C: consecutive quarter labels head the columns; each row starts with a year."""
    k = 0
    while k + 1 < len(labels) and labels[k + 1][0] == labels[k][1]:
        k += 1
    quarters = [lab[2] for lab in labels[:k + 1]]
    i = labels[k][1]
    j = i
    while j < len(tok) and _w(tok[j]) in ("high", "low", "dividend", "dividends", "cash", "declared"):
        j += 1
    schema = _schema_of(tok[i:j])
    if not quarters or not schema or len(schema) % len(quarters):
        return []
    per = len(schema) // len(quarters)
    if "H" not in schema[:per] or "L" not in schema[:per]:
        return []
    out, i, dcols = [], j, set()
    while i < len(tok):
        while i < len(tok) and _w(tok[i]) in ("fiscal", "year", "calendar"):
            i += 1
        if i >= len(tok) or not YEAR.match(tok[i]):
            break
        year = int(YEAR.match(tok[i]).group(1))
        vals, _, i = _row_values(tok, i + 1, len(tok), year_ends=True)
        while i > 0 and _w(tok[i - 1]) in ("fiscal", "year", "calendar"):
            i -= 1                                            # give "Fiscal Year" back to the next row
        if len(vals) != per * len(quarters):
            break
        for n, q in enumerate(quarters):
            hl = _hl(vals[n * per:(n + 1) * per], schema[:per])
            if hl:
                dcols.add(hl[2])
                out.append({"year": year, "quarter": q, "high": hl[0], "low": hl[1]})
    return out if len(dcols) <= 1 else []


def _rows(tok: list, labels: list) -> list:
    """Layouts A, B and D: one row per quarter label."""
    schema, hyears = _header(tok, labels[0][0])
    schema = schema or ["H", "L"]
    groups = 1
    if len(hyears) >= 2 and schema.count("H") == len(hyears) and len(schema) % len(hyears) == 0:
        groups = len(hyears)                                  # layout B
    per = len(schema) // groups
    sub = schema[:per]
    if "H" not in sub or "L" not in sub:
        return []
    year = hyears[-1] if len(hyears) == 1 else None
    out, dcols = [], set()
    for n, (_, e, q, yr) in enumerate(labels):
        stop = labels[n + 1][0] if n + 1 < len(labels) else len(tok)
        vals, seen, _ = _row_values(tok, e, stop)
        if len(vals) != len(schema):
            if out:
                break                                         # the table has ended
            return []
        if groups > 1:
            for g in range(groups):
                hl = _hl(vals[g * per:(g + 1) * per], sub)
                if hl:
                    dcols.add(hl[2])
                    out.append({"year": hyears[g], "quarter": q, "high": hl[0], "low": hl[1]})
        else:
            fy = yr if yr is not None else year
            if fy is None:
                return []
            hl = _hl(vals, sub)
            if hl:
                dcols.add(hl[2])
                out.append({"year": fy, "quarter": q, "high": hl[0], "low": hl[1]})
        if seen:
            year = seen[-1]                                   # a year between rows starts the next group
    return out if len(dcols) <= 1 else []                     # the dividend moved column: unreadable


def parse(text: str, fye_month: int = 12) -> list:
    """[{year, quarter, high, low}] from an Item 5 window; [] when the table cannot be read."""
    tok = (text or "").split()
    labels = _labels(tok, fye_month)
    # A date in the prose ("As of December 31, 2009, ...") is not a row: the table
    # starts at the first label that has values after it, or that heads columns.
    while labels:
        s, e, _, _ = labels[0]
        stop = labels[1][0] if len(labels) > 1 else len(tok)
        if _row_values(tok, e, stop)[0] or (len(labels) > 1 and labels[1][0] == e):
            break
        labels = labels[1:]
    if not labels:
        return []
    layout_c = len(labels) > 1 and labels[1][0] == labels[0][1]
    rows = _columns(tok, labels) if layout_c else _rows(tok, labels)
    seen, out = set(), []
    for r in rows:
        if (r["year"], r["quarter"]) not in seen:
            seen.add((r["year"], r["quarter"]))
            out.append(r)
    if any(r["high"] < r["low"] or r["low"] <= 0 for r in out):
        return []
    return out


def locate(text: str) -> str:
    """The Item 5 window: the LAST 'market for registrant' heading followed by a price table."""
    best = ""
    for m in SECTION.finditer(text or ""):
        w = text[m.start():m.start() + 4000]
        if len(re.findall(r"\d\.\d\d", w)) >= 6 and re.search(r"high", w, re.I):
            best = w
    return best
