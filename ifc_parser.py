# ifc_parser.py
# ============================================================
# IFC → Thermal Envelope Parser (Research Version)
# - Robust: never silently returns None
# - Always returns a dict with keys: ifc_schema, summary, walls, windows, roofs
# - If something fails, raises a RuntimeError with details
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
    raise ImportError(
        "ifcopenshell is required. Install it in your environment / requirements.txt.\n"
        f"Import error: {e}"
    )


# ----------------------------
# Constants (ISO 6946)
# ----------------------------
R_SI = 0.13  # internal surface resistance (m²K/W)
R_SO = 0.04  # external surface resistance (m²K/W)
DEFAULT_LAMBDA = 0.50  # W/mK fallback if material not found


# ----------------------------
# Thermal DB loader
# ----------------------------
def load_thermal_database(csv_path: str) -> pd.DataFrame:
    """
    Expected minimal columns (case-insensitive):
      - material (or material_name / name)
      - lambda   (or conductivity / k)
    Optional:
      - cost_index (any scale)
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Thermal database CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)

    # normalize columns
    cols = {c.lower().strip(): c for c in df.columns}
    name_col = None
    lam_col = None

    for candidate in ["material", "material_name", "name"]:
        if candidate in cols:
            name_col = cols[candidate]
            break

    for candidate in [
    "lambda", "lambda_value",
    "conductivity", "k", "k_value",
    "thermal_conductivity", "thermal_conductivity_wmk", "thermal_conductivity_w_mk"
]:
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

    # drop rows without valid lambda
    out = out[out["__lambda__"].notna()].reset_index(drop=True)
    return out


# ----------------------------
# Main parser
# ----------------------------
def parse_ifc(ifc_path: str, thermal_db: pd.DataFrame) -> Dict[str, Any]:
    """
    Returns:
      {
        "ifc_schema": "IFC4",
        "summary": {...},
        "walls":   [ ... ],
        "windows": [ ... ],
        "roofs":   [ ... ],
      }
    """
    try:
        if not os.path.exists(ifc_path):
            raise FileNotFoundError(f"IFC file not found: {ifc_path}")

        model = ifcopenshell.open(ifc_path)
        if model is None:
            raise RuntimeError("ifcopenshell.open() returned None (invalid IFC or missing ifcopenshell build).")

        schema = getattr(model, "schema", None) or getattr(model, "schema_identifier", None) or "UNKNOWN"

        walls = _extract_walls(model, thermal_db)
        roofs = _extract_roofs(model, thermal_db)
        windows = _extract_windows(model)

        # --- summary numbers ---
        total_wall_area = sum(float(w.get("area_m2") or 0) for w in walls)
        total_win_area = sum(float(w.get("area_m2") or 0) for w in windows)

        overall_wwr = (total_win_area / total_wall_area * 100.0) if total_wall_area > 0 else 0.0

        summary = {
            "total_external_walls": int(len(walls)),
            "total_windows": int(len(windows)),
            "total_roofs": int(len(roofs)),
            "total_wall_area_m2": float(total_wall_area),
            "total_window_area_m2": float(total_win_area),
            "overall_wwr_pct": float(round(overall_wwr, 3)),
            # optional convenience
            "notes": "Areas are derived from IFC quantities when available; fallback may be 0 if not present."
        }

        # Ensure the app-required keys exist
        out = {
            "ifc_schema": schema,
            "summary": summary,
            "walls": walls,
            "windows": windows,
            "roofs": roofs,
        }

        _hard_guard_return(out)
        return out

    except Exception as e:
        # IMPORTANT: never return None silently
        raise RuntimeError(f"parse_ifc failed: {e}")


# ============================================================
# Extraction helpers
# ============================================================

def _extract_walls(model, thermal_db: pd.DataFrame) -> List[Dict[str, Any]]:
    walls_out: List[Dict[str, Any]] = []

    # IFC walls can be IfcWall / IfcWallStandardCase
    walls = []
    for t in ["IfcWall", "IfcWallStandardCase"]:
        try:
            walls += model.by_type(t) or []
        except Exception:
            pass

    for el in walls:
        try:
            gid = getattr(el, "GlobalId", None) or ""
            name = (getattr(el, "Name", None) or "Wall").strip()

            area = _get_area_m2(el, prefer=("NetSideArea", "GrossSideArea", "Area"))
            orientation = _get_orientation_label(el)

            layers, total_thk_mm, conf_counts = _get_layers_with_lambda(el, thermal_db)
            u_value = _calc_u_value(layers)

            walls_out.append({
                "id": gid,
                "name": name,
                "orientation": orientation,
                "area_m2": float(area) if area is not None else 0.0,
                "u_value": float(round(u_value, 4)) if u_value is not None else None,
                "total_thickness_mm": float(round(total_thk_mm, 1)) if total_thk_mm is not None else None,
                "layer_count": int(len(layers)),
                "layers": layers,
                # for transparency reporting
                "confidence_counts": conf_counts,
            })
        except Exception as e:
            # keep robust: skip element but do not crash whole parsing
            # (still do not return None)
            continue

    return walls_out


def _extract_roofs(model, thermal_db: pd.DataFrame) -> List[Dict[str, Any]]:
    roofs_out: List[Dict[str, Any]] = []

    roofs = []
    for t in ["IfcRoof", "IfcSlab"]:
        try:
            roofs += model.by_type(t) or []
        except Exception:
            pass

    # IfcSlab can include ROOF slabs. We filter if possible.
    for el in roofs:
        try:
            if el.is_a("IfcSlab"):
                # Try to detect roof slabs
                # PredefinedType can be ROOF (depends on export)
                pdt = getattr(el, "PredefinedType", None)
                if pdt and str(pdt).upper() not in ["ROOF", "ROOFSLAB", "ROOF_SLAB"]:
                    # many slabs are floors; skip unless clearly roof
                    continue

            gid = getattr(el, "GlobalId", None) or ""
            name = (getattr(el, "Name", None) or el.is_a()).strip()

            area = _get_area_m2(el, prefer=("NetArea", "GrossArea", "Area"))
            layers, total_thk_mm, conf_counts = _get_layers_with_lambda(el, thermal_db)
            u_value = _calc_u_value(layers)

            roofs_out.append({
                "id": gid,
                "name": name,
                "area_m2": float(area) if area is not None else 0.0,
                "u_value": float(round(u_value, 4)) if u_value is not None else None,
                "total_thickness_mm": float(round(total_thk_mm, 1)) if total_thk_mm is not None else None,
                "layer_count": int(len(layers)),
                "layers": layers,
                "confidence_counts": conf_counts,
            })
        except Exception:
            continue

    return roofs_out


def _extract_windows(model) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    wins = []
    for t in ["IfcWindow"]:
        try:
            wins += model.by_type(t) or []
        except Exception:
            pass

    for el in wins:
        try:
            gid = getattr(el, "GlobalId", None) or ""
            name = (getattr(el, "Name", None) or "Window").strip()

            # Try to get psets
            psets = _safe_get_psets(el)

            u_value = _pset_get_float(psets, "Pset_WindowCommon", "ThermalTransmittance")
            shgc = _pset_get_float(psets, "Pset_WindowCommon", "SolarHeatGainCoefficient")

            # size / area (IFC quantities preferred)
            area = _get_area_m2(el, prefer=("Area", "GrossArea", "NetArea"))
            width = _pset_get_float(psets, "Pset_WindowCommon", "OverallWidth")
            height = _pset_get_float(psets, "Pset_WindowCommon", "OverallHeight")

            # Orientation: best-effort (host wall if we can find it; else try own placement)
            orientation = _get_window_orientation_label(el) or _get_orientation_label(el)

            out.append({
                "id": gid,
                "name": name,
                "orientation": orientation,
                "width_m": float(width) if width is not None else None,
                "height_m": float(height) if height is not None else None,
                "area_m2": float(area) if area is not None else 0.0,
                "u_value": float(u_value) if u_value is not None else None,
                "shgc": float(shgc) if shgc is not None else None,
            })
        except Exception:
            continue

    return out


# ============================================================
# Material / layers / U-value
# ============================================================

def _get_layers_with_lambda(el, thermal_db: pd.DataFrame) -> Tuple[List[Dict[str, Any]], float, Dict[str, int]]:
    """
    Returns (layers, total_thickness_mm, confidence_counts)
    Each layer: material_name, thickness_mm, matched_material, lambda, confidence, r_value
    """
    layers_out: List[Dict[str, Any]] = []
    total_thk_mm = 0.0

    conf_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "TOTAL": 0}

    mats = _safe_get_material(el)

    # If material info is missing in IFC, return empty layers
    if mats is None:
        return [], 0.0, conf_counts

    # Try to extract IfcMaterialLayerSetUsage → IfcMaterialLayerSet → MaterialLayers
    raw_layers = _flatten_layers(mats)

    for lay in raw_layers:
        mat_name = (lay.get("material_name") or "Unknown").strip()
        thk_mm = float(lay.get("thickness_mm") or 0.0)

        matched, lam, conf = _match_lambda(mat_name, thermal_db)

        # R = d/lambda
        r_val = None
        if lam and lam > 0 and thk_mm > 0:
            r_val = (thk_mm / 1000.0) / lam

        layers_out.append({
            "material_name": mat_name,
            "thickness_mm": thk_mm if thk_mm > 0 else None,
            "matched_material": matched,
            "lambda": float(round(lam, 4)) if lam is not None else None,
            "confidence": conf,
            "r_value": float(round(r_val, 6)) if r_val is not None else None,
        })

        total_thk_mm += thk_mm
        conf_counts["TOTAL"] += 1
        conf_counts[conf] = conf_counts.get(conf, 0) + 1

    return layers_out, total_thk_mm, conf_counts


def _calc_u_value(layers: List[Dict[str, Any]]) -> Optional[float]:
    """
    ISO 6946: U = 1 / (Rsi + Σ(d/lambda) + Rso)
    If no valid layer R-values exist, return None.
    """
    r_sum = 0.0
    valid = 0
    for l in layers:
        rv = l.get("r_value")
        if isinstance(rv, (int, float)) and rv > 0:
            r_sum += float(rv)
            valid += 1

    if valid == 0:
        return None

    r_total = R_SI + r_sum + R_SO
    if r_total <= 0:
        return None
    return 1.0 / r_total


# ============================================================
# Orientation / quantities
# ============================================================

def _get_area_m2(el, prefer: Tuple[str, ...] = ("Area",)) -> Optional[float]:
    """
    Best-effort area extraction from:
      - IFC BaseQuantities (Qto_*BaseQuantities)
      - quantity takeoff psets
    Returns None if not found.
    """
    try:
        psets = _safe_get_psets(el)

        # First: any Qto sets (common in IFC exports)
        # Search all psets keys for "Qto_" and match prefer fields
        for pset_name, props in (psets or {}).items():
            if not isinstance(props, dict):
                continue
            if not str(pset_name).startswith("Qto_"):
                continue
            for field in prefer:
                v = props.get(field)
                fv = _to_float(v)
                if fv is not None and fv > 0:
                    return float(fv)

        # Second: some exports store quantities elsewhere
        for pset_name, props in (psets or {}).items():
            if not isinstance(props, dict):
                continue
            for field in prefer:
                v = props.get(field)
                fv = _to_float(v)
                if fv is not None and fv > 0:
                    return float(fv)

    except Exception:
        pass

    return None


def _get_orientation_label(el) -> str:
    """
    Best-effort orientation from ObjectPlacement.
    If cannot compute, returns "Unknown".
    """
    try:
        angle = _get_azimuth_deg(el)
        if angle is None:
            return "Unknown"
        # Standard quadrant mapping:
        # 0 = East, 90 = North, 180 = West, 270 = South  (depending on coordinate convention)
        # Many BIM exports use X=east, Y=north. We'll map:
        # az=0 → East, 90 → North, 180 → West, 270 → South
        a = angle % 360.0
        if 45 <= a < 135:
            return "North"
        if 135 <= a < 225:
            return "West"
        if 225 <= a < 315:
            return "South"
        return "East"
    except Exception:
        return "Unknown"


def _get_window_orientation_label(win_el) -> Optional[str]:
    """
    Try to find host wall orientation via fills/void relationships.
    If not possible, return None.
    """
    try:
        # Some IFCs: IfcRelFillsElement → RelatingOpeningElement
        # Opening element often has IfcRelVoidsElement linking to host wall.
        for rel in getattr(win_el, "FillsVoids", []) or []:
            try:
                opening = getattr(rel, "RelatingOpeningElement", None)
                if not opening:
                    continue
                for vr in getattr(opening, "VoidsElements", []) or []:
                    host = getattr(vr, "RelatingBuildingElement", None)
                    if host and host.is_a() in ["IfcWall", "IfcWallStandardCase"]:
                        return _get_orientation_label(host)
            except Exception:
                continue
    except Exception:
        pass
    return None


def _get_azimuth_deg(el) -> Optional[float]:
    """
    Attempts to compute a 2D azimuth angle from placement RefDirection.
    Returns degrees in [0,360), where 0 means +X direction.
    """
    try:
        pl = getattr(el, "ObjectPlacement", None)
        if not pl:
            return None

        rel = getattr(pl, "RelativePlacement", None)
        if not rel:
            # sometimes there is PlacementRelTo chain
            rel = getattr(getattr(pl, "PlacementRelTo", None), "RelativePlacement", None)
            if not rel:
                return None

        ref_dir = getattr(rel, "RefDirection", None)
        if not ref_dir:
            return None

        d = getattr(ref_dir, "DirectionRatios", None)
        if not d or len(d) < 2:
            return None

        x, y = float(d[0]), float(d[1])
        if abs(x) < 1e-9 and abs(y) < 1e-9:
            return None

        import math
        ang = math.degrees(math.atan2(y, x))
        if ang < 0:
            ang += 360.0
        return ang

    except Exception:
        return None


# ============================================================
# IFC material traversal
# ============================================================

def _safe_get_material(el):
    try:
        return ifc_el.get_material(el)
    except Exception:
        return None


def _flatten_layers(material_obj) -> List[Dict[str, Any]]:
    """
    Converts IFC material structure into a simple list of layers.
    Supports:
      - IfcMaterialLayerSetUsage
      - IfcMaterialLayerSet
      - IfcMaterialLayer
      - IfcMaterial (single)
    """
    layers = []

    try:
        # IfcMaterialLayerSetUsage
        if hasattr(material_obj, "ForLayerSet"):
            mls = material_obj.ForLayerSet
            return _flatten_layers(mls)

        # IfcMaterialLayerSet
        if hasattr(material_obj, "MaterialLayers") and material_obj.MaterialLayers:
            for ml in material_obj.MaterialLayers:
                try:
                    mat = getattr(ml, "Material", None)
                    mat_name = getattr(mat, "Name", None) if mat else None
                    thk = getattr(ml, "LayerThickness", None)
                    layers.append({
                        "material_name": str(mat_name or "Unknown"),
                        "thickness_mm": float(thk) * 1000.0 if thk is not None else 0.0,  # meters→mm (IFC typically meters)
                    })
                except Exception:
                    continue
            return layers

        # IfcMaterialLayer
        if material_obj.is_a("IfcMaterialLayer"):
            mat = getattr(material_obj, "Material", None)
            mat_name = getattr(mat, "Name", None) if mat else None
            thk = getattr(material_obj, "LayerThickness", None)
            layers.append({
                "material_name": str(mat_name or "Unknown"),
                "thickness_mm": float(thk) * 1000.0 if thk is not None else 0.0,
            })
            return layers

        # IfcMaterial (single material, no thickness)
        if material_obj.is_a("IfcMaterial"):
            mat_name = getattr(material_obj, "Name", None)
            layers.append({
                "material_name": str(mat_name or "Unknown"),
                "thickness_mm": 0.0,
            })
            return layers

        # Sometimes get_material returns a list/tuple
        if isinstance(material_obj, (list, tuple)):
            for m in material_obj:
                layers += _flatten_layers(m)
            return layers

    except Exception:
        pass

    return layers


# ============================================================
# DB matching (material → lambda)
# ============================================================

def _norm_key(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s\-\_]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _match_lambda(mat_name: str, thermal_db: pd.DataFrame) -> Tuple[str, float, str]:
    """
    Returns (matched_material_name, lambda_value, confidence)
    Confidence:
      HIGH   - exact normalized match
      MEDIUM - keyword overlap match
      LOW    - default lambda used
    """
    key = _norm_key(mat_name)
    if not key:
        return ("—", DEFAULT_LAMBDA, "LOW")

    # HIGH: exact normalized match
    exact = thermal_db[thermal_db["__mat_key__"] == key]
    if len(exact) > 0:
        row = exact.iloc[0]
        return (str(row["__mat_name__"]), float(row["__lambda__"]), "HIGH")

    # MEDIUM: keyword overlap (simple robust matcher)
    tokens = set(key.split())
    if tokens:
        best = None
        best_score = 0.0
        for i in range(len(thermal_db)):
            k2 = thermal_db.at[i, "__mat_key__"]
            t2 = set(str(k2).split())
            if not t2:
                continue
            inter = len(tokens & t2)
            union = len(tokens | t2)
            score = inter / union if union else 0.0
            if score > best_score:
                best_score = score
                best = i
        if best is not None and best_score >= 0.22:
            row = thermal_db.iloc[best]
            return (str(row["__mat_name__"]), float(row["__lambda__"]), "MEDIUM")

    # LOW fallback
    return ("—", DEFAULT_LAMBDA, "LOW")


# ============================================================
# Pset helpers
# ============================================================

def _safe_get_psets(el) -> Dict[str, Any]:
    try:
        return ifc_el.get_psets(el) or {}
    except Exception:
        return {}


def _pset_get_float(psets: Dict[str, Any], pset_name: str, prop_name: str) -> Optional[float]:
    try:
        p = psets.get(pset_name, {})
        if not isinstance(p, dict):
            return None
        return _to_float(p.get(prop_name))
    except Exception:
        return None


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        # Sometimes IFC gives objects; str() can contain numbers
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v)
        # extract first numeric
        m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
        return float(m.group(0)) if m else None
    except Exception:
        return None


# ============================================================
# Safety guard
# ============================================================

def _hard_guard_return(d: Dict[str, Any]) -> None:
    """
    Make sure we ALWAYS return what app expects.
    """
    if not isinstance(d, dict):
        raise RuntimeError(f"Parser output must be dict, got {type(d)}")

    required = ["summary", "walls", "windows", "roofs", "ifc_schema"]
    missing = [k for k in required if k not in d]
    if missing:
        raise RuntimeError(f"Parser output missing keys: {missing}")

    if not isinstance(d["summary"], dict):
        raise RuntimeError("summary must be a dict")
    for k in ["walls", "windows", "roofs"]:
        if not isinstance(d[k], list):
            raise RuntimeError(f"{k} must be a list")


# ============================================================
# End of file
# ============================================================
