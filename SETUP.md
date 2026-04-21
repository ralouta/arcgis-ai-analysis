# Environment Setup & Redeploy Guide

**ArcGIS API for Python** — `arcgis` ≥ 2.4  
Python 3.11+ · [uv](https://docs.astral.sh/uv/)

---

## Prerequisites

Install **uv** (if not already installed):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## First-Time Setup

From the repo root:

```bash
uv sync
```

This creates a `.venv/` virtual environment and installs all dependencies
declared in `pyproject.toml` (arcgis, ipykernel, ipywidgets, requests).

---

## Redeploy / Rebuild Environment

```bash
rm -rf .venv uv.lock
uv sync
```

---

## Verify Installation

```bash
uv run python -c "import arcgis; print(arcgis.__version__)"
```

---

## Select the Kernel in VS Code / Jupyter

1. Open any `.ipynb` notebook.
2. Click **Select Kernel** (top-right).
3. Choose **Python Environments** → `.venv (Python 3.11)` (the local venv).

Or via the Command Palette:  
`Python: Select Interpreter` → select `./.venv/bin/python`.

---

## Legacy: conda setup

If you prefer conda over uv:

```bash
conda create -n arcgis-ai python=3.11 -y
conda install -n arcgis-ai -c esri arcgis ipykernel ipywidgets requests -y
```

---

## Connect to ArcGIS Online

```python
from arcgis.gis import GIS

# Interactive login (browser OAuth)
gis = GIS("home")

# Automation / service account
import os
gis = GIS(
    url="https://www.arcgis.com",
    client_id=os.environ["ARCGIS_CLIENT_ID"],
    client_secret=os.environ["ARCGIS_CLIENT_SECRET"],
)
```

> **Never hardcode credentials.** Store them in environment variables or a `.env` file (excluded from version control).

---

## .gitignore Recommendations

```
__pycache__/
*.pyc
.env
*.ipynb_checkpoints/
```
