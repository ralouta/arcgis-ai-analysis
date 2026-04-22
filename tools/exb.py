"""Experience Builder utilities."""

from __future__ import annotations

import json
import os
import tempfile

from arcgis.gis import GIS, Item


def update_datasources(
    config: dict,
    gis: GIS,
    target_webmap_id: str,
) -> dict:
    """Remap every WEB_MAP data source in an Experience Builder config.

    Parameters
    ----------
    config : dict
        The full JSON config obtained via ``item.get_data()``.
    gis : GIS
        Authenticated GIS connection (used to resolve the web map).
    target_webmap_id : str
        Item ID of the web map the app should point to.

    Returns
    -------
    dict
        The mutated *config* (same object, modified in place).
    """
    target_wm = gis.content.get(target_webmap_id)
    if target_wm is None:
        raise ValueError(f"Web map {target_webmap_id} not found")

    wm_data = target_wm.get_data()
    op_layers = wm_data.get("operationalLayers", [])

    # Build a lookup: child key → child dict for the new web map
    new_children: dict[str, dict] = {}
    for layer in op_layers:
        op_id = layer["id"]
        url = layer.get("url", "")
        layer_num = url.rsplit("/", 1)[-1] if "/" in url else "0"
        child_key = f"{op_id}-layer-{layer_num}"

        new_children[child_key] = {
            "id": op_id,
            "type": "FEATURE_LAYER",
            "sourceLabel": layer.get("title", ""),
            "portalUrl": gis.url,
            "itemId": layer.get("itemId", ""),
            "layerId": layer_num,
            "url": url,
        }

    data_sources = config.get("dataSources", {})
    key_mapping: dict[str, str] = {}  # old full ref → new full ref

    for ds_id, ds in data_sources.items():
        if ds.get("type") != "WEB_MAP":
            continue

        old_children = ds.get("childDataSourceJsons", {})

        # Preserve query / dataViews from the first old child as a template
        template_extras: dict = {}
        if old_children:
            first = next(iter(old_children.values()))
            for k in ("dataViews", "query", "fields"):
                if k in first:
                    template_extras[k] = first[k]

        # Apply template extras to new children
        final_children: dict = {}
        for ck, cv in new_children.items():
            merged = {**cv, **template_extras}
            final_children[ck] = merged

        # Build old→new key mapping for widget reference updates
        # Map each old child key to the first new child that shares the same
        # item ID, or fall back to the first new child.
        for old_key, old_child in old_children.items():
            old_item = old_child.get("itemId", "")
            matched = next(
                (nk for nk, nc in final_children.items()
                 if nc.get("itemId") == old_item),
                next(iter(final_children), old_key),
            )
            key_mapping[f"{ds_id}-{old_key}"] = f"{ds_id}-{matched}"

        # Update the data source
        ds["itemId"] = target_webmap_id
        ds["sourceLabel"] = target_wm.title
        ds["portalUrl"] = gis.url
        ds["childDataSourceJsons"] = final_children

    # Global string replacement for widget refs (handles HTML-embedded refs)
    config_str = json.dumps(config)
    for old_ref, new_ref in key_mapping.items():
        if old_ref != new_ref:
            config_str = config_str.replace(old_ref, new_ref)

    return json.loads(config_str)


def copy_resources(source_item: Item, target_item: Item) -> int:
    """Copy all item resources and thumbnail from source to target.

    Parameters
    ----------
    source_item : Item
        The template item to copy resources from.
    target_item : Item
        The newly created item to copy resources to.

    Returns
    -------
    int
        Number of resources copied.
    """
    resource_list = source_item.resources.list()
    copied = 0

    if resource_list:
        with tempfile.TemporaryDirectory() as tmpdir:
            for entry in resource_list:
                res_path = entry["resource"]
                dirname = os.path.dirname(res_path) or None
                basename = os.path.basename(res_path)

                source_item.resources.get(
                    file=res_path,
                    try_json=False,
                    out_folder=tmpdir,
                    out_file_name=basename,
                )
                local_path = os.path.join(tmpdir, basename)

                target_item.resources.add(
                    file=local_path,
                    folder_name=dirname,
                    file_name=basename,
                )
                os.remove(local_path)
                copied += 1

    # Copy thumbnail separately (not part of resources)
    if source_item.thumbnail:
        with tempfile.TemporaryDirectory() as thumb_dir:
            thumb_path = source_item.download_thumbnail(save_folder=thumb_dir)
            if thumb_path and os.path.exists(thumb_path):
                target_item.update(thumbnail=thumb_path)

    return copied
