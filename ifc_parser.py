"""
ifc_parser.py - Fixed version with None-safe handling
"""

import ifcopenshell
import ifcopenshell.util.element as element_util
import numpy as np
import pandas as pd
import math
import os

RSI = 0.13
RSO = 0.04


def load_thermal_database(csv_path: str) -> dict:
    df = pd.read_csv(csv_path)
    db = {}
    for _, row in df.iterrows():
        db[row["material_name"].lower().strip()] = {
            "lambda": float(row["lambda_value"]),
            "description": row["description"],
            "category": row["category"]
        }
    return db


def safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def fuzzy_match_material(name: str, db: dict) -> tuple:
    if not name:
        return 0.50, "Default", "low"
    name_lower = name.lower().strip()
    if name_lower in db:
        return db[name_lower]["lambda"], name, "high"
    for key, val in db.items():
        if key in name_lower or name_lower in key:
            return val["lambda"], key, "medium"
    keywords = {
        "concrete": 0.51, "brick": 0.77, "eps": 0.038, "xps": 0.034,
        "wool": 0.038, "plaster": 0.25, "timber": 0.13, "wood": 0.13,
        "glass": 1.00, "steel": 50.0, "aluminium": 160.0, "aluminum": 160.0,
        "insul": 0.038, "pir": 0.022, "pur": 0.025, "foam": 0.025,
        "stone": 1.80, "tile": 1.00, "screed": 0.41, "render": 0.72,
        "gypsum": 0.25, "air": 0.18, "cavity": 0.18, "masonry": 0.77,
        "block": 0.51, "membrane": 0.17, "sand": 1.50, "mortar": 0.88,
        "metal": 50.0, "fibre": 0.038, "fiber": 0.038, "rockwool": 0.038,
        "cellulose": 0.040, "panel": 0.038, "board": 0.13
    }
    for kw, lam in keywords.items():
        if kw in name_lower:
            return lam, f"~{kw}", "medium"
    return 0.50, "Unknown", "low"


def calculate_u_value(layers: list):
    r_total = RSI + RSO
    valid = 0
    for layer in layers:
        thickness = safe_float(layer.get("thickness_m"), 0.0)
        lam = safe_float(layer.get("lambda"), 0.50)
        if lam > 0 and thickness > 0:
            r_total += thickness / lam
            valid += 1
    if valid > 0 and r_total > 0:
        return round(1 / r_total, 4)
    return None


def get_element_orientation(ifc_element) -> str:
    try:
        placement = ifc_element.ObjectPlacement
        if not placement:
            return "Unknown"
        loc = placement.RelativePlacement
        if not loc:
            return "Unknown"
        ref_dir = loc.RefDirection
        if ref_dir and hasattr(ref_dir, "DirectionRatios"):
            ratios = ref_dir.DirectionRatios
            if len(ratios) >= 2:
                dx = safe_float(ratios[0], 1.0)
                dy = safe_float(ratios[1], 0.0)
                nx, ny = -dy, dx
                angle = math.degrees(math.atan2(ny, nx)) % 360
                if 45 <= angle < 135:
                    return "North"
                elif 135 <= angle < 225:
                    return "West"
                elif 225 <= angle < 315:
                    return "South"
                else:
                    return "East"
    except Exception:
        pass
    return "Unknown"


def is_external(ifc_element) -> bool:
    try:
        psets = element_util.get_psets(ifc_element)
        found_prop = False
        for pset_name, pset_data in psets.items():
            if not isinstance(pset_data, dict):
                continue
            for key, val in pset_data.items():
                k = key.lower()
                if "external" in k or "isexternal" in k:
                    found_prop = True
                    if val is True or str(val).lower() in ("true", "1", "yes"):
                        return True
        if not found_prop:
            return True  # No IsExternal prop found — include all walls
    except Exception:
        pass
    return True


def get_material_layers(ifc_element, ifc_file) -> list:
    layers = []
    try:
        associations = ifc_element.HasAssociations
        for assoc in associations:
            if not assoc.is_a("IfcRelAssociatesMaterial"):
                continue
            material = assoc.RelatingMaterial
            if material is None:
                continue

            if material.is_a("IfcMaterialLayerSetUsage"):
                layer_set = material.ForLayerSet
                if layer_set and hasattr(layer_set, "MaterialLayers"):
                    for layer in layer_set.MaterialLayers:
                        try:
                            mat_name = layer.Material.Name if layer.Material else "Unknown"
                            thickness_mm = safe_float(layer.LayerThickness, 0.0)
                            layers.append({
                                "material_name": mat_name,
                                "thickness_mm": thickness_mm,
                                "thickness_m": thickness_mm / 1000.0
                            })
                        except Exception:
                            continue

            elif material.is_a("IfcMaterialLayerSet"):
                if hasattr(material, "MaterialLayers"):
                    for layer in material.MaterialLayers:
                        try:
                            mat_name = layer.Material.Name if layer.Material else "Unknown"
                            thickness_mm = safe_float(layer.LayerThickness, 0.0)
                            layers.append({
                                "material_name": mat_name,
                                "thickness_mm": thickness_mm,
                                "thickness_m": thickness_mm / 1000.0
                            })
                        except Exception:
                            continue

            elif material.is_a("IfcMaterialConstituentSet"):
                if hasattr(material, "MaterialConstituents") and material.MaterialConstituents:
                    for constituent in material.MaterialConstituents:
                        try:
                            mat_name = constituent.Material.Name if constituent.Material else "Unknown"
                            fraction = safe_float(getattr(constituent, "Fraction", None), 0.0)
                            est_mm = fraction * 200.0 if fraction > 0 else 100.0
                            layers.append({
                                "material_name": mat_name,
                                "thickness_mm": est_mm,
                                "thickness_m": est_mm / 1000.0
                            })
                        except Exception:
                            continue

            elif material.is_a("IfcMaterialList"):
                if hasattr(material, "Materials"):
                    for mat in material.Materials:
                        try:
                            mat_name = mat.Name if mat else "Unknown"
                            layers.append({
                                "material_name": mat_name,
                                "thickness_mm": 100.0,
                                "thickness_m": 0.1
                            })
                        except Exception:
                            continue

            elif material.is_a("IfcMaterial"):
                layers.append({
                    "material_name": material.Name or "Unknown",
                    "thickness_mm": 200.0,
                    "thickness_m": 0.2
                })

    except Exception:
        pass
    return layers


def get_wall_area(ifc_element) -> float:
    try:
        psets = element_util.get_psets(ifc_element)
        for pset_name, pset_data in psets.items():
            if not isinstance(pset_data, dict):
                continue
            for key, val in pset_data.items():
                k = key.lower()
                if any(x in k for x in ["netside", "netsurface", "grossside", "grosssurface"]):
                    fval = safe_float(val, -1)
                    if fval > 0:
                        return fval
    except Exception:
        pass
    return 0.0


def get_window_properties(ifc_window, psets: dict) -> dict:
    u_value = None
    shgc = None
    width = None
    height = None
    try:
        for pset_name, pset_data in psets.items():
            if not isinstance(pset_data, dict):
                continue
            for key, val in pset_data.items():
                k = key.lower()
                if any(x in k for x in ["thermalresistance", "u-value", "uvalue", "uthermal", "thermaltransmittance"]):
                    fval = safe_float(val, -1)
                    if fval > 0:
                        u_value = fval
                if any(x in k for x in ["shgc", "solarheat", "solarfactor", "g-value", "gvalue"]):
                    fval = safe_float(val, -1)
                    if 0 < fval <= 1:
                        shgc = fval
                if "overallwidth" in k or k == "width":
                    fval = safe_float(val, -1)
                    if fval > 0:
                        width = fval / 1000.0
                if "overallheight" in k or k == "height":
                    fval = safe_float(val, -1)
                    if fval > 0:
                        height = fval / 1000.0
    except Exception:
        pass
    try:
        if width is None:
            w = safe_float(getattr(ifc_window, "OverallWidth", None), -1)
            if w > 0:
                width = w / 1000.0
        if height is None:
            h = safe_float(getattr(ifc_window, "OverallHeight", None), -1)
            if h > 0:
                height = h / 1000.0
    except Exception:
        pass
    area = (width * height) if (width and height) else None
    return {"u_value": u_value, "shgc": shgc, "width_m": width, "height_m": height, "area_m2": area}


def parse_ifc(ifc_path: str, thermal_db: dict) -> dict:
    ifc = ifcopenshell.open(ifc_path)
    walls_data = []
    windows_data = []
    roof_data = []

    # ── WALLS ──
    wall_entities = []
    for etype in ["IfcWall", "IfcWallStandardCase"]:
        try:
            wall_entities.extend(ifc.by_type(etype))
        except Exception:
            pass

    seen_ids = set()
    for wall in wall_entities:
        try:
            gid = wall.GlobalId
            if gid in seen_ids:
                continue
            seen_ids.add(gid)

            if not is_external(wall):
                continue

            type_name = "Unnamed Wall"
            try:
                wt = wall.IsTypedBy
                if wt:
                    type_name = wt[0].RelatingType.Name or type_name
                elif wall.Name:
                    type_name = wall.Name
            except Exception:
                pass

            layers = get_material_layers(wall, ifc)
            orientation = get_element_orientation(wall)
            area = get_wall_area(wall)

            enriched = []
            for layer in layers:
                lam, matched, conf = fuzzy_match_material(layer.get("material_name", ""), thermal_db)
                t_m = safe_float(layer.get("thickness_m"), 0.0)
                t_mm = safe_float(layer.get("thickness_mm"), 0.0)
                r = round(t_m / lam, 4) if (lam > 0 and t_m > 0) else 0.0
                enriched.append({**layer, "thickness_mm": t_mm, "thickness_m": t_m,
                                  "lambda": lam, "matched_material": matched,
                                  "confidence": conf, "r_value": r})

            u_value = calculate_u_value(enriched)
            total_t = sum(safe_float(l.get("thickness_mm"), 0) for l in enriched)

            walls_data.append({
                "id": wall.GlobalId, "name": type_name,
                "orientation": orientation, "area_m2": safe_float(area, 0.0),
                "layers": enriched, "u_value": u_value,
                "total_thickness_mm": total_t, "layer_count": len(enriched)
            })
        except Exception:
            continue

    # ── WINDOWS ──
    try:
        for win in ifc.by_type("IfcWindow"):
            try:
                psets = element_util.get_psets(win)
                props = get_window_properties(win, psets)
                windows_data.append({
                    "id": win.GlobalId,
                    "name": getattr(win, "Name", None) or "Window",
                    "orientation": get_element_orientation(win),
                    **props
                })
            except Exception:
                continue
    except Exception:
        pass

    # ── ROOFS ──
    for etype in ["IfcRoof", "IfcSlab"]:
        try:
            for roof in ifc.by_type(etype):
                try:
                    pred_type = getattr(roof, "PredefinedType", None)
                    if not (roof.is_a("IfcRoof") or (pred_type and "roof" in str(pred_type).lower())):
                        continue
                    layers = get_material_layers(roof, ifc)
                    enriched = []
                    for layer in layers:
                        lam, matched, conf = fuzzy_match_material(layer.get("material_name", ""), thermal_db)
                        t_m = safe_float(layer.get("thickness_m"), 0.0)
                        t_mm = safe_float(layer.get("thickness_mm"), 0.0)
                        r = round(t_m / lam, 4) if (lam > 0 and t_m > 0) else 0.0
                        enriched.append({**layer, "thickness_mm": t_mm, "thickness_m": t_m,
                                          "lambda": lam, "matched_material": matched,
                                          "confidence": conf, "r_value": r})
                    roof_data.append({
                        "id": roof.GlobalId,
                        "name": getattr(roof, "Name", None) or "Roof Assembly",
                        "layers": enriched, "u_value": calculate_u_value(enriched),
                        "area_m2": safe_float(get_wall_area(roof), 0.0),
                        "layer_count": len(enriched)
                    })
                except Exception:
                    continue
        except Exception:
            pass

    # ── SUMMARY ──
    all_u = [w["u_value"] for w in walls_data if w["u_value"] is not None]
    total_wall_area = sum(w["area_m2"] for w in walls_data)
    total_win_area = sum(safe_float(w.get("area_m2"), 0) for w in windows_data)
    wwr = (total_win_area / total_wall_area * 100) if total_wall_area > 0 else 0

    return {
        "walls": walls_data,
        "windows": windows_data,
        "roofs": roof_data,
        "summary": {
            "total_external_walls": len(walls_data),
            "total_windows": len(windows_data),
            "total_roofs": len(roof_data),
            "total_wall_area_m2": round(total_wall_area, 2),
            "total_window_area_m2": round(total_win_area, 2),
            "overall_wwr_pct": round(wwr, 1),
            "avg_wall_u_value": round(sum(all_u) / len(all_u), 3) if all_u else None,
            "unique_wall_types": len(set(w["name"] for w in walls_data))
        },
        "ifc_schema": ifc.schema
    }
