"""
compliance.py
=============
Thermal compliance checking against international energy codes.
Supports MS1525, ASHRAE 90.1 (multiple climate zones), Green Star, UK Part L.

All thresholds are prescriptive U-value paths from official published standards.
"""

import math

# ─────────────────────────────────────────────────
# COMPLIANCE THRESHOLDS (U-value in W/m²K)
# Source: Published energy codes — prescriptive envelope path
# ─────────────────────────────────────────────────
CODES = {
    "MS1525:2019 (Malaysia)": {
        "wall_u_max": 0.40,
        "roof_u_max": 0.30,
        "window_u_max": 3.00,
        "wwr_max_pct": 40.0,
        "shgc_max": 0.25,
        "climate": "Tropical",
        "region": "Malaysia",
        "source": "MS1525:2019, DOSH Malaysia"
    },
    "ASHRAE 90.1-2019 (Climate Zone 1A)": {
        "wall_u_max": 0.701,
        "roof_u_max": 0.273,
        "window_u_max": 3.692,
        "wwr_max_pct": 40.0,
        "shgc_max": 0.25,
        "climate": "Very Hot Humid",
        "region": "Tropical / Hot",
        "source": "ASHRAE 90.1-2019, Table 5.5-1"
    },
    "ASHRAE 90.1-2019 (Climate Zone 4A)": {
        "wall_u_max": 0.365,
        "roof_u_max": 0.183,
        "window_u_max": 2.556,
        "wwr_max_pct": 40.0,
        "shgc_max": 0.40,
        "climate": "Mixed Humid",
        "region": "Temperate",
        "source": "ASHRAE 90.1-2019, Table 5.5-4"
    },
    "Green Star (Australia)": {
        "wall_u_max": 0.35,
        "roof_u_max": 0.25,
        "window_u_max": 2.00,
        "wwr_max_pct": 40.0,
        "shgc_max": 0.35,
        "climate": "Varies",
        "region": "Australia",
        "source": "Green Star Design & As Built v1.3"
    },
    "UK Building Regs Part L (2021)": {
        "wall_u_max": 0.26,
        "roof_u_max": 0.18,
        "window_u_max": 1.60,
        "wwr_max_pct": 40.0,
        "shgc_max": 0.50,
        "climate": "Temperate",
        "region": "United Kingdom",
        "source": "UK Building Regulations Part L, 2021"
    }
}

# Published embodied carbon benchmarks (kgCO2e/m² GFA)
CARBON_BENCHMARKS = {
    "RIBA 2030 Target (Residential)": 300,
    "RIBA 2030 Target (Commercial)": 350,
    "UK Average (Residential)": 800,
    "UK Average (Commercial)": 600,
    "LEED v4 Threshold": 500,
}

# ─────────────────────────────────────────────────
# CLIMATE DATA FOR HEAT LOSS ESTIMATION
# Design temperatures from ASHRAE Fundamentals / published sources
# T_out_winter: 99% design dry-bulb (°C) — peak heating load
# T_out_summer: 1%  design dry-bulb (°C) — peak cooling load
# T_in_winter : maintained indoor setpoint heating (°C)
# T_in_summer : maintained indoor setpoint cooling (°C)
# HDD / CDD    : published degree-days for annual energy context
# ─────────────────────────────────────────────────
CLIMATE_DATA = {
    "MS1525:2019 (Malaysia)": {
        "location":      "Kuala Lumpur, Malaysia",
        "T_out_winter":  24.0,   # No heating season — min ambient
        "T_out_summer":  34.0,   # ASHRAE 1% cooling DB
        "T_in_winter":   24.0,   # Cooling dominated — same setpoint
        "T_in_summer":   24.0,   # ASHRAE 55 comfort setpoint
        "delta_T_heating": 0.0,  # Tropical — no heating load
        "delta_T_cooling": 10.0, # 34 - 24 = 10K cooling
        "HDD_18":        0,      # Near-zero HDD
        "CDD_18":        3800,   # Very high CDD (published)
        "season":        "Cooling only",
        "source":        "ASHRAE Fundamentals 2021, Chapter 14"
    },
    "ASHRAE 90.1-2019 (Climate Zone 1A)": {
        "location":      "Miami, FL / Hot-Humid Tropical",
        "T_out_winter":  10.0,   # 99% heating DB (Miami: ~10°C)
        "T_out_summer":  33.3,   # 1% cooling DB (Miami: ~33°C)
        "T_in_winter":   21.0,
        "T_in_summer":   24.0,
        "delta_T_heating": 11.0,  # 21 - 10
        "delta_T_cooling": 9.3,   # 33.3 - 24
        "HDD_18":        200,
        "CDD_18":        2700,
        "season":        "Cooling dominant",
        "source":        "ASHRAE Fundamentals 2021, Table 1, Chapter 14"
    },
    "ASHRAE 90.1-2019 (Climate Zone 4A)": {
        "location":      "Baltimore, MD / Mixed-Humid",
        "T_out_winter":  -8.0,   # 99% heating DB
        "T_out_summer":  33.3,   # 1% cooling DB
        "T_in_winter":   21.0,
        "T_in_summer":   24.0,
        "delta_T_heating": 29.0,  # 21 - (-8)
        "delta_T_cooling": 9.3,
        "HDD_18":        2700,
        "CDD_18":        900,
        "season":        "Heating & cooling",
        "source":        "ASHRAE Fundamentals 2021, Table 1, Chapter 14"
    },
    "Green Star (Australia)": {
        "location":      "Sydney, Australia",
        "T_out_winter":  5.0,    # Sydney 99% heating DB
        "T_out_summer":  33.6,   # Sydney 1% cooling DB
        "T_in_winter":   20.0,
        "T_in_summer":   24.0,
        "delta_T_heating": 15.0,
        "delta_T_cooling": 9.6,
        "HDD_18":        1100,
        "CDD_18":        800,
        "season":        "Heating & cooling",
        "source":        "BOM Australia / ASHRAE HOF 2021"
    },
    "UK Building Regs Part L (2021)": {
        "location":      "London, United Kingdom",
        "T_out_winter":  -3.0,   # UK design winter DB (BS EN 12831)
        "T_out_summer":  28.0,   # UK summer design DB
        "T_in_winter":   21.0,
        "T_in_summer":   24.0,
        "delta_T_heating": 24.0,  # 21 - (-3)
        "delta_T_cooling": 4.0,   # 28 - 24 (UK rarely needs active cooling)
        "HDD_18":        2900,
        "CDD_18":        150,
        "season":        "Heating dominant",
        "source":        "BS EN 12831:2017 / CIBSE Guide A"
    },
}


def calculate_fabric_heat_loss(walls: list, roofs: list, windows: list,
                                climate: dict) -> dict:
    """
    Calculate peak fabric heat loss through envelope elements.
    Method: steady-state conduction Q = U × A × ΔT (W)
    This is a peak design load estimate, NOT annual energy consumption.

    Returns dict with breakdown by element type and orientation,
    plus code-compliant comparison showing improvement potential.
    """
    dT_heat = climate["delta_T_heating"]
    dT_cool = climate["delta_T_cooling"]

    # ── Wall heat loss ──
    wall_loss = []
    for w in walls:
        u = w.get("u_value")
        a = w.get("area_m2", 0)
        if u and a:
            q_heat = round(u * a * dT_heat, 1)
            q_cool = round(u * a * dT_cool, 1)
            wall_loss.append({
                "name":        w["name"],
                "orientation": w.get("orientation", "Unknown"),
                "area_m2":     a,
                "u_value":     u,
                "q_heating_W": q_heat,
                "q_cooling_W": q_cool,
            })

    # ── Roof heat loss ──
    roof_loss = []
    for r in roofs:
        u = r.get("u_value")
        a = r.get("area_m2", 0)
        if u and a:
            roof_loss.append({
                "name":        r["name"],
                "area_m2":     a,
                "u_value":     u,
                "q_heating_W": round(u * a * dT_heat, 1),
                "q_cooling_W": round(u * a * dT_cool, 1),
            })

    # ── Window conduction heat loss ──
    win_loss = []
    for w in windows:
        u = w.get("u_value")
        a = w.get("area_m2", 0)
        if u and a:
            win_loss.append({
                "name":        w["name"],
                "orientation": w.get("orientation", "Unknown"),
                "area_m2":     a,
                "u_value":     u,
                "q_heating_W": round(u * a * dT_heat, 1),
                "q_cooling_W": round(u * a * dT_cool, 1),
            })

    # ── Totals ──
    total_wall_heat  = sum(x["q_heating_W"] for x in wall_loss)
    total_wall_cool  = sum(x["q_cooling_W"] for x in wall_loss)
    total_roof_heat  = sum(x["q_heating_W"] for x in roof_loss)
    total_roof_cool  = sum(x["q_cooling_W"] for x in roof_loss)
    total_win_heat   = sum(x["q_heating_W"] for x in win_loss)
    total_win_cool   = sum(x["q_cooling_W"] for x in win_loss)

    total_heat = total_wall_heat + total_roof_heat + total_win_heat
    total_cool = total_wall_cool + total_roof_cool + total_win_cool

    # ── Orientation breakdown ──
    orientations = ["North", "South", "East", "West", "Unknown"]
    orient_heat = {o: 0.0 for o in orientations}
    orient_cool = {o: 0.0 for o in orientations}
    orient_area = {o: 0.0 for o in orientations}
    for item in wall_loss + win_loss:
        ori = item.get("orientation", "Unknown")
        if ori not in orient_heat:
            ori = "Unknown"
        orient_heat[ori] += item["q_heating_W"]
        orient_cool[ori] += item["q_cooling_W"]
        orient_area[ori] += item["area_m2"]

    # ── Heat loss intensity (W/m² envelope) ──
    total_env_area = sum(w.get("area_m2", 0) for w in walls) + \
                     sum(r.get("area_m2", 0) for r in roofs)
    intensity_heat = round(total_heat / total_env_area, 2) if total_env_area else 0
    intensity_cool = round(total_cool / total_env_area, 2) if total_env_area else 0

    return {
        "wall_loss":        wall_loss,
        "roof_loss":        roof_loss,
        "win_loss":         win_loss,
        "total_wall_heat":  round(total_wall_heat, 1),
        "total_wall_cool":  round(total_wall_cool, 1),
        "total_roof_heat":  round(total_roof_heat, 1),
        "total_roof_cool":  round(total_roof_cool, 1),
        "total_win_heat":   round(total_win_heat, 1),
        "total_win_cool":   round(total_win_cool, 1),
        "total_heat_W":     round(total_heat, 1),
        "total_cool_W":     round(total_cool, 1),
        "orient_heat":      {k: round(v, 1) for k, v in orient_heat.items()},
        "orient_cool":      {k: round(v, 1) for k, v in orient_cool.items()},
        "orient_area":      {k: round(v, 1) for k, v in orient_area.items()},
        "intensity_heat":   intensity_heat,
        "intensity_cool":   intensity_cool,
        "dT_heating":       dT_heat,
        "dT_cooling":       dT_cool,
        "total_env_area":   round(total_env_area, 1),
    }


def calculate_code_compliant_heat_loss(walls: list, roofs: list, windows: list,
                                        code: dict, climate: dict) -> dict:
    """
    Calculate what the heat loss WOULD BE if all elements met the code threshold.
    Compares against actual to show improvement potential in watts.
    """
    dT_heat = climate["delta_T_heating"]
    dT_cool = climate["delta_T_cooling"]

    # Replace each element's U with min(actual_U, code_threshold)
    compliant_wall_heat = sum(
        min(w["u_value"], code["wall_u_max"]) * w.get("area_m2", 0) * dT_heat
        for w in walls if w.get("u_value") and w.get("area_m2")
    )
    compliant_wall_cool = sum(
        min(w["u_value"], code["wall_u_max"]) * w.get("area_m2", 0) * dT_cool
        for w in walls if w.get("u_value") and w.get("area_m2")
    )
    compliant_roof_heat = sum(
        min(r["u_value"], code["roof_u_max"]) * r.get("area_m2", 0) * dT_heat
        for r in roofs if r.get("u_value") and r.get("area_m2")
    )
    compliant_win_heat = sum(
        min(w["u_value"], code["window_u_max"]) * w.get("area_m2", 0) * dT_heat
        for w in windows if w.get("u_value") and w.get("area_m2")
    )

    return {
        "compliant_total_heat": round(compliant_wall_heat + compliant_roof_heat + compliant_win_heat, 1),
        "compliant_total_cool": round(compliant_wall_cool, 1),
        "compliant_wall_heat":  round(compliant_wall_heat, 1),
        "compliant_roof_heat":  round(compliant_roof_heat, 1),
        "compliant_win_heat":   round(compliant_win_heat, 1),
    }


def check_wall_compliance(u_value: float, code: dict) -> dict:
    """Check single wall U-value against code threshold."""
    threshold = code["wall_u_max"]
    if u_value is None:
        return {"passed": False, "threshold": threshold, "margin": None,
                "pct_above_threshold": None, "status": "⚠️ NO DATA"}
    passed = u_value <= threshold
    margin = round(threshold - u_value, 4)
    pct_diff = round(((u_value - threshold) / threshold) * 100, 1)
    return {
        "passed": passed,
        "threshold": threshold,
        "margin": margin,
        "pct_above_threshold": pct_diff if not passed else 0,
        "status": "✅ PASS" if passed else "❌ FAIL"
    }


def check_roof_compliance(u_value: float, code: dict) -> dict:
    """Check roof U-value against code threshold."""
    threshold = code["roof_u_max"]
    if u_value is None:
        return {"passed": False, "threshold": threshold, "margin": None, "status": "⚠️ NO DATA"}
    passed = u_value <= threshold
    margin = round(threshold - u_value, 4)
    return {"passed": passed, "threshold": threshold, "margin": margin,
            "status": "✅ PASS" if passed else "❌ FAIL"}


def check_window_compliance(u_value: float, shgc: float, code: dict) -> dict:
    """Check window U-value and SHGC against code thresholds."""
    u_threshold = code["window_u_max"]
    shgc_threshold = code["shgc_max"]
    u_passed = (u_value <= u_threshold) if u_value is not None else None
    shgc_passed = (shgc <= shgc_threshold) if shgc is not None else None
    overall = (u_passed is not False) and (shgc_passed is not False)
    return {
        "u_passed": u_passed, "shgc_passed": shgc_passed,
        "overall_passed": overall,
        "u_threshold": u_threshold, "shgc_threshold": shgc_threshold,
        "status": "✅ PASS" if overall else "❌ FAIL"
    }


def check_wwr_compliance(wwr_pct: float, code: dict) -> dict:
    """Check window-to-wall ratio against code maximum."""
    threshold = code["wwr_max_pct"]
    passed = wwr_pct <= threshold
    return {"passed": passed, "threshold": threshold,
            "actual": round(wwr_pct, 1), "status": "✅ PASS" if passed else "❌ FAIL"}


def calculate_thermal_performance_index(walls: list, roofs: list, code: dict, wwr_pct: float) -> int:
    """
    Calculate overall Thermal Performance Index (TPI) 0–100.
    Weighted composite score:
      - Walls: 50% weight (primary envelope element)
      - Roofs: 30% weight
      - WWR:   20% weight
    Scoring: passing elements scored 50–100 (better = higher),
             failing elements scored 0–49 (worse = lower).
    """
    scores = []

    # Wall score — 50% weight
    wall_u_values = [w["u_value"] for w in walls if w["u_value"]]
    if wall_u_values:
        threshold = code["wall_u_max"]
        wall_scores = []
        for u in wall_u_values:
            if u <= threshold:
                score = min(100, 50 + 50 * (threshold - u) / threshold)
            else:
                score = max(0, 50 - 50 * (u - threshold) / threshold)
            wall_scores.append(score)
        scores.append(("walls", sum(wall_scores) / len(wall_scores), 0.50))

    # Roof score — 30% weight
    roof_u_values = [r["u_value"] for r in roofs if r["u_value"]]
    if roof_u_values:
        threshold = code["roof_u_max"]
        roof_scores = []
        for u in roof_u_values:
            if u <= threshold:
                score = min(100, 50 + 50 * (threshold - u) / threshold)
            else:
                score = max(0, 50 - 50 * (u - threshold) / threshold)
            roof_scores.append(score)
        scores.append(("roofs", sum(roof_scores) / len(roof_scores), 0.30))

    # WWR score — 20% weight
    wwr_threshold = code["wwr_max_pct"]
    if wwr_pct <= wwr_threshold:
        wwr_score = min(100, 50 + 50 * (wwr_threshold - wwr_pct) / wwr_threshold)
    else:
        wwr_score = max(0, 50 - 50 * (wwr_pct - wwr_threshold) / wwr_threshold)
    scores.append(("wwr", wwr_score, 0.20))

    if not scores:
        return 0
    total_weight = sum(s[2] for s in scores)
    tpi = sum(s[1] * s[2] for s in scores) / total_weight
    return int(round(tpi))


def get_tpi_grade(tpi: int) -> tuple:
    """Convert TPI score to letter grade, color, label."""
    if tpi >= 85:
        return "A", "#34D399", "Excellent"
    elif tpi >= 70:
        return "B", "#86EFAC", "Good"
    elif tpi >= 55:
        return "C", "#FBBF24", "Moderate"
    elif tpi >= 40:
        return "D", "#FB923C", "Poor"
    else:
        return "F", "#FB7185", "Non-Compliant"


def generate_insulation_recommendations(walls: list, code: dict) -> list:
    """
    For each unique failing wall type, calculate minimum insulation
    thickness needed from 4 insulation types to achieve compliance.
    Deduplication by wall name prevents double-counting.
    """
    recommendations = []
    threshold = code["wall_u_max"]
    seen_names = set()

    insulation_options = [
        {"name": "EPS (Expanded Polystyrene)", "lambda": 0.038, "cost_index": "Low"},
        {"name": "Mineral Wool", "lambda": 0.038, "cost_index": "Low-Medium"},
        {"name": "XPS (Extruded Polystyrene)", "lambda": 0.034, "cost_index": "Medium"},
        {"name": "PIR Board", "lambda": 0.022, "cost_index": "High"},
    ]

    for wall in walls:
        u = wall.get("u_value")
        name = wall.get("name", "Unknown")
        if u is None or u <= threshold or name in seen_names:
            continue
        seen_names.add(name)

        # R-value deficit calculation
        current_r = max(0, (1 / u) - 0.13 - 0.04)
        target_r = (1 / threshold) - 0.13 - 0.04
        r_deficit = max(0, target_r - current_r)

        options = []
        for insul in insulation_options:
            thickness_needed_m = r_deficit * insul["lambda"]
            thickness_mm = math.ceil(thickness_needed_m * 1000 / 5) * 5  # Round to nearest 5mm
            new_r = current_r + (thickness_mm / 1000) / insul["lambda"]
            new_u = round(1 / (new_r + 0.13 + 0.04), 3)
            options.append({
                "insulation": insul["name"],
                "lambda": insul["lambda"],
                "thickness_mm": thickness_mm,
                "new_u_value": new_u,
                "u_improvement": round(u - new_u, 3),
                "cost_index": insul["cost_index"]
            })

        recommendations.append({
            "wall_name": name,
            "current_u": u,
            "target_u": threshold,
            "r_deficit": round(r_deficit, 4),
            "options": options
        })

    return recommendations


def get_material_confidence_summary(walls: list) -> dict:
    """
    Aggregate material matching confidence across all wall layers.
    Returns summary dict for transparency reporting in paper.
    """
    total = high = medium = low = 0
    for wall in walls:
        for layer in wall.get("layers", []):
            conf = layer.get("confidence", "low")
            total += 1
            if conf == "high":
                high += 1
            elif conf == "medium":
                medium += 1
            else:
                low += 1
    return {
        "total_layers": total,
        "high_pct": round(high / total * 100, 1) if total else 0,
        "medium_pct": round(medium / total * 100, 1) if total else 0,
        "low_pct": round(low / total * 100, 1) if total else 0,
        "high": high, "medium": medium, "low": low
    }


def compute_validation_stats(val_data: list) -> dict:
    """
    Compute MAPE, RMSE, max error, r-squared from validation data.
    val_data: list of dicts with 'manual' and 'tool' keys.
    Always returns results as long as at least one valid pair exists.
    """
    if not val_data:
        return {}

    # Accept all pairs where manual > 0 and tool is a valid number
    pairs = []
    for d in val_data:
        m = d.get("manual", 0)
        t = d.get("tool", 0)
        if m and m > 0 and t is not None and t > 0:
            pairs.append((float(m), float(t)))

    if not pairs:
        return {}

    n = len(pairs)
    manuals = [p[0] for p in pairs]
    tools   = [p[1] for p in pairs]

    mape    = sum(abs(t - m) / m * 100 for m, t in pairs) / n
    rmse    = math.sqrt(sum((t - m) ** 2 for m, t in pairs) / n)
    max_err = max(abs(t - m) / m * 100 for m, t in pairs)
    mean_m  = sum(manuals) / n
    ss_tot  = sum((m - mean_m) ** 2 for m in manuals)
    ss_res  = sum((m - t) ** 2 for m, t in pairs)
    # When all values are identical ss_tot=0 → perfect agreement R²=1.0
    r2 = 1.0 if ss_tot == 0 else round(1 - (ss_res / ss_tot), 6)

    return {
        "n": n,
        "mape": round(mape, 4),
        "rmse": round(rmse, 6),
        "max_error_pct": round(max_err, 4),
        "r_squared": r2,
        "validated": mape < 2.0
    }
