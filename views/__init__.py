"""
View layer and web map management utilities.

Provides helpers for creating ArcGIS Online hosted feature layer views,
web maps, renderers, popups, thumbnails, and the item registry.
"""

from views.manage import (
    SYSTEM_FIELDS,
    STATUS_COLORS,
    VIEW_DEFAULTS,
    safe_name,
    clean_title,
    get_view_layer,
    build_field_config,
    get_field_updates,
    get_hidden_field_updates,
    create_view,
    build_status_renderer,
    build_single_renderer,
    build_pending_renderer,
    build_popup,
    create_webmap,
    copy_fieldmaps_config,
    copy_approver_config,
    add_pending_to_webmap,
    set_thumbnail,
    load_registry,
    save_registry,
)
