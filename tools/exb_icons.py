"""Icon management utilities for Experience Builder apps.

Lists image resources on a cloned ExB item (logo, list icons,
widget images, etc.) and replaces them in place with local files
from the repo's ``icons/`` folder.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from arcgis.gis import Item

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}


def list_icon_resources(item: Item) -> list[dict]:
    """Return image resources on *item* with human-friendly context.

    Each entry has keys: ``resource`` (path), ``size``, ``label``,
    ``original_name`` (best-effort friendly file name pulled from the
    ExB config), and ``role`` (best-effort semantic role such as
    "Logo" or "List item icon").
    """
    # Pull the published config so we can look up originalName & role
    try:
        cfg = item.get_data() or {}
    except Exception:
        cfg = {}

    # Map basename -> (original_name, role) by scanning the config.
    import json, re
    blob = json.dumps(cfg) if cfg else ""

    def _find_meta(basename: str) -> tuple[str, str]:
        original_name = ""
        role = ""
        # Find a JSON object that references this filename and pull a
        # nearby "originalName" if present.
        for match in re.finditer(r'\{[^{}]*' + re.escape(basename) + r'[^{}]*\}', blob):
            chunk = match.group(0)
            m = re.search(r'"originalName"\s*:\s*"([^"]+)"', chunk)
            if m and not original_name:
                original_name = m.group(1)
            # heuristic role from surrounding keys
            if '"svg"' in chunk or '"icon' in chunk.lower():
                role = role or "Icon"
            if '"imageParam"' in chunk or '"imgSourceType"' in chunk:
                role = role or "Image / Logo"
            if role and original_name:
                break

        # Look at broader context via widget URIs
        if not role:
            for wid, wcfg in cfg.get("widgets", {}).items():
                wtxt = json.dumps(wcfg)
                if basename not in wtxt:
                    continue
                uri = wcfg.get("uri", "")
                if "image" in uri:
                    role = "Logo / image"
                elif "list" in uri:
                    role = "List item icon"
                elif "button" in uri:
                    role = "Button icon"
                elif "text" in uri:
                    role = "Inline icon"
                else:
                    role = uri.strip("/").split("/")[-1].title() + " icon"
                break

        return original_name, role or "Icon"

    entries = []
    for res in item.resources.list() or []:
        path = res.get("resource", "")
        ext = os.path.splitext(path)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            continue
        basename = os.path.basename(path)
        original_name, role = _find_meta(basename)

        display_name = original_name or basename
        label = f"{role} — {display_name}"

        entries.append({
            "resource": path,
            "size": res.get("size", 0),
            "label": label,
            "original_name": original_name,
            "role": role,
        })
    return entries

def list_local_icons(folder: Path) -> list[Path]:
    """Return all image files in *folder* (non-recursive)."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def replace_icon(item: Item, resource_path: str, local_file: Path) -> None:
    """Overwrite the resource at *resource_path* on *item* with *local_file*.

    The resource path is preserved so every place in the ExB config
    that references the image keeps working with no further edits.
    """
    local_file = Path(local_file)
    if not local_file.is_file():
        raise FileNotFoundError(local_file)

    dirname = os.path.dirname(resource_path) or None
    target_basename = os.path.basename(resource_path)

    # ExB resource names must match the original path; we upload with
    # the target filename regardless of the local filename.
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / target_basename
        staged.write_bytes(local_file.read_bytes())
        item.resources.update(
            file=str(staged),
            folder_name=dirname,
            file_name=target_basename,
        )


def download_icon_preview(item: Item, resource_path: str, out_dir: Path) -> Path:
    """Download an item resource locally so it can be previewed."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    basename = os.path.basename(resource_path)
    item.resources.get(
        file=resource_path,
        try_json=False,
        out_folder=str(out_dir),
        out_file_name=basename,
    )
    return out_dir / basename
