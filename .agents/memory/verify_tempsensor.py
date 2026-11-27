#!/usr/bin/env python3
"""Verify the FB_TempSensor_FFO documentation-only edit."""
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

PATH = "lcls-twincat-pmps/PMPS/AncillaryComponents/FB_TempSensor_FFO.TcPOU"

fail = []


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        fail.append(msg)


new_raw = open(PATH, "rb").read()
old_raw = subprocess.run(
    ["git", "show", "HEAD:" + PATH], capture_output=True, check=True
).stdout

# 1. encoding hygiene
check(new_raw[:3] == b"\xef\xbb\xbf", "UTF-8 BOM preserved")
check(new_raw.count(b"\r\n") == new_raw.count(b"\n"), "line endings still pure CRLF")

new = new_raw.decode("utf-8-sig")
old = old_raw.decode("utf-8-sig")

# 2. XML well formed and CDATA intact
try:
    root = ET.fromstring(new_raw)
    check(root.tag == "TcPlcObject", "XML parses, root is TcPlcObject")
except ET.ParseError as exc:  # pragma: no cover
    check(False, "XML parses (%s)" % exc)
    root = None


def cdata(text, pattern):
    m = re.search(
        r"<" + pattern + r"><!\[CDATA\[(.*?)\]\]></" + pattern + r">", text, re.S
    )
    assert m, pattern
    return m.group(1)


def strip_comments(s):
    s = re.sub(r"\(\*.*?\*\)", " ", s, flags=re.S)
    s = re.sub(r"//[^\r\n]*", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# 3. declaration token stream identical
decl_old = strip_comments(cdata(old, "Declaration"))
decl_new = strip_comments(cdata(new, "Declaration"))
check(decl_old == decl_new, "declaration token stream identical after stripping comments")
if decl_old != decl_new:
    print("--- old ---\n" + decl_old)
    print("--- new ---\n" + decl_new)

# 4. every declaration still carries a preceding comment, looking past pragma blocks
body = cdata(new, "Declaration")
lines = body.replace("\r\n", "\n").split("\n")

# mark which lines are inside a (* *) comment so declaration lines can be found
in_comment = []
state = False
for line in lines:
    starts = line.strip().startswith("(*")
    ends = line.rstrip().endswith("*)")
    in_comment.append(state or ("(*" in line and not starts))
    if starts and not ends:
        state = True
    if ends:
        state = False


def preceding_comment(index):
    """Walk back over blanks and {attribute} pragma blocks to the previous real line."""
    i = index - 1
    in_pragma = False
    while i >= 0:
        s = lines[i].strip()
        if in_pragma:
            if s.startswith("{attribute"):
                in_pragma = False
            i -= 1
            continue
        if not s:
            i -= 1
            continue
        if s.endswith("'}"):
            in_pragma = True
            i -= 1
            continue
        return s
    return ""


for name in [
    "fFaultThreshold",
    "fHysteresis",
    "sDevName",
    "bVeto",
    "bAutoReset",
    "io_fbFFHWO",
    "sPath",
    "bFAULT_OK",
    "FFO",
    "rtRESET",
    "ftFAULT",
    "ftConnected",
    "fbLogger",
]:
    decl_line = None
    for i, line in enumerate(lines):
        if in_comment[i]:
            continue
        if re.match(r"\s*" + re.escape(name) + r"\s*(:|\()", line):
            decl_line = i
            break
    check(decl_line is not None, f"{name} declaration found")
    if decl_line is None:
        continue
    prev = preceding_comment(decl_line)
    check(prev.endswith("*)"), f"{name} has a preceding block comment (saw {prev!r})")

# 5. implementation bodies unchanged except the ACT_Logger header comment
impl_old = [strip_comments(x) for x in re.findall(r"<ST><!\[CDATA\[(.*?)\]\]></ST>", old, re.S)]
impl_new = [strip_comments(x) for x in re.findall(r"<ST><!\[CDATA\[(.*?)\]\]></ST>", new, re.S)]
check(impl_old == impl_new, "all ST bodies identical after stripping comments")
check(
    new.count("(* ACT_Logger") == 1,
    "ACT_Logger carries a header comment",
)

# 6. pre-commit style rules used for TcPOU files
bad_trailing = [
    i + 1
    for i, line in enumerate(new.split("\r\n"))
    if line != line.rstrip()
]
check(not bad_trailing, "no trailing whitespace" + (f" (lines {bad_trailing})" if bad_trailing else ""))
bad_tabs = [i + 1 for i, line in enumerate(new.split("\r\n")) if line.startswith("\t")]
check(not bad_tabs, "no leading tabs" + (f" (lines {bad_tabs})" if bad_tabs else ""))

print()
print("FAILURES:", len(fail))
sys.exit(1 if fail else 0)
