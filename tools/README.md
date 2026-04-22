# Tools

Utility modules used by the notebooks and agents in this project.

---

## `arcgis_inspect.py` — ArcGIS API Introspection

The CLI helps the agent discover the correct `arcgis` modules, classes, functions, and signatures at runtime — no guessing.

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

---

## `exb.py` — Experience Builder Utilities

Helpers for cloning and configuring ArcGIS Experience Builder apps programmatically.

### Functions

#### `update_datasources(config, gis, target_webmap_id) -> dict`
Remaps every `WEB_MAP` data source in an ExB config to point at a new web map. Operates on the JSON config dict returned by `item.get_data()` and mutates it in place.

```python
from tools.exb import update_datasources

config = template_item.get_data()
config = update_datasources(config, gis, new_webmap.id)
```

#### `copy_resources(source_item, target_item) -> int`
Copies all item resources (images, widget assets, etc.) and the thumbnail from a template ExB item to a newly created one. Returns the number of resources copied.

This is needed because `folder.add()` only uploads the JSON config — item resources are stored separately and must be transferred explicitly.

```python
from tools.exb import copy_resources

copied = copy_resources(template_item, new_item)
print(f"{copied} resources copied")
```
