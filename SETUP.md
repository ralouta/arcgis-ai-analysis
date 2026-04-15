# Environment Setup & Redeploy Guide

**ArcGIS API for Python** — `arcgis` 2.4.3  
Python 3.11 · conda (Miniforge) · macOS (arm64)

---

## Prerequisites

Install Miniforge (if not already installed):

```bash
brew install miniforge
conda init zsh   # then restart your terminal
```

---

## First-Time Setup

### 1. Create the conda environment

```bash
conda create -n arcgis-ai python=3.11 -y
```

### 2. Install ArcGIS API for Python from Esri's channel

```bash
conda install -n arcgis-ai -c esri arcgis ipykernel -y
```

### 3. Activate the environment

```bash
conda activate arcgis-ai
```

---

## Redeploy / Rebuild Environment

Use these steps whenever the environment is missing or corrupted.

```bash
conda env remove -n arcgis-ai -y
conda create -n arcgis-ai python=3.11 -y
conda install -n arcgis-ai -c esri arcgis ipykernel -y
```

---

## Update ArcGIS API to Latest

```bash
conda activate arcgis-ai
conda update -c esri arcgis -y
```

---

## Verify Installation

```bash
conda run -n arcgis-ai python -c "import arcgis; print(arcgis.__version__)"
```

Expected output: `2.4.3`

---

## Select the Kernel in VS Code / Jupyter

1. Open any `.ipynb` notebook.
2. Click **Select Kernel** (top-right).
3. Choose **Python Environments** → `arcgis-ai (Python 3.11)`.

Or via the Command Palette:  
`Python: Select Interpreter` → select the `arcgis-ai` conda env.

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
