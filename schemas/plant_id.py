"""
Plant Identification schema for field data collection.

Designed for horticultural surveys where observers photograph plants
and AI later extracts species, condition, and measurements from the images.
"""

SCHEMA_INFO = {
    "label": "Plant Identification",
    "description": (
        "Horticultural plant identification observations with photo attachments. "
        "Observers capture a photo per plant; AI fills species, condition, and measurements."
    ),
}

# ── Coded-value domains ─────────────────────────────────────────────────
condition_domain = {
    "type": "codedValue",
    "name": "PlantConditionDomain",
    "description": "Overall health/condition of the observed plant.",
    "fieldType": "esriFieldTypeString",
    "codedValues": [
        {"name": "Healthy",  "code": "Healthy"},
        {"name": "Stressed", "code": "Stressed"},
        {"name": "Diseased", "code": "Diseased"},
        {"name": "Dead",     "code": "Dead"},
    ],
    "mergePolicy": "esriMPTDefaultValue",
    "splitPolicy": "esriSPTDuplicate",
}

plant_type_domain = {
    "type": "codedValue",
    "name": "PlantTypeDomain",
    "description": "Horticultural life-form category.",
    "fieldType": "esriFieldTypeString",
    "codedValues": [
        {"name": "Tree",      "code": "Tree"},
        {"name": "Shrub",     "code": "Shrub"},
        {"name": "Herb",      "code": "Herb"},
        {"name": "Vine",      "code": "Vine"},
        {"name": "Succulent", "code": "Succulent"},
        {"name": "Grass",     "code": "Grass"},
    ],
    "mergePolicy": "esriMPTDefaultValue",
    "splitPolicy": "esriSPTDuplicate",
}

DOMAINS = [condition_domain, plant_type_domain]

# ── Fields (schema-specific only; OBJECTID/GlobalID/approval/editor added by notebook) ──
FIELDS = [
    {
        "name": "common_name",
        "type": "esriFieldTypeString",
        "alias": "Common Name",
        "length": 100,
        "nullable": True,
        "editable": True,
        "description": "Common/vernacular name (e.g. 'Coast Live Oak').",
    },
    {
        "name": "latin_name",
        "type": "esriFieldTypeString",
        "alias": "Latin Name",
        "length": 120,
        "nullable": True,
        "editable": True,
        "description": "Binomial scientific name (Genus species).",
    },
    {
        "name": "family",
        "type": "esriFieldTypeString",
        "alias": "Family",
        "length": 80,
        "nullable": True,
        "editable": True,
        "description": "Botanical family (e.g. Fagaceae).",
    },
    {
        "name": "plant_type",
        "type": "esriFieldTypeString",
        "alias": "Plant Type",
        "length": 25,
        "nullable": True,
        "editable": True,
        "description": "Horticultural life-form category.",
        "domain": plant_type_domain,
    },
    {
        "name": "condition",
        "type": "esriFieldTypeString",
        "alias": "Plant Condition",
        "length": 25,
        "nullable": True,
        "editable": True,
        "description": "Overall plant health.",
        "domain": condition_domain,
    },
    {
        "name": "height_m",
        "type": "esriFieldTypeDouble",
        "alias": "Height (m)",
        "nullable": True,
        "editable": True,
        "description": "Estimated plant height in meters.",
    },
    {
        "name": "canopy_width_m",
        "type": "esriFieldTypeDouble",
        "alias": "Canopy Width (m)",
        "nullable": True,
        "editable": True,
        "description": "Canopy width/diameter in meters. Inherited from radius_m × 2 for tree circles.",
    },
    {
        "name": "observation_date",
        "type": "esriFieldTypeDate",
        "alias": "Observation Date",
        "nullable": True,
        "editable": True,
        "description": "When the observation was recorded.",
        "defaultValue": None,
    },
    {
        "name": "observer",
        "type": "esriFieldTypeString",
        "alias": "Observer",
        "length": 100,
        "nullable": True,
        "editable": True,
        "description": "Name or initials of the person collecting the record.",
    },
    {
        "name": "notes",
        "type": "esriFieldTypeString",
        "alias": "Field Notes",
        "length": 500,
        "nullable": True,
        "editable": True,
        "description": "Free-form notes about the observation.",
    },
]

# ── Layer metadata ───────────────────────────────────────────────────────
LAYER_META = {
    "name": "Plant_Observations",
    "description": "Horticultural plant identification observations with photo attachments.",
    "geometryType": "esriGeometryPoint",
    "drawingInfo": {
        "renderer": {
            "type": "simple",
            "symbol": {
                "type": "esriSMS",
                "style": "esriSMSCircle",
                "color": [34, 139, 34, 180],
                "size": 9,
                "outline": {"color": [0, 0, 0, 255], "width": 0.75},
            },
        },
    },
    "templates": [
        {
            "name": "New Plant Observation",
            "description": "Default template for plant observations.",
            "drawingTool": "esriFeatureEditToolPoint",
            "prototype": {
                "attributes": {
                    "condition": "Healthy",
                    "plant_type": "Tree",
                }
            },
        }
    ],
}
