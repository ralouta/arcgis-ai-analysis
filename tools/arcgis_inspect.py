#!/usr/bin/env python3
"""
ArcGIS API for Python – module introspection CLI.

Usage
-----
  # List all top-level arcgis subpackages / modules
  python tools/arcgis_inspect.py modules

  # List public members of a specific submodule (classes, functions, constants)
  python tools/arcgis_inspect.py members arcgis.raster.analytics

  # Show the signature + first paragraph of a specific callable
  python tools/arcgis_inspect.py sig arcgis.raster.analytics.detect_objects_using_deep_learning

  # Search across all arcgis submodules for a name containing a keyword
  python tools/arcgis_inspect.py search detect_objects
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import pkgutil
import sys
import textwrap


# ── helpers ──────────────────────────────────────────────────────────────────

def _import(dotted: str):
    """Import a dotted path, falling back to getattr for nested attributes."""
    parts = dotted.split(".")
    mod = None
    for i in range(len(parts), 0, -1):
        try:
            mod = importlib.import_module(".".join(parts[:i]))
            break
        except ModuleNotFoundError:
            continue
    if mod is None:
        raise ModuleNotFoundError(f"Cannot import any prefix of '{dotted}'")
    obj = mod
    for attr in parts[i:]:
        obj = getattr(obj, attr)
    return obj


def _short_doc(obj, max_lines: int = 5) -> str:
    """Return the first paragraph of the docstring, trimmed."""
    doc = inspect.getdoc(obj)
    if not doc:
        return "(no docstring)"
    lines: list[str] = []
    for line in doc.splitlines():
        if not line.strip() and lines:
            break
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return textwrap.dedent("\n".join(lines)).strip()


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_modules(_args: argparse.Namespace) -> None:
    """Print every importable arcgis.* subpackage / module (one level deep)."""
    import arcgis  # noqa: F811

    print("Top-level arcgis submodules / subpackages\n" + "=" * 48)
    for importer, modname, ispkg in sorted(
        pkgutil.walk_packages(arcgis.__path__, prefix="arcgis."),
        key=lambda t: t[1],
    ):
        depth = modname.count(".") - 1  # 0 = direct child of arcgis
        if depth > 1:
            continue  # keep it one level deep by default
        kind = "pkg" if ispkg else "mod"
        try:
            m = importlib.import_module(modname)
            summary = (_short_doc(m, max_lines=1) or "")[:90]
        except Exception:
            summary = "(import error)"
        indent = "  " * depth
        print(f"  {indent}{modname:<40} [{kind}]  {summary}")


def cmd_members(args: argparse.Namespace) -> None:
    """List public classes, functions, and constants in a module."""
    mod = _import(args.module)
    print(f"Public members of {args.module}\n" + "=" * 48)
    members = sorted(
        [(n, o) for n, o in inspect.getmembers(mod) if not n.startswith("_")],
        key=lambda t: (not inspect.isclass(t[1]), not inspect.isfunction(t[1]), t[0]),
    )
    for name, obj in members:
        if inspect.isclass(obj):
            kind = "class"
        elif inspect.isfunction(obj) or inspect.isbuiltin(obj):
            kind = "func "
        elif inspect.ismodule(obj):
            kind = "mod  "
        else:
            kind = "const"
        summary = (_short_doc(obj, max_lines=1) or "")[:80]
        print(f"  {name:<45} [{kind}]  {summary}")


def cmd_sig(args: argparse.Namespace) -> None:
    """Show the full signature and first-paragraph docstring of a callable."""
    obj = _import(args.name)
    print(f"{args.name}")
    try:
        sig = inspect.signature(obj)
        print(f"  Signature: {args.name.split('.')[-1]}{sig}")
    except (ValueError, TypeError):
        print("  (signature not available)")
    print()
    doc = _short_doc(obj, max_lines=15)
    print(textwrap.indent(doc, "  "))

    # Show parameter docs if available
    full_doc = inspect.getdoc(obj) or ""
    param_section = []
    in_params = False
    for line in full_doc.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("parameter") or stripped.startswith(":param"):
            in_params = True
        if in_params:
            param_section.append(line)
            if len(param_section) > 60:
                break
        if in_params and not line.strip() and len(param_section) > 2:
            break
    if param_section:
        print("\n  Parameters (excerpt):")
        for pl in param_section[:50]:
            print(f"  {pl}")


def cmd_search(args: argparse.Namespace) -> None:
    """Search all arcgis submodules for names matching a keyword."""
    import arcgis  # noqa: F811

    keyword = args.keyword.lower()
    print(f"Searching arcgis.* for '{args.keyword}'\n" + "=" * 48)

    hits: list[str] = []
    seen_modules: set[str] = set()

    for _importer, modname, _ispkg in pkgutil.walk_packages(
        arcgis.__path__, prefix="arcgis."
    ):
        if modname in seen_modules:
            continue
        seen_modules.add(modname)
        try:
            mod = importlib.import_module(modname)
        except Exception:
            continue
        for name in dir(mod):
            if name.startswith("_"):
                continue
            if keyword in name.lower():
                obj = getattr(mod, name, None)
                if inspect.isclass(obj):
                    kind = "class"
                elif callable(obj):
                    kind = "func"
                else:
                    kind = "other"
                full = f"{modname}.{name}"
                if full not in hits:
                    hits.append(full)
                    summary = (_short_doc(obj, max_lines=1) or "")[:70]
                    print(f"  {full:<60} [{kind}]  {summary}")

    if not hits:
        print("  (no matches)")
    else:
        print(f"\n  {len(hits)} match(es) found.")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Introspect the arcgis Python package."
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("modules", help="List top-level arcgis submodules")

    p_members = sub.add_parser("members", help="List public members of a module")
    p_members.add_argument("module", help="Dotted module path, e.g. arcgis.raster.analytics")

    p_sig = sub.add_parser("sig", help="Show signature + docstring of a callable")
    p_sig.add_argument("name", help="Fully qualified name, e.g. arcgis.raster.analytics.detect_objects_using_deep_learning")

    p_search = sub.add_parser("search", help="Search for a keyword across arcgis.*")
    p_search.add_argument("keyword", help="Keyword to search for in member names")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "modules": cmd_modules,
        "members": cmd_members,
        "sig": cmd_sig,
        "search": cmd_search,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
