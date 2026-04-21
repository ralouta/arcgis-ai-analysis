"""
QA/QC shape-correction tools for deep-learning object detections.

Each submodule exposes a ``run(features, spatial_reference, **params)`` function
that returns an ``arcgis.features.FeatureSet`` of corrected point geometries.
"""

# Registry: label → module path (relative import)
TOOLS = {
    "Tree Points": "qaqc.tree",
}
