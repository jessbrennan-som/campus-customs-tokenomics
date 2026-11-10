"""Defenses for the vendor desk agent (Problem 6).

1. clean_document(path): keeps ONLY text a person would see when reading the document the ordinary way.
   Text that is hidden (display:none, same color as the background, 0 or tiny font, pushed off the page or
   screen, invisible PDF render mode, HTML comments, zero-width characters) is dropped BEFORE the agent sees
   it, and each dropped piece is recorded with the reason.
2. handbook_fingerprint / check_handbook_unchanged: the handbook is read-only for the AI.
3. blocked_vendors / blocked_vendor_in: removed and pending vendors (read from handbook section 6) can never
   be recommended; this is checked in code as well as in the prompt.
"""
import hashlib
import math
import re
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from pypdf import PdfReader

MIN_VISIBLE_PX = 4        # text smaller than this (4 px = 3 pt) cannot be read by a person
MIN_VISIBLE_PT = 3
OFFSCREEN = -500          # an offset further left/up than this many px/pt is "permanently out of view"
COLOR_CLOSE = 24          # text color within this distance of the background (0-255 scale) is invisible
ZERO_WIDTH = re.compile("[​‌‍‎‏⁠﻿­‪-‮⁦-⁩]")


@dataclass
class CleanDoc:
    text: str
    kind: str
    removed: list = field(default_factory=list)   # [{"reason": ..., "text": ...}]
    zero_width_removed: int = 0


# ---------------------------------------------------------------- HTML
NAMED = {"white": (255, 255, 255), "black": (0, 0, 0), "transparent": None, "#fff": (255, 255, 255)}


def parse_color(value: str):
    """Return (r, g, b) or None if unknown/transparent. A mostly transparent rgba counts as transparent."""
    v = value.strip().lower().replace("!important", "").strip()
    if v in NAMED:
        return NAMED[v]
    m = re.fullmatch(r"#([0-9a-f]{3})", v)
    if m:
        return tuple(int(c * 2, 16) for c in m.group(1))
    m = re.fullmatch(r"#([0-9a-f]{6})([0-9a-f]{2})?", v)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(([^)]*)\)", v)
    if m:
        parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(1).strip()) if p.strip()]
        try:
            rgb = tuple(float(p.rstrip("%")) * (2.55 if p.endswith("%") else 1) for p in parts[:3])
            if len(parts) > 3 and float(parts[3].rstrip("%")) / (100 if parts[3].endswith("%") else 1) < 0.1:
                return None
            return tuple(int(x) for x in rgb)
        except ValueError:
            return None
    return None


def to_px(value: str, parent_px: float) -> float | None:
    v = value.strip().lower().replace("!important", "").strip()
    m = re.fullmatch(r"(-?[\d.]+)\s*(px|pt|em|rem|%|)", v)
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2)
    return {"px": n, "": n, "pt": n * 4 / 3, "em": n * parent_px, "rem": n * 16, "%": n / 100 * parent_px}[unit]


def parse_declarations(css: str) -> dict:
    out = {}
    for part in css.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def stylesheet_rules(soup) -> list:
    rules = []
    for tag in soup.find_all("style"):
        css = re.sub(r"/\*.*?\*/", "", tag.get_text(), flags=re.S)
        css = re.sub(r"@media[^{]*print[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css, flags=re.S)  # print-only rules
        for sel, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css):
            for s_ in sel.split(","):
                rules.append((s_.strip(), parse_declarations(body)))
    return rules


SKIP_SELECTOR = re.compile(r"::|:(hover|focus|active|visited|before|after|first-line|first-letter|target)\b")


def style_map(soup, rules: list) -> dict:
    """{id(element): declarations} from the stylesheet. Any selector BeautifulSoup understands works
    (descendant, child, compound, attribute, :nth-child ...). Later rules win; specificity is not modeled."""
    out = {}
    for sel, decl in rules:
        if not sel or SKIP_SELECTOR.search(sel):
            continue
        try:
            matched = soup.select(sel)
        except Exception:
            continue  # a selector we cannot parse
        for el in matched:
            out.setdefault(id(el), {}).update(decl)
    return out


FONT_SIZE_PX = {1: 10, 2: 13, 3: 16, 4: 18, 5: 24, 6: 32, 7: 48}


def legacy_style(el: Tag) -> dict:
    """Old HTML presentation attributes: <font color size>, bgcolor, <body text>."""
    st = {}
    if el.name == "font":
        if el.get("color"):
            st["color"] = el["color"]
        size = str(el.get("size", "")).strip()
        if re.fullmatch(r"[+-]?\d", size):
            n = int(size) if size[0] not in "+-" else 3 + int(size)
            st["font-size"] = f"{FONT_SIZE_PX[min(7, max(1, n))]}px"
    if el.get("bgcolor"):
        st["background-color"] = el["bgcolor"]
    if el.name == "body" and el.get("text"):
        st["color"] = el["text"]
    return st


def element_style(el: Tag, sheet: dict) -> dict:
    style = legacy_style(el)                          # lowest priority
    style.update(sheet.get(id(el), {}))               # then the stylesheet
    style.update(parse_declarations(el.get("style", "")))  # inline style wins
    return style


def hidden_reason(el: Tag, st: dict) -> str | None:
    """Why this whole element is invisible, or None."""
    if el.has_attr("hidden"):
        return "hidden attribute"
    if el.name in ("noscript", "template", "script", "style", "head", "title", "meta", "link"):
        return f"<{el.name}> is never shown on the page"
    if el.name == "input" and el.get("type", "").lower() == "hidden":
        return "hidden input"
    d = st.get("display", "").lower()
    if d.startswith("none"):
        return "display:none"
    if st.get("visibility", "").lower().split()[0:1] in (["hidden"], ["collapse"]):
        return "visibility:hidden"
    try:
        if "opacity" in st and float(st["opacity"]) <= 0.05:
            return "opacity:0"
    except ValueError:
        pass
    clip = (st.get("clip", "") + st.get("clip-path", "")).replace(" ", "").lower()
    if "rect(0,0,0,0)" in clip or "inset(50%)" in clip or "inset(100%)" in clip:
        return "clipped to nothing"
    overflow_hidden = "hidden" in (st.get("overflow", "") + st.get("overflow-x", "") + st.get("overflow-y", "")).lower()
    for prop in ("width", "height", "max-height", "max-width"):
        if overflow_hidden and prop in st and (to_px(st[prop], 16) or 1) == 0:
            return f"{prop}:0 with overflow hidden"
    for prop in ("left", "top", "right", "bottom", "margin-left", "margin-top", "text-indent"):
        if prop in st:
            px = to_px(st[prop], 16)
            if px is not None and px <= OFFSCREEN and (prop == "text-indent" or st.get("position", "").lower() in ("absolute", "fixed", "relative") or prop.startswith("margin")):
                return f"pushed off screen ({prop}:{st[prop]})"
    m = re.search(r"translate[xy]?\(\s*(-?[\d.]+)(px|pt)?", st.get("transform", "").lower())
    if m and float(m.group(1)) <= OFFSCREEN:
        return "pushed off screen (transform)"
    return None


def sanitize_html(html: str):
    """Return (visible text, removed pieces)."""
    soup = BeautifulSoup(html, "html.parser")
    sheet = style_map(soup, stylesheet_rules(soup))
    removed = []

    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        if c.strip():
            removed.append({"reason": "HTML comment", "text": c.strip()})
        c.extract()

    def walk(el: Tag, color, fs_px, bg):
        st = element_style(el, sheet)
        why = hidden_reason(el, st)
        if why:
            text = el.get_text(" ", strip=True)
            if text and el.name not in ("head", "style", "script", "title", "meta", "link"):
                removed.append({"reason": why, "text": text})
            el.extract()
            return
        c = parse_color(st["color"]) if "color" in st else None
        color = c or color
        for prop in ("background-color", "background"):
            b = parse_color(st[prop].split(" ")[0]) if prop in st and not st[prop].lower().startswith("rgb") else (
                parse_color(st[prop]) if prop in st else None)
            if b:
                bg = b
        if "font-size" in st:
            px = to_px(st["font-size"], fs_px)
            fs_px = px if px is not None else fs_px
        if "font" in st:
            m = re.search(r"([\d.]+(?:px|pt|em|rem|%))", st["font"])
            if m:
                px = to_px(m.group(1), fs_px)
                fs_px = px if px is not None else fs_px
        text_why = None
        if fs_px < MIN_VISIBLE_PX:
            text_why = f"font size {fs_px:.1f}px is too small to read"
        elif color is not None and bg is not None and max(abs(a - b) for a, b in zip(color, bg)) <= COLOR_CLOSE:
            text_why = f"text color {color} matches the background {bg}"
        for child in list(el.children):
            if isinstance(child, Tag):
                walk(child, color, fs_px, bg)
            elif isinstance(child, NavigableString) and text_why and child.strip():
                removed.append({"reason": text_why, "text": child.strip()})
                child.extract()

    for top in list(soup.children):  # the whole tree, so html and body styles (page background, text color) count
        if isinstance(top, Tag):
            walk(top, (0, 0, 0), 16.0, (255, 255, 255))
    text = (soup.body or soup).get_text(separator="\n", strip=True)
    return text, removed


# ---------------------------------------------------------------- PDF
def sanitize_pdf(path: Path):
    reader = PdfReader(str(path))
    removed, pages_text = [], []
    for page in reader.pages:
        box = page.cropbox
        left, bottom, right, top = float(box.left), float(box.bottom), float(box.right), float(box.top)
        state = {"fill": (0.0, 0.0, 0.0), "tr": 0}
        stack = []
        pieces = []

        def on_op(op, args, cm, tm):
            if op == b"q":
                stack.append(dict(state))
            elif op == b"Q" and stack:
                state.update(stack.pop())
            elif op == b"rg" and len(args) == 3:
                state["fill"] = tuple(float(a) for a in args)
            elif op == b"g" and len(args) == 1:
                state["fill"] = (float(args[0]),) * 3
            elif op == b"k" and len(args) == 4:
                c, m, y, k = (float(a) for a in args)
                state["fill"] = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
            elif op in (b"sc", b"scn") and len(args) in (1, 3) and all(isinstance(a, (int, float)) for a in args):
                state["fill"] = tuple(float(a) for a in args) * (3 if len(args) == 1 else 1)
            elif op == b"Tr" and args:
                state["tr"] = int(args[0])

        def on_text(text, cm, tm, font, size):
            if not text.strip():
                return
            sx = math.sqrt(abs(tm[0] * tm[3] - tm[1] * tm[2])) * math.sqrt(abs(cm[0] * cm[3] - cm[1] * cm[2]))
            pt = (size or 0) * (sx or 1)
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            why = None
            if state["tr"] == 3:
                why = "invisible text render mode"
            elif pt < MIN_VISIBLE_PT:
                why = f"font size {pt:.1f}pt is too small to read"
            elif min(state["fill"]) >= 0.92:
                why = "white text on a white page"
            elif x < left - 5 or x > right + 5 or y < bottom - 5 or y > top + 5:
                why = f"placed outside the page ({x:.0f}, {y:.0f})"
            if why:
                removed.append({"reason": why, "text": text.strip()})
            else:
                pieces.append(text)

        page.extract_text(visitor_text=on_text, visitor_operand_before=on_op)
        pages_text.append("".join(p if p.endswith("\n") else p + "\n" for p in pieces))
    return "\n".join(pages_text).strip(), removed


# ---------------------------------------------------------------- email
def sanitize_eml(path: Path):
    msg = BytesParser(policy=policy.default).parse(open(path, "rb"))
    head = f"From: {msg['From']}\nTo: {msg['To']}\nSubject: {msg['Subject']}\nDate: {msg['Date']}\n\n"
    body = msg.get_body(preferencelist=("html", "plain"))  # mail programs show the HTML part when there is one
    if body is None:
        return head, []
    content = body.get_content()
    if body.get_content_type() == "text/html":
        text, removed = sanitize_html(content)
    else:
        text, removed = content, []
    return head + text, removed


# ---------------------------------------------------------------- entry
def clean_document(path: Path) -> CleanDoc:
    """The ONE way the agent gets document text. Returns only what a person would see."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".html":
        text, removed = sanitize_html(path.read_text(errors="replace"))
    elif ext == ".pdf":
        text, removed = sanitize_pdf(path)
    elif ext == ".eml":
        text, removed = sanitize_eml(path)
    else:
        raise ValueError(f"Unsupported document type: {ext}")
    zw = len(ZERO_WIDTH.findall(text))
    if zw:
        text = ZERO_WIDTH.sub("", text)
    return CleanDoc(text=text, kind=ext.lstrip("."), removed=removed, zero_width_removed=zw)


# ---------------------------------------------------------------- unfiltered reader (tests only)
def raw_clean(path, **_) -> CleanDoc:
    """What the read tools returned BEFORE the filter existed (Problems 3 to 5). Used ONLY by the comparison
    tests (defense_test.py, red_team.py) to show what the agent does without the filter. The real agent never uses it."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".html":
        soup = BeautifulSoup(path.read_text(errors="replace"), "html.parser")
        for tag in soup(["style", "script"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    elif ext == ".pdf":
        text = "\n".join(pg.extract_text() or "" for pg in PdfReader(str(path)).pages)
    else:
        msg = BytesParser(policy=policy.default).parse(open(path, "rb"))
        body = msg.get_body(preferencelist=("plain", "html"))
        text = f"From: {msg['From']}\nTo: {msg['To']}\nSubject: {msg['Subject']}\nDate: {msg['Date']}\n\n" + (body.get_content() if body else "")
    return CleanDoc(text=text, kind=ext.lstrip("."), removed=[], zero_width_removed=0)


# ---------------------------------------------------------------- handbook protection
def handbook_fingerprint(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_handbook_unchanged(path: Path, fingerprint: str) -> None:
    if handbook_fingerprint(path) != fingerprint:
        raise RuntimeError("The handbook changed during the run. Only the owner may edit it. Run stopped.")


# ---------------------------------------------------------------- removed / pending vendors
def blocked_vendors(handbook_text: str) -> dict:
    """{lowercase vendor name: status} from handbook section 6 (removed and pending vendors)."""
    section = re.search(r"## 6\..*?(?=\n## )", handbook_text, flags=re.S)
    out = {}
    for row in re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", section.group(0) if section else "", flags=re.M):
        name, status = row
        if name.lower() in ("vendor", "---") or set(name) <= set("-"):
            continue
        out[name.lower()] = "pending" if "pending" in status.lower() else "removed"
    return out


def blocked_vendor_in(blocked: dict, vendor: str, doc_text: str):
    """Return (vendor name, status) if the answer or the visible document names a removed/pending vendor."""
    hay_vendor, hay_doc = (vendor or "").lower(), doc_text.lower()
    for name, status in blocked.items():
        if name in hay_vendor or name in hay_doc:
            return name, status
    return None
