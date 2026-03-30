"""Eigenes CalVer-Schema für setuptools-scm.

Format: YY.MM.PATCH[.devN]
- Auf einem Tag:       26.3.13
- Gleicher Monat:      26.3.14.dev2
- Neuer Monat:         26.4.1.dev2
"""

from datetime import date


def calver_next(version) -> str:
    today = date.today()
    cur_yy = today.year % 100
    cur_mm = today.month

    if version.distance == 0:
        return str(version.tag)

    parts = str(version.tag).lstrip("v").split(".")
    tag_yy, tag_mm, tag_patch = int(parts[0]), int(parts[1]), int(parts[2])

    if cur_yy != tag_yy or cur_mm != tag_mm:
        base = f"{cur_yy}.{cur_mm}.1"
    else:
        base = f"{tag_yy}.{tag_mm}.{tag_patch + 1}"

    return f"{base}.dev{version.distance}"
