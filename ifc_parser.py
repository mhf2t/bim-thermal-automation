# ifc_parser.py
# ============================================================
# IFC Thermal Parser — robust + never returns None
# - Extracts walls, roofs, windows
# - Computes U-values using ISO 6946 from material layers
# - Uses thermal database CSV for lambda (conductivity)
# ============================================================

from __future__ import annotations

import os
import re
import math
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd

try:
    import ifcopenshell
    import ifcopenshell.util.element as ifc_el
except Exception as e:
    raise ImportError("ifcopenshell is required. Add it to requirements and ensure it installs.") from e


# ----------------------------
# Helpers
# ----------------------------
_WS_RE = re.compile(r"\s+")


def _norm_key(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = _WS_RE.sub(" ", s)
    return s


def _safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _mm_to_m(mm: float) -> float:
    return float(mm) / 1000.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ----------------------------
# Thermal DB loader
# ----------------------------
def load_thermal_database(csv_path: str) -> pd.DataFrame:
    """
    Expected minimal columns (case-insensitive):
      - material (or material_name / name)
      - lambda   (or conductivity / k / lambda_value)

    Optional:
      - cost_index (any scale)

    Your file has: ['material_name', 'lambda_value', 'description', 'category']
    ✅ This loader supports that.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Thermal database CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)

    cols = {c.lower().strip(): c for c in df.columns}
    name_col = None
    lam_col = None

    for candidate in ["material", "material_name", "name"]:
        if candidate in cols:
            name_col = cols[candidate]
            break

    for candidate in ["lambda", "lambda_value", "conductivity", "k"]:
        if candidate in cols:
            lam_col = cols[candidate]
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

    # optional cost index
    cost_col = None
    for candidate in ["cost_index", "cost", "index"]:
        if candidate in cols:
            cost_col = cols[candidate]
            break
    out["__cost__"] = pd.to_numeric(out[cost_col], errors="coerce") if cost_col else None

    # keep only rows with lambda
    out = out[out["__lambda__"].notna()].reset_index(drop=True)

    if out.empty:
        raise ValueError("Thermal DB loaded, but no valid lambda values were found after cleaning.")

    return out


def _match_lambda(material_name: str, db: pd.DataFrame) -> Tuple[Optional[float], str, str]:
    """
    Returns (lambda, matched_material_name, confidence)
    confidence in {"high","medium","low"}
    """
    key = _norm_key(material_name)
    if not key:
        return None, "—", "low"

    # exact key match
    hit = db[db["__mat_key__"] == key]
    if not hit.empty:
        row = hit.iloc[0]
        return float(row["__lambda__"]), str(row["__mat_name__"]), "high"

    # contains / partial match
    # try: db key contained in material key or vice versa
    # Keep it simple and deterministic (first best length match)
    candidates = []
    for _, r in db.iterrows():
        dk = r["__mat_key__"]
        if not dk:
            continue
        if dk in key or key in dk:
            candidates.append((len(dk), r))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        r = candidates[0][1]
        return float(r["__lambda__"]), str(r["__mat_name__"]), "medium"

    return None, "—", "low"


# ----------------------------
# ISO 6946 calculations
# ----------------------------
def _u_value_from_layers(layers: List[Dict[str, Any]], r_si: float = 0.13, r_so: float = 0.04) -> Tuple[Optional[float], float]:
    """
    layers: list of dicts with thickness_mm and lambda
    Returns (U, R_total)
    """
    r_sum = 0.0
    for layer in layers:
        th_mm = _safe_float(layer.get("thickness_mm"), 0.0) or 0.0
        lam = _safe_float(layer.get("lambda"), None)
        if th_mm <= 0 or lam is None or lam <= 0:
            continue
        r_sum += _mm_to_m(th_mm) / lam

    r_total = r_si + r_sum + r_so
    if r_total <= 0:
        return None, r_total
    u = 1.0 / r_total
    return float(u), float(r_total)


# ----------------------------
# IFC extraction helpers
# ----------------------------
def _get_pset_value(elem, pset_name: str, prop_name: str):
    """
    Safe read property from pset using ifcopenshell.util.element.get_psets
    """
    try:
        psets = ifc_el.get_psets(elem) or {}
        pset = psets.get(pset_name) or {}
        val = pset.get(prop_name)
        return val
    except Exception:
        return None


def _get_global_id(elem) -> str:
    try:
        return str(getattr(elem, "GlobalId", "") or "")
    except Exception:
        return ""


def _get_name(elem) -> str:
    try:
        return str(getattr(elem, "Name", "") or "") or str(getattr(elem, "ObjectType", "") or "")
    except Exception:
        return ""


def _extract_layer_set_from_elem(ifc_file, elem) -> List[Tuple[str, float]]:
    """
    Attempt to extract (material_name, thickness_mm) from:
      - IfcMaterialLayerSetUsage -> ForLayerSet -> MaterialLayers
      - IfcMaterialLayerSet
    If not found, returns [].
    """
    layers_out: List[Tuple[str, float]] = []

    try:
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
                if ls and hasattr(ls, "MaterialLayers"):
                    for ml in ls.MaterialLayers:
                        mname = ""
                        if ml.Material:
                            mname = str(getattr(ml.Material, "Name", "") or "")
                        th = _safe_float(getattr(ml, "LayerThickness", None), 0.0) or 0.0
                        # IFC thickness usually meters; convert to mm if value seems small/large:
                        # Heuristic: if <= 1.0 assume meters; convert to mm
                        th_mm = th * 1000.0 if th <= 1.0 else th
                        layers_out.append((mname, float(th_mm)))
                break

            # IfcMaterialLayerSet (sometimes directly)
            if mat.is_a("IfcMaterialLayerSet"):
                if hasattr(mat, "MaterialLayers"):
                    for ml in mat.MaterialLayers:
                        mname = ""
                        if ml.Material:
                            mname = str(getattr(ml.Material, "Name", "") or "")
                        th = _safe_float(getattr(ml, "LayerThickness", None), 0.0) or 0.0
                        th_mm = th * 1000.0 if th <= 1.0 else th
                        layers_out.append((mname, float(th_mm)))
                break

    except Exception:
        return []

    # remove empties
    layers_out = [(n.strip(), t) for n, t in layers_out if (n or "").strip() and t and t > 0]
    return layers_out


def _extract_area_m2(elem) -> Optional[float]:
    """
    Try to read base quantities if available.
    In Revit IFC exports, wall area may appear under Qto_WallBaseQuantities / NetSideArea or GrossSideArea.
    """
    # common quantity names
    for pset, prop in [
        ("Qto_WallBaseQuantities", "NetSideArea"),
        ("Qto_WallBaseQuantities", "GrossSideArea"),
        ("Qto_RoofBaseQuantities", "NetArea"),
        ("Qto_RoofBaseQuantities", "GrossArea"),
        ("Qto_WindowBaseQuantities", "Area"),
    ]:
        v = _get_pset_value(elem, pset, prop)
        fv = _safe_float(v, None)
        if fv and fv > 0:
            return float(fv)

    return None


def _guess_orientation_from_pset(elem) -> str:
    """
    Many exports don’t include orientation. If you already compute it elsewhere, keep it there.
    Here we only attempt a safe read; else return "Unknown".
    """
    for pset, prop in [
        ("Pset_WallCommon", "Orientation"),
        ("Pset_BuildingElementProxyCommon", "Orientation"),
    ]:
        v = _get_pset_value(elem, pset, prop)
        if isinstance(v, str) and v.strip():
            return v.strip()

    return "Unknown"


# ----------------------------
# Main parse function
# ----------------------------
def parse_ifc(ifc_path: str, thermal_db: pd.DataFrame) -> Dict[str, Any]:
    """
    Returns a dict with keys:
      - ifc_schema
      - summary
      - walls, roofs, windows
    Never returns None. Raises RuntimeError on fatal open/parse issues.
    """
    if not os.path.exists(ifc_path):
        raise RuntimeError(f"IFC file not found: {ifc_path}")

    try:
        ifc = ifcopenshell.open(ifc_path)
    except Exception as e:
        raise RuntimeError(f"Could not open IFC: {e}") from e

    try:
        schema = str(getattr(ifc, "schema", None) or "Unknown")
    except Exception:
        schema = "Unknown"

    walls: List[Dict[str, Any]] = []
    roofs: List[Dict[str, Any]] = []
    windows: List[Dict[str, Any]] = []

    # --------
    # Walls
    # --------
    try:
        ifc_walls = (ifc.by_type("IfcWall") or []) + (ifc.by_type("IfcWallStandardCase") or [])
    except Exception:
        ifc_walls = []

    for w in ifc_walls:
        gid = _get_global_id(w)
        name = _get_name(w) or f"Wall_{gid[:8] if gid else 'Unknown'}"

        layer_pairs = _extract_layer_set_from_elem(ifc, w)
        layers = []
        total_th = 0.0

        for mat_name, th_mm in layer_pairs:
            lam, matched, conf = _match_lambda(mat_name, thermal_db)
            if lam is None:
                # fallback lambda (your earlier logic used 0.50) — keep consistent
                lam = 0.50
                conf = "low"
                matched = "DEFAULT(0.50)"

            r_val = (_mm_to_m(th_mm) / lam) if lam > 0 and th_mm > 0 else 0.0
            layers.append({
                "material_name": mat_name,
                "matched_material": matched,
                "confidence": conf,
                "thickness_mm": float(th_mm),
                "lambda": float(lam),
                "r_value": float(r_val),
            })
            total_th += float(th_mm)

        u, rtot = _u_value_from_layers(layers)

        area = _extract_area_m2(w)
        orientation = _guess_orientation_from_pset(w)

        walls.append({
            "id": gid,
            "name": name,
            "orientation": orientation,
            "area_m2": float(area) if area is not None else 0.0,
            "layers": layers,
            "layer_count": len(layers),
            "total_thickness_mm": float(total_th) if total_th > 0 else 0.0,
            "u_value": float(round(u, 4)) if u is not None else None,
        })

    # --------
    # Roofs
    # --------
    try:
        ifc_roofs = ifc.by_type("IfcRoof") or []
    except Exception:
        ifc_roofs = []

    for r in ifc_roofs:
        gid = _get_global_id(r)
        name = _get_name(r) or f"Roof_{gid[:8] if gid else 'Unknown'}"

        layer_pairs = _extract_layer_set_from_elem(ifc, r)
        layers = []
        total_th = 0.0

        for mat_name, th_mm in layer_pairs:
            lam, matched, conf = _match_lambda(mat_name, thermal_db)
            if lam is None:
                lam = 0.50
                conf = "low"
                matched = "DEFAULT(0.50)"

            r_val = (_mm_to_m(th_mm) / lam) if lam > 0 and th_mm > 0 else 0.0
            layers.append({
                "material_name": mat_name,
                "matched_material": matched,
                "confidence": conf,
                "thickness_mm": float(th_mm),
                "lambda": float(lam),
                "r_value": float(r_val),
            })
            total_th += float(th_mm)

        u, rtot = _u_value_from_layers(layers)

        area = _extract_area_m2(r)

        roofs.append({
            "id": gid,
            "name": name,
            "area_m2": float(area) if area is not None else 0.0,
            "layers": layers,
            "layer_count": len(layers),
            "total_thickness_mm": float(total_th) if total_th > 0 else 0.0,
            "u_value": float(round(u, 4)) if u is not None else None,
        })

    # --------
    # Windows
    # --------
    try:
        ifc_windows = ifc.by_type("IfcWindow") or []
    except Exception:
        ifc_windows = []

    for win in ifc_windows:
        gid = _get_global_id(win)
        name = _get_name(win) or f"Window_{gid[:8] if gid else 'Unknown'}"

        # Window thermal properties commonly appear in Pset_WindowCommon
        u = _get_pset_value(win, "Pset_WindowCommon", "ThermalTransmittance")
        shgc = _get_pset_value(win, "Pset_WindowCommon", "SolarHeatGainCoefficient")

        area = _extract_area_m2(win)
        orientation = _guess_orientation_from_pset(win)

        windows.append({
            "id": gid,
            "name": name,
            "orientation": orientation,
            "area_m2": float(area) if area is not None else 0.0,
            "u_value": _safe_float(u, None),
            "shgc": _safe_float(shgc, None),
            "width_m": None,
            "height_m": None,
        })

    # --------
    # Summary
    # --------
    total_wall_area = sum(w.get("area_m2", 0.0) or 0.0 for w in walls)
    total_win_area = sum(w.get("area_m2", 0.0) or 0.0 for w in windows)
    overall_wwr = (total_win_area / total_wall_area * 100.0) if total_wall_area > 0 else 0.0

    summary = {
        "total_external_walls": int(len(walls)),
        "total_windows": int(len(windows)),
        "total_roofs": int(len(roofs)),
        "total_wall_area_m2": float(total_wall_area),
        "overall_wwr_pct": float(round(overall_wwr, 2)),
    }

    # IMPORTANT: always return dict (never None)
    return {
        "ifc_schema": schema,
        "summary": summary,
        "walls": walls,
        "windows": windows,
        "roofs": roofs,
    }
