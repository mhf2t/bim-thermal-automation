# ifc_parser.py
# ============================================================
# IFC Parser (baseline version)
# - Extract walls, roofs, windows
# - Compute U-values via ISO 6946 using material layer set
# - Load thermal DB and match lambda
# ============================================================

from __future__ import annotations

import os
import re
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd

try:
    import ifcopenshell
    import ifcopenshell.util.element as ifc_el
except Exception as e:
    raise ImportError("ifcopenshell is required for ifc_parser.py") from e


# ----------------------------
# small utils
# ----------------------------
_WS = re.compile(r"\s+")


def _norm_key(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = _WS.sub(" ", s)
    return s


def _safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


# ----------------------------
# Thermal DB loader (baseline)
# ----------------------------
def load_thermal_database(csv_path: str) -> pd.DataFrame:
    """
    Minimal required columns (case-insensitive):
      - material_name / material / name
      - lambda / lambda_value / conductivity / k
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Thermal database CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    cols = {c.lower().strip(): c for c in df.columns}

    name_col = None
    for c in ["material_name", "material", "name"]:
        if c in cols:
            name_col = cols[c]
            break

    lam_col = None
    for c in ["lambda_value", "lambda", "conductivity", "k"]:
        if c in cols:
            lam_col = cols[c]
            break

    if not name_col or not lam_col:
        raise ValueError(
            "Thermal DB CSV must contain material name and lambda/conductivity.\n"
            f"Found columns: {list(df.columns)}"
        )

    out = df.copy()
    out["__mat_name__"] = out[name_col].astype(str).fillna("").str.strip()
    out["__mat_key__"] = out["__mat_name__"].map(_norm_key)
    out["__lambda__"] = pd.to_numeric(out[lam_col], errors="coerce")

    out = out[out["__lambda__"].notna()].reset_index(drop=True)

    if out.empty:
        raise ValueError("Thermal DB loaded but has no valid lambda values after cleaning.")

    return out


def _match_lambda(material_name: str, db: pd.DataFrame) -> Tuple[Optional[float], str, str]:
    """
    Return (lambda, matched_material, confidence)
    confidence: high/medium/low
    """
    key = _norm_key(material_name)
    if not key:
        return None, "—", "low"

    hit = db[db["__mat_key__"] == key]
    if not hit.empty:
        row = hit.iloc[0]
        return float(row["__lambda__"]), str(row["__mat_name__"]), "high"

    # baseline: simple contains match
    for _, row in db.iterrows():
        dk = row["__mat_key__"]
        if dk and (dk in key or key in dk):
            return float(row["__lambda__"]), str(row["__mat_name__"]), "medium"

    return None, "—", "low"


# ----------------------------
# ISO 6946 U-value
# ----------------------------
def _u_value_from_layers(layers: List[Dict[str, Any]]) -> Optional[float]:
    """
    U = 1 / (Rsi + Σ(d/lambda) + Rso)
    Baseline uses fixed Rsi=0.13, Rso=0.04.
    thickness_mm is expected.
    """
    Rsi = 0.13
    Rso = 0.04

    r_sum = 0.0
    for layer in layers:
        th_mm = _safe_float(layer.get("thickness_mm"), 0.0) or 0.0
        lam = _safe_float(layer.get("lambda"), None)
        if th_mm <= 0 or lam is None or lam <= 0:
            continue
        d_m = th_mm / 1000.0
        r_sum += d_m / lam

    r_total = Rsi + r_sum + Rso
    if r_total <= 0:
        return None
    return 1.0 / r_total


# ----------------------------
# IFC material layer extraction (baseline)
# ----------------------------
def _extract_layers(elem, thermal_db: pd.DataFrame) -> Tuple[List[Dict[str, Any]], float]:
    """
    Try to read IfcMaterialLayerSetUsage/IfcMaterialLayerSet.
    Returns (layers, total_thickness_mm)
    """
    layers: List[Dict[str, Any]] = []
    total_th = 0.0

    assoc = getattr(elem, "HasAssociations", None) or []
    for rel in assoc:
        if not rel or not rel.is_a("IfcRelAssociatesMaterial"):
            continue

        mat = rel.RelatingMaterial
        if mat is None:
            continue

        # IfcMaterialLayerSetUsage
        if mat.is_a("IfcMaterialLayerSetUsage"):
            ls = mat.ForLayerSet
            mls = getattr(ls, "MaterialLayers", None) or []
            for ml in mls:
                mname = ""
                if getattr(ml, "Material", None):
                    mname = str(getattr(ml.Material, "Name", "") or "")
                th = _safe_float(getattr(ml, "LayerThickness", None), 0.0) or 0.0
                th_mm = th * 1000.0 if th <= 1.0 else th

                lam, matched, conf = _match_lambda(mname, thermal_db)
                if lam is None:
                    lam = 0.50
                    matched = "DEFAULT(0.50)"
                    conf = "low"

                layers.append({
                    "material_name": mname,
                    "matched_material": matched,
                    "confidence": conf,
                    "thickness_mm": float(th_mm),
                    "lambda": float(lam),
                    "r_value": float((th_mm / 1000.0) / lam) if lam > 0 else 0.0,
                })
                total_th += float(th_mm)

            break

        # IfcMaterialLayerSet
        if mat.is_a("IfcMaterialLayerSet"):
            mls = getattr(mat, "MaterialLayers", None) or []
            for ml in mls:
                mname = ""
                if getattr(ml, "Material", None):
                    mname = str(getattr(ml.Material, "Name", "") or "")
                th = _safe_float(getattr(ml, "LayerThickness", None), 0.0) or 0.0
                th_mm = th * 1000.0 if th <= 1.0 else th

                lam, matched, conf = _match_lambda(mname, thermal_db)
                if lam is None:
                    lam = 0.50
                    matched = "DEFAULT(0.50)"
                    conf = "low"

                layers.append({
                    "material_name": mname,
                    "matched_material": matched,
                    "confidence": conf,
                    "thickness_mm": float(th_mm),
                    "lambda": float(lam),
                    "r_value": float((th_mm / 1000.0) / lam) if lam > 0 else 0.0,
                })
                total_th += float(th_mm)

            break

    return layers, total_th


def _get_pset_value(elem, pset: str, prop: str):
    try:
        psets = ifc_el.get_psets(elem) or {}
        return (psets.get(pset) or {}).get(prop)
    except Exception:
        return None


def _extract_area_m2(elem) -> float:
    # Baseline tries a few common quantities; else 0
    for pset, prop in [
        ("Qto_WallBaseQuantities", "NetSideArea"),
        ("Qto_WallBaseQuantities", "GrossSideArea"),
        ("Qto_RoofBaseQuantities", "NetArea"),
        ("Qto_RoofBaseQuantities", "GrossArea"),
        ("Qto_WindowBaseQuantities", "Area"),
    ]:
        v = _safe_float(_get_pset_value(elem, pset, prop), None)
        if v and v > 0:
            return float(v)
    return 0.0


def _get_name(elem) -> str:
    try:
        return str(getattr(elem, "Name", "") or "") or str(getattr(elem, "ObjectType", "") or "")
    except Exception:
        return ""


def _get_gid(elem) -> str:
    try:
        return str(getattr(elem, "GlobalId", "") or "")
    except Exception:
        return ""


# ----------------------------
# Main parse
# ----------------------------
def parse_ifc(ifc_path: str, thermal_db: pd.DataFrame) -> Dict[str, Any]:
    """
    Baseline behavior:
    - returns dict (never None)
    - if some categories missing, returns empty lists
    """
    if not os.path.exists(ifc_path):
        raise RuntimeError(f"IFC file not found: {ifc_path}")

    try:
        ifc = ifcopenshell.open(ifc_path)
    except Exception as e:
        raise RuntimeError(f"Could not open IFC: {e}") from e

    schema = str(getattr(ifc, "schema", None) or "Unknown")

    walls: List[Dict[str, Any]] = []
    roofs: List[Dict[str, Any]] = []
    windows: List[Dict[str, Any]] = []

    # Walls
    try:
        ifc_walls = (ifc.by_type("IfcWall") or []) + (ifc.by_type("IfcWallStandardCase") or [])
    except Exception:
        ifc_walls = []

    for w in ifc_walls:
        layers, total_th = _extract_layers(w, thermal_db)
        u = _u_value_from_layers(layers)
        walls.append({
            "id": _get_gid(w),
            "name": _get_name(w) or "Wall",
            "orientation": "Unknown",
            "area_m2": _extract_area_m2(w),
            "layers": layers,
            "layer_count": len(layers),
            "total_thickness_mm": float(total_th) if total_th > 0 else 0.0,
            "u_value": round(float(u), 4) if u is not None else None,
        })

    # Roofs
    try:
        ifc_roofs = ifc.by_type("IfcRoof") or []
    except Exception:
        ifc_roofs = []

    for r in ifc_roofs:
        layers, total_th = _extract_layers(r, thermal_db)
        u = _u_value_from_layers(layers)
        roofs.append({
            "id": _get_gid(r),
            "name": _get_name(r) or "Roof",
            "area_m2": _extract_area_m2(r),
            "layers": layers,
            "layer_count": len(layers),
            "total_thickness_mm": float(total_th) if total_th > 0 else 0.0,
            "u_value": round(float(u), 4) if u is not None else None,
        })

    # Windows
    try:
        ifc_windows = ifc.by_type("IfcWindow") or []
    except Exception:
        ifc_windows = []

    for win in ifc_windows:
        u = _safe_float(_get_pset_value(win, "Pset_WindowCommon", "ThermalTransmittance"), None)
        shgc = _safe_float(_get_pset_value(win, "Pset_WindowCommon", "SolarHeatGainCoefficient"), None)
        windows.append({
            "id": _get_gid(win),
            "name": _get_name(win) or "Window",
            "orientation": "Unknown",
            "area_m2": _extract_area_m2(win),
            "u_value": u,
            "shgc": shgc,
            "width_m": None,
            "height_m": None,
        })

    # Summary
    total_wall_area = sum(w.get("area_m2", 0.0) or 0.0 for w in walls)
    total_win_area = sum(w.get("area_m2", 0.0) or 0.0 for w in windows)
    overall_wwr = (total_win_area / total_wall_area * 100.0) if total_wall_area > 0 else 0.0

    summary = {
        "total_external_walls": len(walls),
        "total_windows": len(windows),
        "total_roofs": len(roofs),
        "total_wall_area_m2": float(total_wall_area),
        "overall_wwr_pct": float(round(overall_wwr, 2)),
    }

    return {
        "ifc_schema": schema,
        "summary": summary,
        "walls": walls,
        "windows": windows,
        "roofs": roofs,
    }
