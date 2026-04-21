"""
Field data-collection schemas for hosted feature layers.

Each submodule exposes:
  FIELDS        – list of Esri field dicts (including OBJECTID / GlobalID)
  DOMAINS       – list of coded-value domain dicts
  LAYER_META    – dict with name, description, geometryType, renderer, etc.
  SCHEMA_INFO   – dict with label, description (for the notebook dropdown)

The notebook merges these with the standard approval-workflow fields,
editor tracking, and attachment support automatically.
"""

# Registry: label → module path
SCHEMAS = {
    "Plant Identification": "schemas.plant_id",
}
