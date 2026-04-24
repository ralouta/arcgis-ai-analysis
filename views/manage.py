"""Core helpers for view layer and web map management."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from arcgis.features import FeatureLayer, FeatureLayerCollection
from arcgis.gis import GIS

# ── Constants ─────────────────────────────────────────────────────────

SYSTEM_FIELDS = {"objectid", "globalid"}

STATUS_COLORS = {
    "Pending Review": [255, 170, 0, 200],
    "In Review": [163, 73, 164, 200],
    "Approved": [56, 168, 0, 200],
    "Rejected": [255, 0, 0, 200],
    "Needs Revision": [0, 112, 255, 200],
}

# Per-view default field visibility.  Use "__all__" to mark every field visible.
VIEW_DEFAULTS: dict[str, dict] = {
    "Collector": {
        "visible": {
            "review_status", "revision_notes", "notes",
            "observation_date", "observer",
        },
        "readonly": {"review_status"},
    },
    "Approver": {
        "visible": "__all__",
        "readonly": set(),
    },
    "Public": {
        "visible": {
            "common_name", "latin_name", "family", "plant_type", "condition",
            "height_m", "canopy_width_m", "observation_date", "notes",
        },
        "readonly": set(),
    },
}

# ── Name / title helpers ──────────────────────────────────────────────

def safe_name(label: str) -> str:
    """Convert a human title to a safe service name (alphanumeric + underscores)."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return re.sub(r"_+", "_", name).strip("_")


def clean_title(title: str) -> str:
    """Strip trailing ' - Field Collection' from a title."""
    return re.sub(r"\s*-\s*Field Collection$", "", title, flags=re.IGNORECASE)


# ── View propagation ──────────────────────────────────────────────────

def get_view_layer(view_item, gis: GIS, *, retries: int = 20, delay: int = 8):
    """Re-fetch a view item and return ``(item, layer)``, retrying until propagated."""
    for attempt in range(retries):
        item = gis.content.get(view_item.id)
        try:
            flc_v = FeatureLayerCollection.fromitem(item)
            if flc_v.layers:
                return item, flc_v.layers[0]
        except Exception:
            pass
        if item.url:
            try:
                lyr = FeatureLayer(item.url + "/0", gis=gis)
                _ = lyr.properties
                return item, lyr
            except Exception:
                pass
        if attempt == 0:
            print(f"  View URL: {getattr(item, 'url', '(none)')}")
        print(f"  Waiting for view to propagate... ({attempt + 1}/{retries})")
        time.sleep(delay)
    raise RuntimeError(
        f"View {view_item.title} has no layers after {retries} retries ({retries * delay}s)."
    )


# ── Field configuration ──────────────────────────────────────────────

def build_field_config(base_layer, defaults: dict | None = None) -> tuple[dict, list[str]]:
    """Build per-view field config from *defaults* and actual base layer fields.

    Returns ``(config, selectable_fields)`` where *config* is::

        {view_name: {field_name: {"visible": bool, "readonly": bool}}}

    and *selectable_fields* is the list of non-system field names.
    """
    if defaults is None:
        defaults = VIEW_DEFAULTS

    selectable = [
        f["name"]
        for f in base_layer.properties.fields
        if f["name"].lower() not in SYSTEM_FIELDS
    ]

    config: dict[str, dict] = {}
    for vname, vdef in defaults.items():
        config[vname] = {}
        vis_set = vdef.get("visible", set())
        ro_set = vdef.get("readonly", set())
        all_visible = vis_set == "__all__"
        for fname in selectable:
            config[vname][fname] = {
                "visible": all_visible or fname.lower() in vis_set,
                "readonly": fname.lower() in ro_set,
            }
    return config, selectable


def get_field_updates(base_layer, field_config: dict, *, editable_view: bool = True) -> list[dict]:
    """Build field update dicts from a single view's *field_config* for ``update_definition``."""
    updates = []
    for f in base_layer.properties.fields:
        fname = f["name"]
        if fname.lower() in SYSTEM_FIELDS:
            continue
        fc = field_config.get(fname, {})
        if not fc.get("visible", False):
            updates.append({"name": fname, "visible": False})
        elif editable_view and fc.get("readonly", False):
            updates.append({"name": fname, "editable": False})
        elif editable_view:
            updates.append({"name": fname, "editable": True})
    return updates


def get_hidden_field_updates(base_layer) -> list[dict]:
    """Build field updates that hide **all** non-system fields."""
    return [
        {"name": f["name"], "visible": False}
        for f in base_layer.properties.fields
        if f["name"].lower() not in SYSTEM_FIELDS
    ]


# ── Renderers ─────────────────────────────────────────────────────────

def build_status_renderer() -> dict:
    """Unique-value renderer for ``review_status`` (Collector & Approver views)."""
    return {
        "type": "uniqueValue",
        "field1": "review_status",
        "defaultSymbol": {
            "type": "esriSMS",
            "style": "esriSMSDiamond",
            "color": [0, 200, 255, 220],
            "size": 10,
            "outline": {
                "type": "esriSLS", "style": "esriSLSSolid",
                "color": [255, 255, 255, 255], "width": 1.5,
            },
        },
        "defaultLabel": "New (NULL)",
        "uniqueValueInfos": [
            {
                "value": status,
                "label": status,
                "symbol": {
                    "type": "esriSMS", "style": "esriSMSCircle",
                    "color": color, "size": 8,
                    "outline": {
                        "type": "esriSLS", "style": "esriSLSSolid",
                        "color": [0, 0, 0, 255], "width": 1,
                    },
                },
            }
            for status, color in STATUS_COLORS.items()
        ],
    }


def build_single_renderer(color: list) -> dict:
    """Simple circle renderer with a given fill *color*."""
    return {
        "type": "simple",
        "symbol": {
            "type": "esriSMS",
            "style": "esriSMSCircle",
            "color": color,
            "size": 8,
            "outline": {
                "type": "esriSLS", "style": "esriSLSSolid",
                "color": [255, 255, 255, 255], "width": 1,
            },
        },
    }


def build_pending_renderer() -> dict:
    """Small grey circle with white outline for pending / non-approved features."""
    return {
        "type": "simple",
        "symbol": {
            "type": "esriSMS",
            "style": "esriSMSCircle",
            "color": [160, 160, 160, 180],
            "size": 6,
            "outline": {
                "type": "esriSLS", "style": "esriSLSSolid",
                "color": [255, 255, 255, 255], "width": 1,
            },
        },
    }


# ── View creation ─────────────────────────────────────────────────────

def create_view(
    gis: GIS,
    flc: FeatureLayerCollection,
    base_layer,
    title: str,
    *,
    updateable: bool,
    capabilities: str,
    description: str,
    tags: str,
    snippet: str,
    folder: str | None = None,
    def_query: str | None = None,
    field_updates: list[dict] | None = None,
    renderer: dict | None = None,
):
    """Create a hosted view layer, wait for propagation, and apply optional settings.

    Returns ``(view_item, view_layer)``.
    """
    item = flc.manager.create_view(
        name=safe_name(title),
        updateable=updateable,
        capabilities=capabilities,
        view_layers=[base_layer],
        description=description,
        tags=tags,
        snippet=snippet,
        folder=folder,
    )
    item.update(item_properties={"title": title})
    print(f"  Created view item: {item.id}")
    time.sleep(5)
    item, lyr = get_view_layer(item, gis)

    update_props: dict = {}
    if def_query:
        update_props["viewDefinitionQuery"] = def_query
    if field_updates:
        update_props["fields"] = field_updates
    if renderer:
        update_props["drawingInfo"] = {"renderer": renderer}
    if update_props:
        lyr.manager.update_definition(update_props)

    return item, lyr


# ── Popup builder ─────────────────────────────────────────────────────

def build_popup(view_lyr, field_config: dict) -> dict:
    """Build popup definition from layer fields and *field_config* visibility."""
    field_infos = []
    for f in view_lyr.properties.fields:
        fname = f["name"]
        if fname.lower() in SYSTEM_FIELDS:
            field_infos.append({
                "fieldName": fname, "label": f.get("alias", fname),
                "visible": False, "isEditable": False,
            })
            continue
        fc = field_config.get(fname, {})
        is_visible = fc.get("visible", True)
        is_readonly = fc.get("readonly", False)
        field_infos.append({
            "fieldName": fname, "label": f.get("alias", fname),
            "visible": is_visible,
            "isEditable": is_visible and not is_readonly,
        })
    return {
        "title": "{review_status} — {common_name}",
        "fieldInfos": field_infos,
        "popupElements": [
            {"type": "fields"},
            {"type": "attachments", "displayType": "auto"},
        ],
    }


# ── Web map creation ──────────────────────────────────────────────────

def create_webmap(
    gis: GIS,
    view_item,
    view_lyr,
    title: str,
    snippet: str,
    clean_name: str,
    *,
    editable: bool = True,
    offline: bool = False,
    folder: str | None = None,
    renderer: dict | None = None,
    field_config: dict | None = None,
):
    """Create a Web Map item with an operational layer and popup.

    Returns the web map ``Item``.
    """
    ext = dict(view_lyr.properties.extent)
    sr = ext.get("spatialReference", {"wkid": 4326})
    data_extent = {
        "xmin": ext["xmin"], "ymin": ext["ymin"],
        "xmax": ext["xmax"], "ymax": ext["ymax"],
        "spatialReference": sr if isinstance(sr, dict) else {"wkid": sr},
    }

    popup_info = build_popup(view_lyr, field_config or {})
    geom_type = getattr(view_lyr.properties, "geometryType", "esriGeometryPoint")

    layer_def: dict = {"geometryType": geom_type}
    if editable:
        caps = "Create,Delete,Query,Update,Editing"
        if offline:
            caps += ",Sync"
        layer_def["capabilities"] = caps
    if renderer:
        layer_def["drawingInfo"] = {"renderer": renderer}
    if getattr(view_lyr.properties, "hasAttachments", False):
        layer_def["hasAttachments"] = True

    op_layer = {
        "id": f"layer_{view_item.id[:8]}",
        "title": view_item.title,
        "url": view_lyr.url,
        "itemId": view_item.id,
        "layerType": "ArcGISFeatureLayer",
        "visibility": True,
        "opacity": 1,
        "disablePopup": False,
        "popupInfo": popup_info,
        "layerDefinition": layer_def,
    }

    webmap_json = {
        "operationalLayers": [op_layer],
        "baseMap": {
            "baseMapLayers": [{
                "id": "World_Imagery",
                "title": "World Imagery",
                "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
                "layerType": "ArcGISTiledMapServiceLayer",
                "visibility": True,
                "opacity": 1,
            }],
            "title": "Imagery",
        },
        "initialState": {"viewpoint": {"targetGeometry": data_extent}},
        "version": "2.28",
    }

    if editable or offline:
        webmap_json["applicationProperties"] = {
            "editing": {"locationTracking": {"enabled": False}},
            "offline": {
                "editableLayers": {"enabled": True},
                "readOnlyLayers": {"enabled": False},
                "basemapSwitching": {"enabled": False},
                "syncContribution": {"enabled": False},
            },
        }

    item_props = {
        "title": title,
        "type": "Web Map",
        "snippet": snippet,
        "tags": f"{clean_name}, Web Map",
        "text": json.dumps(webmap_json),
        "extent": (
            f"{data_extent['xmin']},{data_extent['ymin']},"
            f"{data_extent['xmax']},{data_extent['ymax']}"
        ),
    }
    if folder:
        target_folder = gis.content.folders.get(folder)
        result = target_folder.add(item_props)
    else:
        result = gis.content.folders.get().add(item_props)
    wm_item = result.result() if hasattr(result, "result") else result
    wm_item.update(data=json.dumps(webmap_json))

    kw = set(wm_item.typeKeywords or [])
    kw.discard("FieldMapsDisabled")
    kw.discard("CollectorDisabled")
    if editable:
        kw.add("Collector")
    wm_item.update(item_properties={"typeKeywords": list(kw)})

    return wm_item


def _pick_main_op_layer(ops: list) -> dict | None:
    """Return the first operational layer whose title does not contain
    'pending' (case-insensitive), falling back to the first entry if
    every layer is tagged pending or the list is empty."""
    for ol in ops or []:
        if "pending" not in str(ol.get("title", "")).lower():
            return ol
    return (ops[0] if ops else None)


# ── Copy Field Maps configuration from a template web map ────────────

def copy_fieldmaps_config(gis: GIS, source_wm_id: str, target_wm_id: str):
    """Copy Field Maps form config (Arcade expressions, formInfo, templates)
    from a source web map's main (non-Pending) operational layer to the
    target web map's main (non-Pending) operational layer.

    This lets a staging Collector map inherit the production map's Arcade
    calculations, feature templates, and form layout without manual setup.

    Returns ``(target_item, copied_keys)``.
    """
    src_item = gis.content.get(source_wm_id)
    src_data = src_item.get_data()
    tgt_item = gis.content.get(target_wm_id)
    tgt_data = tgt_item.get_data()

    src_ol = _pick_main_op_layer(src_data.get("operationalLayers", []))
    tgt_ol = _pick_main_op_layer(tgt_data.get("operationalLayers", []))
    if not src_ol or not tgt_ol:
        return tgt_item, []

    copied: list[str] = []

    # Keys that carry Field Maps / Arcade / form configuration.
    # Note: ``editingInfo`` carries the source layer's edit timestamps and
    # must NOT be copied — doing so confuses Field Maps offline sync.
    for key in ("formInfo", "templates"):
        if key in src_ol:
            tgt_ol[key] = src_ol[key]
            copied.append(key)

    src_ld = src_ol.get("layerDefinition", {})
    tgt_ld = tgt_ol.setdefault("layerDefinition", {})
    for key in ("expressionInfos",):
        if key in src_ld:
            tgt_ld[key] = src_ld[key]
            copied.append(f"layerDefinition.{key}")

    tgt_item.update(data=json.dumps(tgt_data))
    return tgt_item, copied


# ── Copy Approver config (popup + Field Maps) from a template web map ──

def copy_approver_config(gis: GIS, source_wm_id: str, target_wm_id: str):
    """Copy popup, Field Maps form, templates, and Arcade expressions from
    a template Approver web map's main (non-Pending) operational layer to
    the target Approver web map's main (non-Pending) operational layer.

    The Pending layer is skipped on both source and target so the
    grey-dot layer keeps its empty popup.

    Returns ``(target_item, copied_keys)``.
    """
    src_item = gis.content.get(source_wm_id)
    tgt_item = gis.content.get(target_wm_id)
    src_data = src_item.get_data()
    tgt_data = tgt_item.get_data()

    src_ol = _pick_main_op_layer(src_data.get("operationalLayers", []))
    tgt_ol = _pick_main_op_layer(tgt_data.get("operationalLayers", []))
    if not src_ol or not tgt_ol:
        return tgt_item, []

    copied: list[str] = []

    # Top-level operational-layer keys carrying popup + form config.
    # ``editingInfo`` intentionally excluded — carries source edit
    # timestamps that would confuse Field Maps offline sync.
    for key in ("popupInfo", "formInfo", "templates"):
        if key in src_ol:
            tgt_ol[key] = src_ol[key]
            copied.append(key)

    # layerDefinition sub-keys for Arcade + subtypes.
    # ``typeIdField`` must accompany ``types`` so clients can resolve
    # which field drives the subtype selection.
    src_ld = src_ol.get("layerDefinition", {})
    tgt_ld = tgt_ol.setdefault("layerDefinition", {})
    for key in ("expressionInfos", "types", "typeIdField", "defaultType"):
        if key in src_ld:
            tgt_ld[key] = src_ld[key]
            copied.append(f"layerDefinition.{key}")

    tgt_item.update(data=json.dumps(tgt_data))
    return tgt_item, copied


# ── Add pending layer to an existing web map ──────────────────────────

def add_pending_to_webmap(
    gis: GIS,
    wm_id: str,
    pending_view_item,
    pending_lyr,
    renderer: dict,
    clean_name: str,
):
    """Insert the pending layer into a web map at index 0 (renders under other layers).

    Removes any existing pending entry for the same item first, then saves.
    Returns the updated web map ``Item``.
    """
    wm_item = gis.content.get(wm_id)
    wm_data = wm_item.get_data()

    # Remove previous pending entry (if re-running)
    wm_data["operationalLayers"] = [
        ol for ol in wm_data["operationalLayers"]
        if ol.get("itemId") != pending_view_item.id
    ]

    pending_op_layer = {
        "id": f"pending_{pending_view_item.id[:8]}",
        "title": f"{clean_name} - Pending",
        "url": pending_lyr.url,
        "itemId": pending_view_item.id,
        "layerType": "ArcGISFeatureLayer",
        "visibility": True,
        "opacity": 0.6,
        "disablePopup": True,
        "layerDefinition": {"drawingInfo": {"renderer": renderer}},
        "popupInfo": {"title": "", "fieldInfos": [], "popupElements": []},
    }

    wm_data["operationalLayers"].insert(0, pending_op_layer)
    wm_item.update(data=json.dumps(wm_data))
    return wm_item


# ── Thumbnails ────────────────────────────────────────────────────────

def set_thumbnail(gis: GIS, wm_item, label: str) -> bool:
    """Export the web map with a text overlay as its thumbnail image."""
    import os
    import tempfile
    import requests as _rq

    wm_data = wm_item.get_data()

    extent = None
    try:
        extent = wm_data["initialState"]["viewpoint"]["targetGeometry"]
    except (KeyError, TypeError):
        pass
    if not extent:
        item_ext = wm_item.extent
        if item_ext:
            extent = {
                "xmin": item_ext[0][0], "ymin": item_ext[0][1],
                "xmax": item_ext[1][0], "ymax": item_ext[1][1],
                "spatialReference": {"wkid": 4326},
            }
    if not extent:
        print("no extent available")
        return False

    _token = gis._con.token
    op_layers = wm_data.get("operationalLayers", [])
    for lyr in op_layers:
        if _token:
            lyr["token"] = _token

    # Text overlay
    cx = (extent["xmin"] + extent["xmax"]) / 2
    cy = extent["ymin"] + (extent["ymax"] - extent["ymin"]) * 0.10
    sr = extent.get("spatialReference", {"wkid": 4326})
    text_layer = {
        "id": "label_overlay",
        "opacity": 1,
        "minScale": 0,
        "maxScale": 0,
        "featureCollection": {
            "layers": [{
                "layerDefinition": {
                    "name": "Label",
                    "geometryType": "esriGeometryPoint",
                },
                "featureSet": {
                    "geometryType": "esriGeometryPoint",
                    "features": [{
                        "geometry": {"x": cx, "y": cy, "spatialReference": sr},
                        "symbol": {
                            "type": "esriTS",
                            "color": [255, 255, 255, 255],
                            "backgroundColor": [0, 0, 0, 170],
                            "haloColor": [0, 0, 0, 255],
                            "haloSize": 2,
                            "text": label,
                            "horizontalAlignment": "center",
                            "verticalAlignment": "middle",
                            "font": {
                                "size": 28, "weight": "bold", "family": "Arial",
                            },
                        },
                    }],
                },
            }],
        },
    }
    op_layers.append(text_layer)

    print_url = gis.properties.helperServices.printTask.url
    export_url = print_url.rstrip("/") + "/execute"
    print_json = {
        "mapOptions": {"extent": extent, "showAttribution": False},
        "operationalLayers": op_layers,
        "baseMap": wm_data.get("baseMap", {}),
        "exportOptions": {"outputSize": [600, 400], "dpi": 96},
    }
    payload = {
        "Web_Map_as_JSON": json.dumps(print_json),
        "Format": "PNG32",
        "Layout_Template": "MAP_ONLY",
        "f": "json",
    }

    resp = gis._con.post(export_url, payload, timeout=120)
    result = resp.json() if hasattr(resp, "json") else resp

    img_url = None
    if isinstance(result, dict):
        for r in result.get("results", []):
            val = r.get("value", {})
            if isinstance(val, dict) and "url" in val:
                img_url = val["url"]
                break
        if not img_url and "value" in result:
            val = result["value"]
            if isinstance(val, dict):
                img_url = val.get("url")
            elif isinstance(val, str) and val.startswith("http"):
                img_url = val

    if not img_url:
        print(f"    Response: {json.dumps(result, indent=2)[:500]}")
        return False

    img_data = _rq.get(img_url, timeout=30).content
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(img_data)
        tmp_path = f.name

    wm_item.update(thumbnail=tmp_path)
    os.unlink(tmp_path)
    return True


# ── Registry I/O ──────────────────────────────────────────────────────

def load_registry(registry_path: str | Path) -> dict:
    """Load ``item_registry.json``."""
    return json.loads(Path(registry_path).read_text())


def save_registry(registry_path: str | Path, data: dict) -> None:
    """Save *data* to ``item_registry.json``."""
    Path(registry_path).write_text(json.dumps(data, indent=2))
