"""Experience Builder utilities."""

from __future__ import annotations

import json
import os
import tempfile

from arcgis.gis import GIS, Item


def _child_match_tokens(child_key: str, child: dict) -> tuple[str | None, str | None]:
    """Return stable tokens that can match an ExB child data source."""
    layer_id = child.get("layerId")
    if layer_id is None and "-layer-" in child_key:
        layer_id = child_key.rsplit("-layer-", 1)[-1]

    source_label = child.get("sourceLabel") or child.get("label") or child.get("id")
    if source_label is not None:
        source_label = str(source_label)

    if layer_id is not None:
        layer_id = str(layer_id)

    return layer_id, source_label


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

    # Build a lookup: child key → child dict template for the new web map.
    # Key convention matches ExB: child key = operational layer id (no suffix).
    # The child's internal "id" is set per data source later as f"{ds_id}-{key}".
    new_children: dict[str, dict] = {}
    for layer in op_layers:
        op_id = layer["id"]
        url = layer.get("url", "")
        layer_num = url.rsplit("/", 1)[-1] if "/" in url else "0"
        child_key = op_id

        new_children[child_key] = {
            "type": "FEATURE_LAYER",
            "sourceLabel": layer.get("title", ""),
            "portalUrl": gis.url,
            "itemId": layer.get("itemId", ""),
            "layerId": layer_num,
            "url": url,
        }

    data_sources = config.get("dataSources", {})
    key_mapping: dict[str, str] = {}  # old full ref → new full ref
    child_item_mapping: dict[str, dict] = {}
    value_replacements: dict[str, str] = {}

    for ds_id, ds in data_sources.items():
        if ds.get("type") != "WEB_MAP":
            continue

        old_children = ds.get("childDataSourceJsons", {})

        # Match each old child to the corresponding new child using stable
        # layer metadata, then preserve that old child's own settings.
        matched_keys: dict[str, str] = {}
        final_children: dict = {}
        fallback_key = next(iter(new_children), None)
        used_new_keys: set[str] = set()

        def _label_tokens(text) -> set:
            if not text:
                return set()
            cleaned = "".join(c.lower() if c.isalnum() else " " for c in str(text))
            # drop common filler tokens that don't disambiguate layers
            ignore = {"ai", "staging", "plant", "identification", "the", "a", "of", "for", "-"}
            return {tok for tok in cleaned.split() if tok and tok not in ignore and not tok.isdigit()}

        for old_key, old_child in old_children.items():
            old_layer_id, old_label = _child_match_tokens(old_key, old_child)
            old_tokens = _label_tokens(old_label) | _label_tokens(old_key)

            matched = None
            best_overlap = 0

            # First pass: pick the new child whose label tokens overlap the old
            # child's label tokens the most. This lets us map e.g. "…Approver…"
            # to "…Approver…" even when prefixes / suffixes differ, and it
            # outranks a naive layerId match when multiple children share
            # the same layer id (very common with views on layer 0).
            for new_key, new_child in new_children.items():
                if new_key in used_new_keys:
                    continue
                _, new_label = _child_match_tokens(new_key, new_child)
                new_tokens = _label_tokens(new_label) | _label_tokens(new_key)
                overlap = len(old_tokens & new_tokens)
                if overlap > best_overlap:
                    best_overlap = overlap
                    matched = new_key

            # Second pass: fall back to layerId match if no label overlap
            if matched is None:
                for new_key, new_child in new_children.items():
                    if new_key in used_new_keys:
                        continue
                    new_layer_id, _ = _child_match_tokens(new_key, new_child)
                    if old_layer_id and new_layer_id == old_layer_id:
                        matched = new_key
                        break

            if matched is None:
                matched = next((key for key in new_children if key not in used_new_keys), fallback_key)
            if matched is None:
                continue

            used_new_keys.add(matched)
            matched_keys[old_key] = matched

            merged = dict(new_children[matched])
            merged["id"] = f"{ds_id}-{matched}"
            # Preserve only non-schema settings from the old child. The old
            # template's schema/fields/query/dataViews refer to a different
            # layer and cause ExB to fail creating the data source at runtime
            # ("Create data source error"). Let ExB rebuild schema/fields
            # from the actual new layer service.
            for key in ("gdbVersion", "dataViews"):
                if key in old_child:
                    merged[key] = old_child[key]
            final_children[matched] = merged

        for new_key, new_child in new_children.items():
            if new_key not in final_children:
                child_copy = dict(new_child)
                child_copy["id"] = f"{ds_id}-{new_key}"
                final_children[new_key] = child_copy

        # Build old→new key mapping for widget reference updates
        for old_key, old_child in old_children.items():
            matched = matched_keys.get(old_key, next(iter(final_children), old_key))
            key_mapping[f"{ds_id}-{old_key}"] = f"{ds_id}-{matched}"

            old_item_id = old_child.get("itemId")
            if old_item_id and matched in final_children:
                mapped_child = dict(final_children[matched])
                child_item_mapping[str(old_item_id)] = mapped_child
                new_item_id = mapped_child.get("itemId")
                if new_item_id and str(old_item_id) != str(new_item_id):
                    value_replacements[str(old_item_id)] = str(new_item_id)

            old_url = old_child.get("url")
            new_url = final_children.get(matched, {}).get("url")
            if old_url and new_url and str(old_url) != str(new_url):
                value_replacements[str(old_url)] = str(new_url)

        # Save original ID for global replacement later
        ds["_original_itemId"] = ds.get("itemId", "")
        # Update the data source
        ds["itemId"] = target_webmap_id
        ds["sourceLabel"] = target_wm.title
        ds["portalUrl"] = gis.url
        ds["childDataSourceJsons"] = final_children

    for ds in data_sources.values():
        if ds.get("type") != "FEATURE_LAYER":
            continue

        mapped = child_item_mapping.get(str(ds.get("itemId", "")))
        if not mapped:
            continue

        ds["itemId"] = mapped.get("itemId", ds.get("itemId", ""))
        ds["sourceLabel"] = mapped.get("sourceLabel", ds.get("sourceLabel", ""))
        ds["portalUrl"] = mapped.get("portalUrl", gis.url)
        ds["layerId"] = mapped.get("layerId", ds.get("layerId"))
        ds["url"] = mapped.get("url", ds.get("url", ""))

    # Collect old web map IDs for global replacement
    old_wm_ids: set[str] = set()
    for ds in data_sources.values():
        if ds.get("type") == "WEB_MAP":
            old_id = ds.get("_original_itemId")
            if old_id and old_id != target_webmap_id:
                old_wm_ids.add(old_id)

    # Global string replacement for widget refs AND web map IDs
    config_str = json.dumps(config)
    for old_ref, new_ref in key_mapping.items():
        if old_ref != new_ref:
            config_str = config_str.replace(old_ref, new_ref)
    for old_wm_id in old_wm_ids:
        config_str = config_str.replace(old_wm_id, target_webmap_id)
    for old_value, new_value in value_replacements.items():
        config_str = config_str.replace(old_value, new_value)

    result = json.loads(config_str)
    # Clean up internal markers
    for ds in result.get("dataSources", {}).values():
        ds.pop("_original_itemId", None)
    return result


def sync_config_resources(target_item: Item, config: dict) -> int:
    """Overwrite Experience Builder draft config resources with *config*."""
    resource_list = target_item.resources.list()
    updated = 0

    if not resource_list:
        return updated

    with tempfile.TemporaryDirectory() as tmpdir:
        for entry in resource_list:
            res_path = entry["resource"]
            if not res_path.endswith(".json"):
                continue

            dirname = os.path.dirname(res_path) or None
            basename = os.path.basename(res_path)
            target_item.resources.get(
                file=res_path,
                try_json=False,
                out_folder=tmpdir,
                out_file_name=basename,
            )
            local_path = os.path.join(tmpdir, basename)

            try:
                with open(local_path) as fh:
                    blob = json.load(fh)
            except (json.JSONDecodeError, UnicodeDecodeError):
                os.remove(local_path)
                continue

            if not isinstance(blob, dict) or "dataSources" not in blob:
                os.remove(local_path)
                continue

            with open(local_path, "w") as fh:
                json.dump(config, fh)

            target_item.resources.update(
                file=local_path,
                folder_name=dirname,
                file_name=basename,
            )
            os.remove(local_path)
            updated += 1

    return updated


def copy_resources(
    source_item: Item,
    target_item: Item,
    config: dict | None = None,
) -> int:
    """Copy item resources and thumbnail from source to target.

    If *config* is provided, any JSON resource that contains an ExB
    config (identified by a top-level dataSources key) is replaced
    with the remapped config so the editor draft matches the published
    item data.

    Parameters
    ----------
    source_item : Item
        The template item to copy resources from.
    target_item : Item
        The newly created item to copy resources to.
    config : dict, optional
        Remapped ExB config to write over any draft config resources.

    Returns
    -------
    int
        Number of resources copied.
    """
    # Auto-read the published config from the target item so we can
    # overwrite any draft config resources without the caller needing
    # to pass it explicitly.
    if config is None:
        loaded_config = target_item.get_data()
        config = loaded_config if isinstance(loaded_config, dict) else None

    resource_list = source_item.resources.list()
    copied = 0

    if resource_list:
        with tempfile.TemporaryDirectory() as tmpdir:
            for entry in resource_list:
                res_path = entry["resource"]
                dirname = os.path.dirname(res_path) or None
                basename = os.path.basename(res_path)

                # Download the resource
                source_item.resources.get(
                    file=res_path,
                    try_json=False,
                    out_folder=tmpdir,
                    out_file_name=basename,
                )
                local_path = os.path.join(tmpdir, basename)

                # If a replacement config was given, check whether this
                # resource is an ExB config JSON and swap it out.
                if config is not None and res_path.endswith(".json"):
                    try:
                        with open(local_path) as fh:
                            blob = json.load(fh)
                        if isinstance(blob, dict) and "dataSources" in blob:
                            with open(local_path, "w") as fh:
                                json.dump(config, fh)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass

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
