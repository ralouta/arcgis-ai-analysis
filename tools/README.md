# ArcGIS API Introspection Tools

## Overview
The `tools/arcgis_inspect.py` CLI helps the agent discover the correct `arcgis` modules, classes, functions, and signatures at runtime — no guessing.

## When to Use
- **Before writing code** that calls an `arcgis` API you're not 100% sure about.
- **When choosing between submodules** (e.g. `arcgis.raster.analytics` vs `arcgis.features`).
- **When you need exact function signatures** or parameter names.

## Commands

### 1. List all top-level arcgis submodules
```bash
python tools/arcgis_inspect.py modules
```
Returns every `arcgis.*` subpackage/module with a one-line summary.

### 2. List public members of a module
```bash
python tools/arcgis_inspect.py members arcgis.raster.analytics
```
Shows all classes, functions, and constants in the given module.

### 3. Get the signature + docstring of a specific function/class
```bash
python tools/arcgis_inspect.py sig arcgis.raster.analytics.detect_objects_using_deep_learning
```
Prints the full signature and first paragraph of the docstring.

### 4. Search across all arcgis submodules by keyword
```bash
python tools/arcgis_inspect.py search detect_objects
```
Finds every public name matching the keyword across the entire `arcgis` package.

## Workflow
1. **Discover** → `search <keyword>` to find what exists.
2. **Explore** → `members <module>` to see everything in the relevant module.
3. **Confirm** → `sig <fully.qualified.name>` to get the exact signature before writing code.
