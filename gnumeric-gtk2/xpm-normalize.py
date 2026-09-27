#!/usr/bin/env python3
# Rewrite XPM files in the strict form glycin's XPM loader accepts:
# "static const char *" declaration, exactly the number of rows the
# header declares, no trailing comma before "};".
import re
import sys

for path in sys.argv[1:]:
    with open(path, encoding="latin-1") as f:
        text = f.read()
    m = re.search(r"static\s+[^\[]*?(\w+)\s*\[\s*\]\s*=\s*\{", text)
    if not m:
        continue
    strings = re.findall(r'"((?:[^"\\]|\\.)*)"', text[m.end():])
    width, height, ncolors = (int(v) for v in strings[0].split()[:3])
    strings = strings[:1 + ncolors + height]
    body = ",\n".join('"%s"' % s for s in strings)
    with open(path, "w", encoding="latin-1") as f:
        f.write("/* XPM */\nstatic const char *%s[] = {\n%s};\n" % (m.group(1), body))
