#!/usr/bin/env python3
"""Normalize notebooks before conversion:
- ensure first cell containing YAML-like front matter is markdown
- quote title/description values that contain YAML-sensitive characters
- normalize boolean 'comments' to lowercase
- add missing cell 'id' fields (nbformat requirement)
"""
from __future__ import annotations

import glob
import json
import os
import re
import uuid
from typing import List

import nbformat


def quote_value(val: str) -> str:
    # If already quoted, return as-is
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val
    # Lowercase booleans should remain unquoted
    if val.lower() in ("true", "false", "null"):
        return val.lower()
    # Quote if contains colon or leading/trailing whitespace or YAML specials
    if ':' in val or val.startswith(' ') or val.endswith(' ') or '\n' in val or val.startswith('#'):
        # escape inner double quotes
        safe = val.replace('"', '\\"')
        return f'"{safe}"'
    return val


FRONT_MATTER_KEY_RE = re.compile(r'^(?P<key>[A-Za-z0-9_\-]+):\s*(?P<val>.*)$')


def normalize_front_matter_lines(lines: List[str]) -> List[str]:
    out: List[str] = []
    for line in lines:
        m = FRONT_MATTER_KEY_RE.match(line)
        if not m:
            out.append(line)
            continue
        key = m.group('key')
        val = m.group('val')
        # Normalize the comments boolean
        if key.lower() == 'comments':
            v = val.strip().lower()
            if v in ('true', 'false'):
                out.append(f"{key}: {v}")
            else:
                out.append(f"{key}: true")
            continue

        # Quote title and description or any value containing ':'
        if key.lower() in ('title', 'description') or ':' in val:
            q = quote_value(val)
            out.append(f"{key}: {q}")
            continue

        # Leave other keys as-is
        out.append(line)
    return out


def ensure_cell_ids(nb: dict) -> None:
    for cell in nb.get('cells', []):
        if 'id' not in cell or not cell.get('id'):
            cell['id'] = str(uuid.uuid4())


def fix_notebook(path: str) -> None:
    try:
        nb = nbformat.read(path, as_version=4)
    except Exception:
        # If nbformat can't read it, skip
        return

    changed = False

    # Ensure cell ids exist
    for cell in nb.get('cells', []):
        if 'id' not in cell or not cell.get('id'):
            cell['id'] = str(uuid.uuid4())
            changed = True

    # Check first cell for YAML-like front matter
    if nb.get('cells'):
        first = nb['cells'][0]
        src = first.get('source', '')
        if isinstance(src, list):
            src_text = ''.join(src)
        else:
            src_text = src

        if src_text.lstrip().startswith('---') or 'title:' in src_text.splitlines()[0:3]:
            # Ensure markdown cell
            if first.get('cell_type') != 'markdown':
                first['cell_type'] = 'markdown'
                changed = True

            lines = src_text.splitlines()
            # If the cell starts with '---', find closing '---'
            if lines and lines[0].strip() == '---':
                try:
                    end = lines.index('---', 1)
                except ValueError:
                    end = None
                if end is not None:
                    fm_lines = lines[1:end]
                    new_fm = normalize_front_matter_lines(fm_lines)
                    new_lines = ['---'] + new_fm + ['---'] + lines[end+1:]
                    first['source'] = '\n'.join(new_lines) + ('\n' if src_text.endswith('\n') else '')
                    changed = True
                else:
                    # Try best-effort: normalize all lines
                    new_fm = normalize_front_matter_lines(lines)
                    first['source'] = '\n'.join(new_fm)
                    changed = True
            else:
                # No explicit --- block but likely front-matter lines; normalize first few lines
                head = lines[:6]
                tail = lines[6:]
                new_head = normalize_front_matter_lines(head)
                first['source'] = '\n'.join(new_head + tail)
                changed = True

    if changed:
        try:
            nbformat.write(nb, path)
            print(f"Normalized: {path}")
        except Exception as e:
            print(f"Failed to write {path}: {e}")


def main() -> None:
    notebooks = glob.glob(os.path.join('_notebooks', '**', '*.ipynb'), recursive=True)
    for nb in notebooks:
        fix_notebook(nb)


if __name__ == '__main__':
    main()
