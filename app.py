"""
app.py — BIM Thermal Envelope Dashboard (Final Research Version)
================================================================
Author  : Md Obidul Haque
Purpose : Research — automated IFC thermal compliance assessment
Method  : ISO 6946 U-value from IFC material layers (ifcopenshell)
Codes   : MS1525:2019, ASHRAE 90.1-2019, Green Star, UK Part L 2021

Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import tempfile, os, json
from datetime import datetime

from ifc_parser import parse_ifc, load_thermal_database
from compliance import (
    CODES, CLIMATE_DATA,
    check_wall_compliance, check_roof_compliance,
    check_window_compliance, check_wwr_compliance,
    calculate_thermal_performance_index, get_tpi_grade,
    generate_insulation_recommendations,
    get_material_confidence_summary, compute_validation_stats,
    calculate_fabric_heat_loss, calculate_code_compliant_heat_loss
)

# ─────────────────────────────────────────────────
st.set_page_config(
    page_title="BIM Thermal Dashboard — Md Obidul Haque",
    page_icon="🏗️", layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────
# CSS — dark glass with purple/cyan/pink gradients
# ─────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap');

:root {
  --bg0:#070A12; --g1:rgba(255,255,255,0.06); --g2:rgba(255,255,255,0.09);
  --sk:rgba(255,255,255,0.12); --sk2:rgba(255,255,255,0.18);
  --tx:rgba(255,255,255,0.92); --tx2:rgba(255,255,255,0.78);
  --mu:rgba(255,255,255,0.58);
  --ac:#7C3AED; --cy:#22D3EE; --pk:#F472B6;
  --warn:#FBBF24; --pass:#34D399; --fail:#FB7185;
  --sh:0 10px 30px rgba(0,0,0,0.45); --sh2:0 18px 56px rgba(0,0,0,0.55);
  --rd:16px;
}

html,body,[class*="css"] {
  font-family:"Manrope",system-ui,sans-serif;
  background:
    radial-gradient(1100px 650px at 18% 8%,  rgba(124,58,237,0.24),transparent 55%),
    radial-gradient(850px  600px at 86% 12%, rgba(34,211,238,0.20),transparent 58%),
    radial-gradient(900px  550px at 48% 90%, rgba(244,114,182,0.15),transparent 54%),
    var(--bg0);
  color:var(--tx);
}
.stApp{background:transparent!important;}
.block-container{padding-top:1rem;padding-bottom:2rem;max-width:1420px;}

[data-testid="stSidebar"]{
  background:linear-gradient(180deg,rgba(255,255,255,0.07),rgba(255,255,255,0.03))!important;
  border-right:1px solid var(--sk2)!important; backdrop-filter:blur(18px);
}
#MainMenu,footer,.stDeployButton{visibility:hidden;display:none;}

/* HEADER */
.dash-header{
  border-radius:22px; padding:1.9rem 2.2rem 1.6rem;
  margin-bottom:1.1rem;
  background:
    radial-gradient(850px 280px at 10% 0%,rgba(124,58,237,0.38),transparent 58%),
    radial-gradient(850px 280px at 90% 0%,rgba(34,211,238,0.30),transparent 60%),
    rgba(255,255,255,0.065);
  border:1px solid var(--sk2); box-shadow:var(--sh2);
  backdrop-filter:blur(20px); position:relative; overflow:hidden;
}
.dash-header::after{
  content:""; position:absolute; inset:-1px; border-radius:23px; padding:1px;
  background:linear-gradient(90deg,rgba(124,58,237,0.70),rgba(34,211,238,0.62),rgba(244,114,182,0.52));
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);
  -webkit-mask-composite:xor; mask-composite:exclude;
  opacity:0.52; pointer-events:none;
}
.dash-title{
  font-family:"JetBrains Mono",monospace; font-size:1.95rem;
  font-weight:800; letter-spacing:-0.03em; color:var(--tx); margin:0;
}
.dash-meta{
  font-size:0.82rem; color:var(--tx2); margin-top:0.4rem;
  font-family:"JetBrains Mono",monospace; letter-spacing:0.03em;
}
.accent-bar{
  width:58px; height:4px; border-radius:999px; margin:0.80rem 0 0.3rem;
  background:linear-gradient(90deg,var(--ac),var(--cy),var(--pk));
}

/* SECTION LABEL */
.section-title{
  font-family:"JetBrains Mono",monospace; font-size:0.78rem;
  text-transform:uppercase; letter-spacing:0.18em;
  color:rgba(34,211,238,0.95); border-left:3px solid rgba(34,211,238,0.82);
  padding-left:10px; margin:1.4rem 0 0.9rem;
}

/* METRIC CARD */
.metric-card{
  background:linear-gradient(160deg,rgba(255,255,255,0.09),rgba(255,255,255,0.04));
  border:1px solid var(--sk); border-radius:var(--rd);
  padding:1.0rem 1.1rem; box-shadow:var(--sh);
  backdrop-filter:blur(16px); position:relative; overflow:hidden;
  transition:transform .16s ease,border-color .16s ease;
}
.metric-card:hover{transform:translateY(-2px);border-color:var(--sk2);}
.metric-card::before{
  content:""; position:absolute; top:0;left:0;right:0; height:2px;
  background:linear-gradient(90deg,rgba(124,58,237,.85),rgba(34,211,238,.78),rgba(244,114,182,.68));
}
.metric-label{
  font-size:0.68rem; color:var(--mu); text-transform:uppercase;
  letter-spacing:0.13em; font-family:"JetBrains Mono",monospace; margin-bottom:0.45rem;
}
.metric-value{font-size:1.8rem;font-weight:800;color:var(--tx);line-height:1.05;}
.metric-sub{font-size:0.79rem;color:var(--tx2);margin-top:0.40rem;}

/* BADGES */
.badge-pass{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;
  border-radius:999px;font-size:0.72rem;font-weight:800;
  font-family:"JetBrains Mono",monospace;
  border:1px solid rgba(52,211,153,0.30);color:rgba(52,211,153,0.95);
  background:rgba(52,211,153,0.09);}
.badge-fail{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;
  border-radius:999px;font-size:0.72rem;font-weight:800;
  font-family:"JetBrains Mono",monospace;
  border:1px solid rgba(251,113,133,0.30);color:rgba(251,113,133,0.95);
  background:rgba(251,113,133,0.09);}
.badge-warn{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;
  border-radius:999px;font-size:0.72rem;font-weight:800;
  font-family:"JetBrains Mono",monospace;
  border:1px solid rgba(251,191,36,0.28);color:rgba(251,191,36,0.95);
  background:rgba(251,191,36,0.09);}

/* INFO BOX */
.info-box{
  background:linear-gradient(160deg,rgba(124,58,237,0.12),rgba(34,211,238,0.07));
  border:1px solid rgba(34,211,238,0.17); border-radius:14px;
  padding:0.90rem 1.05rem; font-size:0.86rem; color:var(--tx2);
  box-shadow:var(--sh); margin:0.8rem 0;
}
code{
  background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.13);
  padding:1px 6px; border-radius:8px;
  color:rgba(34,211,238,0.95); font-family:"JetBrains Mono",monospace; font-size:0.84em;
}

/* UPLOAD */
.upload-zone{
  background:linear-gradient(160deg,rgba(255,255,255,0.08),rgba(255,255,255,0.04));
  border:1.5px dashed rgba(255,255,255,0.20); border-radius:22px;
  padding:2.8rem 2rem; text-align:center;
  box-shadow:var(--sh2); backdrop-filter:blur(16px);
}

/* TABS */
.stTabs [data-baseweb="tab-list"]{
  background:rgba(255,255,255,0.055); border:1px solid var(--sk);
  border-radius:14px; padding:5px; gap:5px; backdrop-filter:blur(14px);
}
.stTabs [data-baseweb="tab"]{
  background:transparent; border-radius:11px;
  color:rgba(255,255,255,0.68); font-family:"JetBrains Mono",monospace;
  font-size:0.74rem; padding:0.50rem 0.95rem;
}
.stTabs [aria-selected="true"]{
  background:linear-gradient(90deg,rgba(124,58,237,0.92),rgba(34,211,238,0.88))!important;
  color:#050912!important; font-weight:900!important;
}

.stDataFrame{border:1px solid var(--sk)!important;border-radius:12px!important;box-shadow:var(--sh);}
.stButton>button{
  border-radius:12px; border:1px solid rgba(255,255,255,0.13);
  background:linear-gradient(90deg,rgba(124,58,237,0.22),rgba(34,211,238,0.16))!important;
  color:rgba(255,255,255,0.92)!important; font-weight:700; box-shadow:var(--sh);
}
.stButton>button:hover{border-color:rgba(34,211,238,0.28);transform:translateY(-1px);transition:.15s;}
</style>
""", unsafe_allow_html=True)

# Watermark
st.markdown("""
<div style="position:fixed;right:16px;bottom:12px;z-index:9999;
  font-family:'JetBrains Mono',monospace;font-size:10.5px;
  color:rgba(255,255,255,0.40);background:rgba(0,0,0,0.22);
  border:1px solid rgba(255,255,255,0.09);padding:5px 10px;
  border-radius:999px;backdrop-filter:blur(10px);pointer-events:none;">
  © 2025 Md Obidul Haque
</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# CHART THEME
# ─────────────────────────────────────────────────
CT = {
    "paper": "rgba(255,255,255,0.055)", "plot": "rgba(255,255,255,0.03)",
    "font":  "rgba(255,255,255,0.88)",  "muted":"rgba(255,255,255,0.65)",
    "grid":  "rgba(255,255,255,0.09)",
    "pass":  "rgba(52,211,153,0.85)",   "fail": "rgba(251,113,133,0.50)",
    "warn":  "#FBBF24", "accent":"#7C3AED", "cyan":"#22D3EE", "ff":"Manrope",
}

def chlayout(title="", h=400, l=20, r=20, t=48, b=20):
    return dict(
        title=dict(text=title, font=dict(size=12,color=CT["muted"],family=CT["ff"])),
        paper_bgcolor=CT["paper"], plot_bgcolor=CT["plot"],
        font=dict(color=CT["font"],family=CT["ff"]),
        height=h, margin=dict(l=l,r=r,t=t,b=b),
        xaxis=dict(gridcolor=CT["grid"],linecolor=CT["grid"],tickfont=dict(size=9,color=CT["muted"])),
        yaxis=dict(gridcolor=CT["grid"],linecolor=CT["grid"],tickfont=dict(size=9,color=CT["muted"])),
    )

def metric_card(label, value, sub="", color=None):
    cs = f"color:{color};" if color else ""
    st.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">{label}</div>
      <div class="metric-value" style="{cs}">{value}</div>
      <div class="metric-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:.85rem .95rem;border-radius:14px;
      background:linear-gradient(160deg,rgba(255,255,255,0.10),rgba(255,255,255,0.04));
      border:1px solid rgba(255,255,255,0.12);box-shadow:0 12px 32px rgba(0,0,0,0.35);
      margin-bottom:1rem;">
      <div style="font-family:'JetBrains Mono',monospace;font-size:.98rem;font-weight:800;
        color:rgba(34,211,238,0.95);margin-bottom:.2rem;">🏗️ BIM THERMAL</div>
      <div style="font-size:.82rem;font-weight:700;color:rgba(255,255,255,0.90);margin-bottom:.18rem;">
        Md Obidul Haque</div>
      <div style="font-size:.74rem;color:rgba(255,255,255,0.62);line-height:1.4;">
        Envelope Analysis Dashboard</div>
      <div style="margin-top:.50rem;font-family:'JetBrains Mono',monospace;font-size:.64rem;
        color:rgba(255,255,255,0.48);letter-spacing:.08em;text-transform:uppercase;">
        © 2025 · Research Tool · ISO 6946</div>
    </div>""", unsafe_allow_html=True)

    st.markdown("**Energy Code**")
    selected_code_name = st.selectbox("code", list(CODES.keys()), index=0, label_visibility="collapsed")
    code = CODES[selected_code_name]

    st.markdown(f"""
    <div class="info-box" style="margin-top:.6rem;font-size:.80rem;">
    🌍 <b>{code['region']}</b> · {code['climate']}<br>
    <span style="font-size:.70rem;color:rgba(255,255,255,0.50);">Source: {code['source']}</span><br><br>
    <b>Prescriptive Thresholds:</b><br>
    Wall &nbsp;U ≤ {code['wall_u_max']} W/m²K<br>
    Roof &nbsp;U ≤ {code['roof_u_max']} W/m²K<br>
    Window U ≤ {code['window_u_max']} W/m²K<br>
    Max WWR ≤ {code['wwr_max_pct']}%<br>
    Max SHGC ≤ {code['shgc_max']}
    </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
    <div style="font-size:.78rem;color:rgba(255,255,255,0.65);line-height:1.55;">
    Upload any IFC file from Revit.<br>U-values calculated via <b>ISO 6946</b>
    from extracted material layer data.<br><br>
    <b>Research Tool</b> — Designed for BIM automation.
    </div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────
st.markdown("""
<div class="dash-header">
  <div class="dash-title">BIM Thermal Envelope Dashboard</div>
  <div class="accent-bar"></div>
  <div class="dash-meta">
    Automated IFC → Material Extraction → ISO 6946 U-value → Multi-Code Compliance · Research Grade
  </div>
</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────
for key, default in [("parsed_data", None), ("filename", None), ("val_entered", False)]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─────────────────────────────────────────────────
# UPLOAD
# ─────────────────────────────────────────────────
if st.session_state.parsed_data is None:
    st.markdown("""
    <div class="upload-zone">
      <div style="font-size:2.8rem;margin-bottom:.8rem;">🏛️</div>
      <div style="font-family:'JetBrains Mono',monospace;font-size:1.05rem;font-weight:900;
        color:rgba(255,255,255,0.92);margin-bottom:.45rem;">UPLOAD YOUR IFC FILE</div>
      <div style="font-size:.85rem;color:rgba(255,255,255,0.66);">
        Export from Revit as IFC4 · Enable Psets and Base Quantities<br>
        The dashboard builds itself automatically in seconds.
      </div>
    </div>""", unsafe_allow_html=True)

    uploaded = st.file_uploader("IFC", type=["ifc"], label_visibility="collapsed")

    if uploaded:
        tmp_path = None
        try:
            with st.spinner("🔍 Parsing IFC · Extracting material layers · Calculating U-values..."):
                with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
                    tmp.write(uploaded.read())
                    tmp_path = tmp.name
                db_path = os.path.join(os.path.dirname(__file__), "thermal_database.csv")
                thermal_db = load_thermal_database(db_path)
                data = parse_ifc(tmp_path, thermal_db)
                st.session_state.parsed_data = data
                st.session_state.filename = uploaded.name
                st.session_state.val_entered = False
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error parsing IFC: {e}")
            st.info("Ensure wall assemblies have material layers defined in Revit Edit Assembly.")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    st.markdown("""<div style="text-align:center;color:rgba(255,255,255,0.52);
    font-size:.78rem;margin-top:1.5rem;">
    Tip: Revit → File → Export → IFC → IFC4 Reference View → ✅ Base Quantities + Psets
    </div>""", unsafe_allow_html=True)
    st.stop()

# ─────────────────────────────────────────────────
# DATA LOADED
# ─────────────────────────────────────────────────
@st.cache_data
def compute_wall_results(filename, code_name, walls_json):
    """Cache compliance results per file+code combination."""
    walls = json.loads(walls_json)
    c = CODES[code_name]
    return [(w, check_wall_compliance(w["u_value"], c)) for w in walls if w["u_value"] is not None]

@st.cache_data
def get_unique_types(walls_json):
    """Deduplicate walls by type name for research reporting."""
    walls = json.loads(walls_json)
    seen, unique = set(), []
    for w in walls:
        if w["name"] not in seen:
            seen.add(w["name"])
            unique.append(w)
    return unique

data    = st.session_state.parsed_data
summary = data["summary"]
walls   = data["walls"]
windows = data["windows"]
roofs   = data["roofs"]

walls_json    = json.dumps(walls)
wall_results  = compute_wall_results(st.session_state.filename, selected_code_name, walls_json)
unique_types  = get_unique_types(walls_json)

pass_count = sum(1 for _, r in wall_results if r["passed"])
fail_count = len(wall_results) - pass_count
pass_types = sum(1 for w in unique_types
                 if w["u_value"] and w["u_value"] <= code["wall_u_max"])
fail_types = len(unique_types) - pass_types

tpi = calculate_thermal_performance_index(walls, roofs, code, summary["overall_wwr_pct"])
tpi_grade, tpi_color, tpi_label = get_tpi_grade(tpi)
conf = get_material_confidence_summary(walls)

# Sidebar file info + reset
with st.sidebar:
    st.markdown("---")
    if st.button("🔄 Upload New File", use_container_width=True):
        st.session_state.parsed_data = None
        st.session_state.filename = None
        compute_wall_results.clear()
        get_unique_types.clear()
        st.rerun()
    st.markdown(f"""
    <div style="font-size:.74rem;color:rgba(255,255,255,0.62);margin-top:.8rem;line-height:1.55;">
    📄 {st.session_state.filename}<br>
    Schema: {data['ifc_schema']}<br>
    Instances: {summary['total_external_walls']} walls · {summary['total_windows']} windows<br>
    Unique types: {len(unique_types)}<br>
    Parsed: {datetime.now().strftime('%H:%M:%S')}
    </div>""", unsafe_allow_html=True)

    st.markdown(f"""
    <div style="margin-top:.9rem;font-size:.74rem;color:rgba(255,255,255,0.62);">
    <b>Material Match Confidence</b><br>
    🟢 High: {conf['high_pct']}% &nbsp;
    🟡 Med: {conf['medium_pct']}% &nbsp;
    🔴 Low: {conf['low_pct']}%<br>
    <span style="font-size:.66rem;color:rgba(255,255,255,.44);">
    Report in paper methodology section</span>
    </div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# 01 — OVERVIEW CARDS
# ─────────────────────────────────────────────────
st.markdown('<div class="section-title">01 — PROJECT OVERVIEW</div>', unsafe_allow_html=True)

c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1: metric_card("Wall Instances", str(summary["total_external_walls"]), "elements in IFC")
with c2: metric_card("Unique Types", str(len(unique_types)), "distinct assemblies")
with c3: metric_card("Windows", str(summary["total_windows"]), "glazing units")
with c4: metric_card("Envelope Area", f"{summary['total_wall_area_m2']:.0f} m²", "total external wall")
with c5:
    wwr = summary["overall_wwr_pct"]
    metric_card("Overall WWR", f"{wwr:.1f}%", f"limit: {code['wwr_max_pct']}%",
                CT["pass"] if wwr <= code["wwr_max_pct"] else CT["fail"])
with c6:
    metric_card("Thermal Index", f"{tpi}/100", f"Grade {tpi_grade} · {tpi_label}", tpi_color)

st.markdown("<br>", unsafe_allow_html=True)

# Compliance banner
if fail_types == 0:
    st.markdown(f"""
    <div style="background:rgba(52,211,153,0.10);border:1px solid rgba(52,211,153,0.22);
    border-radius:16px;padding:1rem 1.2rem;display:flex;align-items:center;gap:1rem;
    box-shadow:0 16px 44px rgba(0,0,0,0.35);backdrop-filter:blur(14px);">
    <span style="font-size:1.5rem;">✅</span>
    <div>
      <div style="font-family:'JetBrains Mono',monospace;font-weight:900;
        color:rgba(52,211,153,0.95);font-size:.90rem;">ALL WALL TYPES COMPLIANT</div>
      <div style="font-size:.82rem;color:rgba(255,255,255,0.70);">
        All {len(unique_types)} unique assembly types pass {selected_code_name}</div>
    </div></div>""", unsafe_allow_html=True)
else:
    pct = round(fail_types / len(unique_types) * 100, 1) if unique_types else 0
    st.markdown(f"""
    <div style="background:rgba(251,113,133,0.10);border:1px solid rgba(251,113,133,0.22);
    border-radius:16px;padding:1rem 1.2rem;display:flex;align-items:center;gap:1rem;
    box-shadow:0 16px 44px rgba(0,0,0,0.35);backdrop-filter:blur(14px);">
    <span style="font-size:1.5rem;">⚠️</span>
    <div>
      <div style="font-family:'JetBrains Mono',monospace;font-weight:900;
        color:rgba(251,113,133,0.95);font-size:.90rem;">
        {fail_types} ASSEMBLY TYPE(S) FAILING — {pct}% NON-COMPLIANT</div>
      <div style="font-size:.82rem;color:rgba(255,255,255,0.70);">
        {pass_types} types passing · {fail_types} types failing · Standard: {selected_code_name}<br>
        <span style="font-size:.76rem;opacity:.75;">
        (Unique types: {len(unique_types)} · Total wall instances: {summary['total_external_walls']})</span>
      </div>
    </div></div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🧱 U-Value Analysis",
    "🧮 R-Value Analysis",
    "🗺️ Facade Map",
    "🪟 Glazing",
    "🔧 Scenarios",
    "🌡️ Heat Loss",
    "✅ Validation",
    "📋 Raw Data"
])

# ══════════════════════════════════════════════════
# TAB 1 — U-VALUE ANALYSIS
# ══════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-title">02 — U-VALUE COMPLIANCE ASSESSMENT</div>',
                unsafe_allow_html=True)

    if not wall_results:
        st.warning("No U-values calculated. Ensure wall assemblies have material layers defined in Revit.")
    else:
        threshold = code["wall_u_max"]
        # Sort worst first for visual clarity
        sorted_walls = sorted(wall_results, key=lambda x: x[0].get("u_value", 0), reverse=True)

        wall_names, u_values, bar_colors, hover_texts = [], [], [], []
        for wall, result in sorted_walls:
            wall_names.append(wall["name"][:42])
            u_values.append(wall["u_value"])
            bar_colors.append(CT["pass"] if result["passed"] else CT["fail"])
            layers_str = " | ".join(
                f"{l['material_name']} {l['thickness_mm']:.0f}mm"
                for l in wall["layers"] if l.get("thickness_mm")
            )
            hover_texts.append(
                f"<b>{wall['name']}</b><br>"
                f"U-value: {wall['u_value']} W/m²K<br>"
                f"Status: {result['status']}<br>"
                f"Margin: {result['margin']:+.4f} W/m²K<br>"
                f"Layers: {layers_str}"
            )

        col_bar, col_right = st.columns([3, 2])

        with col_bar:
            n = len(wall_names)

            # ✅ FIX: cap height so the chart never becomes extremely tall
            ch = min(650, max(360, n * 18 + 140))

            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                y=wall_names, x=u_values, orientation="h",
                marker_color=bar_colors,
                text=[f"{u:.3f}" for u in u_values],
                textposition="outside",
                textfont=dict(family=CT["ff"], size=10, color=CT["font"]),
                hovertext=hover_texts, hoverinfo="text",
                hoverlabel=dict(bgcolor="rgba(8,12,24,0.96)",
                                bordercolor="rgba(255,255,255,0.14)",
                                font=dict(color=CT["font"])),
            ))
            fig_bar.add_vline(x=threshold, line_dash="dash",
                              line_color=CT["warn"], line_width=2,
                              annotation_text=f"Code Limit: {threshold} W/m²K",
                              annotation_font=dict(color=CT["warn"],size=10,family=CT["ff"]),
                              annotation_position="top right")
            lay = chlayout("Wall U-Values vs. Compliance Threshold", h=ch, l=5, r=72, t=42, b=25)
            lay["xaxis"]["title"] = "U-Value (W/m²K)"
            lay["xaxis"]["title_font"] = dict(size=10, color=CT["muted"])
            lay["bargap"] = 0.30
            lay["showlegend"] = False
            fig_bar.update_layout(**lay)
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_right:
            # ✅ FIX: keep right-column plots always visible (do NOT tie height to left chart)
            half_h = 260

            # Donut — unique types pass/fail
            fig_donut = go.Figure(go.Pie(
                labels=["Pass","Fail"],
                values=[pass_types, fail_types],
                hole=0.60,
                marker=dict(colors=["rgba(52,211,153,0.88)","rgba(251,113,133,0.38)"],
                            line=dict(color="rgba(255,255,255,0.12)",width=2)),
                textinfo="label+percent",
                textfont=dict(size=11,family=CT["ff"],color=CT["font"]),
                hovertemplate="<b>%{label}</b><br>%{value} assembly types<extra></extra>",
                pull=[0.04,0.04]
            ))
            fig_donut.add_annotation(
                text=f"<b>{len(unique_types)}</b><br>types",
                x=0.5,y=0.5,showarrow=False,
                font=dict(size=14,color=CT["font"],family=CT["ff"]),align="center"
            )
            dl = chlayout("Assembly Type Pass / Fail", h=half_h, l=10, r=10, t=36, b=28)
            dl["showlegend"] = True
            dl["legend"] = dict(orientation="h",x=0.5,xanchor="center",y=-0.06,
                                 font=dict(size=10,color=CT["muted"]))
            fig_donut.update_layout(**dl)
            st.plotly_chart(fig_donut, use_container_width=True)

            # Box plot
            pass_u = [w["u_value"] for w,r in wall_results if r["passed"] and w["u_value"]]
            fail_u = [w["u_value"] for w,r in wall_results if not r["passed"] and w["u_value"]]
            fig_box = go.Figure()
            if pass_u:
                fig_box.add_trace(go.Box(
                    y=pass_u, name="Pass",
                    marker_color="rgba(52,211,153,0.90)",
                    line=dict(color="rgba(52,211,153,0.90)",width=1.5),
                    fillcolor="rgba(52,211,153,0.12)", boxmean="sd"
                ))
            if fail_u:
                fig_box.add_trace(go.Box(
                    y=fail_u, name="Fail",
                    marker_color="rgba(251,113,133,0.72)",
                    line=dict(color="rgba(251,113,133,0.72)",width=1.5),
                    fillcolor="rgba(251,113,133,0.10)", boxmean="sd"
                ))
            fig_box.add_hline(y=threshold, line_dash="dash",
                              line_color=CT["warn"], line_width=1.5,
                              annotation_text=f"Limit: {threshold}",
                              annotation_font=dict(size=9,color=CT["warn"],family=CT["ff"]))
            bl = chlayout("U-Value Distribution (with SD)", h=half_h, l=45, r=12, t=36, b=28)
            bl["yaxis"]["title"] = "W/m²K"
            bl["yaxis"]["title_font"] = dict(size=9,color=CT["muted"])
            bl["showlegend"] = True
            bl["legend"] = dict(orientation="h",x=0.5,xanchor="center",y=-0.10,
                                 font=dict(size=10,color=CT["muted"]))
            fig_box.update_layout(**bl)
            st.plotly_chart(fig_box, use_container_width=True)

        # ── Layer Details ──
        st.markdown('<div class="section-title">WALL ASSEMBLY LAYER DETAILS</div>',
                    unsafe_allow_html=True)
        st.markdown("""
        <div class="info-box">
        📐 <b>ISO 6946:</b> U = 1 / (R<sub>si</sub> + Σ d<sub>i</sub>/λ<sub>i</sub> + R<sub>so</sub>)
        &nbsp;·&nbsp; R<sub>si</sub>=0.13 &nbsp;·&nbsp; R<sub>so</sub>=0.04 m²K/W<br>
        <span style="font-size:.78rem;color:rgba(255,255,255,0.52);">
        λ values from published databases (ASHRAE Fundamentals / EN 12524).
        Confidence = material name matching accuracy.</span>
        </div>""", unsafe_allow_html=True)

        shown_types = set()
        for wall, result in sorted_walls:
            # Show each unique type once in detail expanders
            is_dupe = wall["name"] in shown_types
            shown_types.add(wall["name"])
            dupe_label = " *(duplicate instance)*" if is_dupe else ""
            margin_txt = (f"✓ within limit by {abs(result['margin'])} W/m²K"
                          if result["passed"]
                          else f"✗ exceeds by {abs(result['margin'])} W/m²K")
            margin_col = "rgba(52,211,153,0.95)" if result["passed"] else "rgba(251,113,133,0.95)"

            with st.expander(
                f"{'✅' if result['passed'] else '❌'}  {wall['name']}{dupe_label}  ·  "
                f"U = {wall['u_value']} W/m²K  ·  {margin_txt}"
            ):
                ca, cb = st.columns([3,1])
                with ca:
                    rows = []
                    for i, layer in enumerate(wall["layers"]):
                        r = layer.get("r_value", 0)
                        rows.append({
                            "Layer": i+1,
                            "Material (IFC)": layer["material_name"],
                            "DB Match": layer.get("matched_material","—"),
                            "Confidence": layer.get("confidence","—").upper(),
                            "Thickness (mm)": f"{layer['thickness_mm']:.1f}" if layer.get("thickness_mm") else "—",
                            "λ (W/mK)": layer.get("lambda","—"),
                            "R (m²K/W)": f"{r:.4f}" if isinstance(r,float) else "—",
                        })
                    rows += [
                        {"Layer":"Rsi","Material (IFC)":"Interior surface resistance",
                         "DB Match":"ISO 6946","Confidence":"STANDARD",
                         "Thickness (mm)":"—","λ (W/mK)":"—","R (m²K/W)":"0.1300"},
                        {"Layer":"Rso","Material (IFC)":"Exterior surface resistance",
                         "DB Match":"ISO 6946","Confidence":"STANDARD",
                         "Thickness (mm)":"—","λ (W/mK)":"—","R (m²K/W)":"0.0400"},
                    ]
                    r_total = sum(float(row["R (m²K/W)"]) for row in rows if row["R (m²K/W)"] != "—")
                    rows.append({"Layer":"TOTAL","Material (IFC)":"—","DB Match":"—",
                                 "Confidence":f"→ U = {wall['u_value']} W/m²K",
                                 "Thickness (mm)":f"{wall['total_thickness_mm']:.0f}",
                                 "λ (W/mK)":"—","R (m²K/W)":f"{r_total:.4f}"})
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                with cb:
                    badge = '<span class="badge-pass">✅ PASS</span>' if result["passed"] \
                            else '<span class="badge-fail">❌ FAIL</span>'
                    st.markdown(f"""
                    <div style="text-align:center;padding:1rem;border-radius:14px;
                      background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.11);">
                      {badge}
                      <div style="margin-top:1.2rem;">
                        <div class="metric-label">Calculated U</div>
                        <div style="font-size:1.9rem;font-family:'JetBrains Mono',monospace;
                          font-weight:900;color:{CT['font']};">{wall['u_value']}</div>
                        <div style="font-size:.70rem;color:{CT['muted']};">W/m²K</div>
                      </div>
                      <div style="margin-top:.9rem;">
                        <div class="metric-label">Code Limit</div>
                        <div style="font-size:1.5rem;font-family:'JetBrains Mono',monospace;
                          font-weight:900;color:{CT['warn']};">{threshold}</div>
                        <div style="font-size:.70rem;color:{CT['muted']};">W/m²K</div>
                      </div>
                      <div style="margin-top:.9rem;font-size:.78rem;color:{margin_col};">
                        {margin_txt}
                      </div>
                    </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════
# TAB 2 — R-VALUE ANALYSIS (ISO 6946)
# ══════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-title">03 — R-VALUE ANALYSIS (ISO 6946)</div>',
                unsafe_allow_html=True)

    st.markdown(f"""
    <div class="info-box">
    🧮 <b>Definition:</b> R<sub>total</sub> = 1 / U &nbsp; (m²K/W)<br>
    ISO 6946 also includes surface resistances: R<sub>si</sub>=0.13 and R<sub>so</sub>=0.04 m²K/W.<br>
    <span style="font-size:.78rem;color:rgba(255,255,255,0.52);">
    This tab improves interpretability: U is used for code compliance, R shows thermal resistance accumulation.
    </span>
    </div>
    """, unsafe_allow_html=True)

    if not wall_results:
        st.warning("No wall U-values available to derive R-values.")
    else:
        # Unique wall types (avoid repetition)
        unique_r = []
        seen = set()
        for w, r in wall_results:
            name = w.get("name", "")
            if name and name not in seen and w.get("u_value") not in (None, 0):
                seen.add(name)
                unique_r.append((w, r))

        if not unique_r:
            st.warning("No valid U-values found (U must be > 0) to compute R-values.")
        else:
            threshold_u = code["wall_u_max"]
            threshold_r = (1.0 / threshold_u) if threshold_u else None

            # Prepare data
            names = []
            r_vals = []
            colors = []
            hover = []

            for wall, res in unique_r:
                u = float(wall["u_value"])
                rtot = 1.0 / u if u > 0 else None

                names.append(wall["name"][:42])
                r_vals.append(rtot)

                # Pass logic (same as U-pass): U <= Umax  ↔  R >= 1/Umax
                passed = res.get("passed", False)
                colors.append(CT["pass"] if passed else CT["fail"])

                hover.append(
                    f"<b>{wall['name']}</b><br>"
                    f"U: {u:.4f} W/m²K<br>"
                    f"R-total: {rtot:.4f} m²K/W<br>"
                    f"Status: {res.get('status','—')}<br>"
                    f"{'Meets code' if passed else 'Fails code'}"
                )

            # Sort by R ascending (worst resistance first)
            order = np.argsort(r_vals)
            names = [names[i] for i in order]
            r_vals = [r_vals[i] for i in order]
            colors = [colors[i] for i in order]
            hover = [hover[i] for i in order]

            colA, colB = st.columns([3, 2])

            with colA:
                # Fixed height (no endless scroll)
                n = len(names)
                chart_h = 520 if n > 24 else (480 if n > 12 else 420)

                fig_rbar = go.Figure()
                fig_rbar.add_trace(go.Bar(
                    y=names,
                    x=r_vals,
                    orientation="h",
                    marker_color=colors,
                    text=[f"R={v:.2f}" for v in r_vals],
                    textposition="outside",
                    textfont=dict(family=CT["ff"], size=10, color=CT["font"]),
                    hovertext=hover,
                    hoverinfo="text",
                    hoverlabel=dict(
                        bgcolor="rgba(8,12,24,0.96)",
                        bordercolor="rgba(255,255,255,0.14)",
                        font=dict(color=CT["font"])
                    )
                ))

                if threshold_r is not None:
                    fig_rbar.add_vline(
                        x=threshold_r,
                        line_dash="dash",
                        line_color=CT["warn"],
                        line_width=2,
                        annotation_text=f"Min R for code (≈ 1/{threshold_u}) = {threshold_r:.2f}",
                        annotation_font=dict(color=CT["warn"], size=10, family=CT["ff"]),
                        annotation_position="top right"
                    )

                lay = chlayout("R-total by Wall Assembly Type (Derived from U)", h=chart_h, l=5, r=80, t=42, b=25)
                lay["xaxis"]["title"] = "R-total (m²K/W)"
                lay["xaxis"]["title_font"] = dict(size=10, color=CT["muted"])
                lay["showlegend"] = False
                lay["bargap"] = 0.28
                fig_rbar.update_layout(**lay)

                st.plotly_chart(fig_rbar, use_container_width=True)

            with colB:
                # Summary stats (publication-friendly)
                r_arr = np.array(r_vals, dtype=float)
                r_min = float(np.min(r_arr))
                r_mean = float(np.mean(r_arr))
                r_max = float(np.max(r_arr))

                metric_card("R-min", f"{r_min:.2f}", "lowest resistance (worst)", CT["fail"])
                metric_card("R-mean", f"{r_mean:.2f}", "average resistance", CT["cyan"])
                metric_card("R-max", f"{r_max:.2f}", "highest resistance (best)", CT["pass"])

                if threshold_r is not None:
                    # % meeting R threshold is same as U pass, but shown explicitly
                    r_pass = sum(1 for (w, res) in unique_r if res.get("passed", False))
                    r_fail = len(unique_r) - r_pass
                    fig_d = go.Figure(go.Pie(
                        labels=["Meets min R", "Below min R"],
                        values=[r_pass, r_fail],
                        hole=0.58,
                        marker=dict(
                            colors=["rgba(52,211,153,0.88)", "rgba(251,113,133,0.38)"],
                            line=dict(color="rgba(255,255,255,0.14)", width=2)
                        ),
                        textinfo="label+percent",
                        textfont=dict(size=11, family=CT["ff"], color=CT["font"])
                    ))
                    fig_d.add_annotation(
                        text=f"<b>{len(unique_r)}</b><br>types",
                        x=0.5, y=0.5, showarrow=False,
                        font=dict(size=13, color=CT["font"], family=CT["ff"])
                    )
                    dl = chlayout("R-threshold Compliance Share", h=260, l=10, r=10, t=38, b=10)
                    dl["showlegend"] = False
                    fig_d.update_layout(**dl)
                    st.plotly_chart(fig_d, use_container_width=True)

            # Optional: export table
            st.markdown('<div class="section-title">R-VALUE TABLE (EXPORT)</div>', unsafe_allow_html=True)

            rows = []
            for wall, res in unique_r:
                u = float(wall["u_value"])
                rtot = 1.0 / u if u > 0 else None
                rows.append({
                    "Wall Assembly Type": wall["name"],
                    "U (W/m²K)": round(u, 4),
                    "R-total (m²K/W)": round(rtot, 4) if rtot is not None else None,
                    "Min R for Code (m²K/W)": round(threshold_r, 4) if threshold_r is not None else None,
                    "Compliance": "PASS" if res.get("passed", False) else "FAIL"
                })

            df_r = pd.DataFrame(rows)
            st.dataframe(df_r, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Export R-Value CSV",
                               df_r.to_csv(index=False),
                               "r_value_analysis.csv",
                               "text/csv")
# ══════════════════════════════════════════════════
# TAB 3 — FACADE MAP
# ══════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-title">03 — FACADE PERFORMANCE MAP</div>',
                unsafe_allow_html=True)

    orientations = ["North","South","East","West"]
    icons = {"North":"⬆️","South":"⬇️","East":"➡️","West":"⬅️"}
    facade_data = {}
    for ori in orientations:
        ow = [w for w in walls if w["orientation"]==ori and w["u_value"]]
        if ow:
            total_area = sum(w["area_m2"] for w in ow) or 1
            weighted_u = sum(w["u_value"]*w["area_m2"] for w in ow) / total_area
            facade_data[ori] = {"avg_u":round(weighted_u,3),"count":len(ow),"area":round(total_area,1)}
        else:
            facade_data[ori] = {"avg_u":None,"count":0,"area":0}

    valid_f = {k:v for k,v in facade_data.items() if v["avg_u"] is not None}
    col_r, col_b = st.columns(2)

    with col_r:
        if len(valid_f) >= 3:
            cats = list(valid_f.keys())
            vals = [valid_f[c]["avg_u"] for c in cats]
            cats_c = cats+[cats[0]]; vals_c = vals+[vals[0]]
            lim = [code["wall_u_max"]]*len(cats_c)
            fig_r = go.Figure()
            fig_r.add_trace(go.Scatterpolar(r=vals_c,theta=cats_c,fill="toself",
                fillcolor="rgba(124,58,237,0.14)",
                line=dict(color=CT["cyan"],width=2),name="U-values"))
            fig_r.add_trace(go.Scatterpolar(r=lim,theta=cats_c,
                line=dict(color=CT["warn"],width=2,dash="dash"),
                name=f"Limit ({code['wall_u_max']})"))
            fig_r.update_layout(
                polar=dict(radialaxis=dict(visible=True,color=CT["muted"],gridcolor=CT["grid"]),
                           angularaxis=dict(color=CT["font"]),bgcolor="rgba(0,0,0,0)"),
                paper_bgcolor=CT["paper"],font=dict(color=CT["font"],family=CT["ff"]),
                height=380,showlegend=True,
                legend=dict(font=dict(size=10,color=CT["muted"])),
                title=dict(text="Area-Weighted U-Value by Facade",
                           font=dict(size=12,color=CT["muted"],family=CT["ff"])),
                margin=dict(l=20,r=20,t=48,b=20)
            )
            st.plotly_chart(fig_r, use_container_width=True)
        else:
            st.info("Need ≥3 facade orientations for radar chart. Check wall orientations in Revit.")

    with col_b:
        if valid_f:
            fn = list(valid_f.keys())
            fu = [valid_f[f]["avg_u"] for f in fn]
            fc = [CT["pass"] if u<=code["wall_u_max"] else CT["fail"] for u in fu]
            fig_fb = go.Figure()
            fig_fb.add_trace(go.Bar(x=fn,y=fu,marker_color=fc,
                text=[f"{u:.3f}" for u in fu],textposition="outside",
                textfont=dict(family=CT["ff"],size=11,color=CT["font"])))
            fig_fb.add_hline(y=code["wall_u_max"],line_dash="dash",
                line_color=CT["warn"],line_width=2,
                annotation_text=f"Limit: {code['wall_u_max']}",
                annotation_font=dict(color=CT["warn"],size=10,family=CT["ff"]))
            lf = chlayout("Average U-Value per Facade",h=380)
            lf["yaxis"]["title"] = "U-Value (W/m²K)"
            lf["showlegend"] = False
            fig_fb.update_layout(**lf)
            st.plotly_chart(fig_fb, use_container_width=True)

    st.markdown('<div class="section-title">FACADE BREAKDOWN</div>', unsafe_allow_html=True)
    fc_cols = st.columns(4)
    for i, ori in enumerate(orientations):
        with fc_cols[i]:
            fd = facade_data[ori]
            if fd["avg_u"] is not None:
                passed = fd["avg_u"] <= code["wall_u_max"]
                col = CT["pass"] if passed else CT["fail"]
                bc  = "badge-pass" if passed else "badge-fail"
                st.markdown(f"""
                <div class="metric-card">
                  <div class="metric-label">{icons[ori]} {ori} Facade</div>
                  <div class="metric-value" style="color:{col};">{fd['avg_u']}</div>
                  <div class="metric-sub">W/m²K · {fd['count']} wall(s) · {fd['area']} m²</div>
                  <div style="margin-top:.7rem;">
                    <span class="{bc}">{'PASS' if passed else 'FAIL'}</span>
                  </div>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="metric-card">
                  <div class="metric-label">{icons[ori]} {ori} Facade</div>
                  <div class="metric-value" style="color:{CT['muted']};">—</div>
                  <div class="metric-sub">No orientation data</div>
                </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════
# TAB 4 — GLAZING
# ══════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-title">04 — WINDOW & GLAZING PERFORMANCE</div>',
                unsafe_allow_html=True)

    if not windows:
        st.info("No window elements found. Ensure windows are modelled and exported in Revit.")
    else:
        st.markdown("**Window-to-Wall Ratio (WWR) by Facade**")
        wwr_cols = st.columns(4)
        wwr_limit = code["wwr_max_pct"]
        for i, ori in enumerate(orientations):
            with wwr_cols[i]:
                ori_win_area  = sum(w.get("area_m2",0) for w in windows
                                    if w["orientation"]==ori and w.get("area_m2"))
                ori_wall_area = sum(w["area_m2"] for w in walls if w["orientation"]==ori)
                if ori_wall_area > 0:
                    wwr_val = round(ori_win_area/ori_wall_area*100, 1)
                    passed  = wwr_val <= wwr_limit
                    col     = CT["pass"] if passed else CT["fail"]
                    fig_g   = go.Figure(go.Indicator(
                        mode="gauge+number", value=wwr_val,
                        number=dict(suffix="%",font=dict(size=20,family="JetBrains Mono",color=col)),
                        title=dict(text=ori,font=dict(size=11,color=CT["muted"],family="JetBrains Mono")),
                        gauge=dict(
                            axis=dict(range=[0,100],tickfont=dict(size=9)),
                            bar=dict(color=col),
                            bgcolor="rgba(255,255,255,0.04)",
                            bordercolor="rgba(255,255,255,0.12)",
                            steps=[dict(range=[0,wwr_limit],color="rgba(52,211,153,0.10)"),
                                   dict(range=[wwr_limit,100],color="rgba(251,113,133,0.08)")],
                            threshold=dict(line=dict(color=CT["warn"],width=3),
                                           thickness=0.8,value=wwr_limit)
                        )
                    ))
                    fig_g.update_layout(paper_bgcolor=CT["paper"],
                                        font=dict(color=CT["font"],family=CT["ff"]),
                                        height=200,margin=dict(l=20,r=20,t=28,b=10))
                    st.plotly_chart(fig_g, use_container_width=True)
                else:
                    st.markdown(f"""<div class="metric-card" style="text-align:center;">
                    <div class="metric-label">{ori}</div>
                    <div style="color:{CT['muted']};font-size:.80rem;padding:1rem;">
                    No wall area data</div></div>""", unsafe_allow_html=True)

        st.markdown('<div class="section-title">WINDOW THERMAL PROPERTIES</div>',
                    unsafe_allow_html=True)
        win_rows = []
        for w in windows:
            u,shgc,area = w.get("u_value"),w.get("shgc"),w.get("area_m2")
            comp = check_window_compliance(u,shgc,code)
            win_rows.append({
                "Window":w["name"],"Orientation":w["orientation"],
                "Area (m²)":f"{area:.2f}" if area else "—",
                "U-Value":f"{u:.2f}" if u else "⚠️ Not in IFC",
                "SHGC":f"{shgc:.2f}" if shgc else "⚠️ Not in IFC",
                "U Status":comp["status"] if u else "⚠️ NO DATA",
                "SHGC Status":("✅ PASS" if shgc and shgc<=code["shgc_max"]
                               else ("❌ FAIL" if shgc else "⚠️ NO DATA"))
            })
        if win_rows:
            st.dataframe(pd.DataFrame(win_rows), use_container_width=True, hide_index=True)
        st.markdown("""
        <div class="info-box">
        💡 Window U-values & SHGC are read from IFC <code>Pset_WindowCommon</code>:
        <code>ThermalTransmittance</code> and <code>SolarHeatGainCoefficient</code>.<br>
        Add in Revit: select window type → Edit Type → add as shared parameters.
        </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════
# TAB 5 — SCENARIOS
# ══════════════════════════════════════════════════
with tab5:
    st.markdown('<div class="section-title">05 — INSULATION IMPROVEMENT SCENARIOS</div>',
                unsafe_allow_html=True)

    recommendations = generate_insulation_recommendations(walls, code)

    if not recommendations:
        st.success("🎉 All wall assemblies comply. No insulation upgrades required.")
    else:
        st.markdown(f"""
        <div class="info-box">
        🔧 <b>{len(recommendations)} unique assembly type(s)</b> require upgrades to meet
        {selected_code_name}.<br>
        Minimum insulation thickness derived from R-value deficit (ISO 6946). Rounded to nearest 5 mm.
        </div>""", unsafe_allow_html=True)

        for rec in recommendations:
            with st.expander(
                f"🧱 {rec['wall_name']}  ·  "
                f"Current U: {rec['current_u']} → Target: {rec['target_u']} W/m²K  ·  "
                f"R-deficit: {rec['r_deficit']} m²K/W"
            ):
                ci, co = st.columns([1,3])
                with ci:
                    pct_gap = round(rec['r_deficit']/((1/rec['target_u'])-0.17)*100,1)
                    st.markdown(f"""
                    <div style="padding:.85rem;border-radius:12px;
                      background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.10);">
                      <div class="metric-label">R-Value Deficit</div>
                      <div style="font-size:1.4rem;font-family:'JetBrains Mono',monospace;
                        font-weight:900;color:{CT['warn']};">{rec['r_deficit']}</div>
                      <div style="font-size:.70rem;color:{CT['muted']};">m²K/W needed</div>
                      <div style="margin-top:.6rem;font-size:.75rem;color:{CT['muted']};">
                        Thermal gap: {pct_gap}%</div>
                    </div>""", unsafe_allow_html=True)
                with co:
                    opt_rows = [{
                        "Insulation": o["insulation"],
                        "λ (W/mK)": o["lambda"],
                        "Min. Thickness": f"{o['thickness_mm']} mm",
                        "New U-Value": f"{o['new_u_value']} W/m²K",
                        "Improvement": f"−{o['u_improvement']} W/m²K",
                        "Cost Index": o["cost_index"],
                        "Compliance": "✅ PASS"
                    } for o in rec["options"]]
                    st.dataframe(pd.DataFrame(opt_rows), use_container_width=True, hide_index=True)

        # Waterfall
        failing = [(w,r) for w,r in wall_results if not r["passed"]]
        if failing:
            st.markdown('<div class="section-title">COMPLIANCE IMPROVEMENT PATHWAY</div>',
                        unsafe_allow_html=True)
            sorted_fail = sorted(failing, key=lambda x: x[0]["u_value"], reverse=True)
            wf_x  = ["Worst Failing Assembly"]
            wf_m  = ["absolute"]
            wf_v  = [sorted_fail[0][0]["u_value"]]
            seen_wf = set()
            for wall, _ in sorted_fail:
                if wall["name"] in seen_wf:
                    continue
                seen_wf.add(wall["name"])
                rm = next((r for r in recommendations if r["wall_name"]==wall["name"]), None)
                if rm and rm["options"]:
                    best = min(rm["options"], key=lambda x: x["new_u_value"])
                    wf_x.append(f"Fix: {wall['name'][:24]}")
                    wf_m.append("relative")
                    wf_v.append(round(-(wall["u_value"]-best["new_u_value"]),3))
            wf_x.append("After All Fixes"); wf_m.append("total"); wf_v.append(0)

            fig_wf = go.Figure(go.Waterfall(
                orientation="v", measure=wf_m, x=wf_x, y=wf_v,
                connector=dict(line=dict(color=CT["grid"],width=1.5)),
                increasing=dict(marker=dict(color=CT["fail"])),
                decreasing=dict(marker=dict(color=CT["pass"])),
                totals=dict(marker=dict(color=CT["cyan"])),
                text=[f"{v:+.3f}" if m=="relative" else f"{v:.3f}"
                      for v,m in zip(wf_v,wf_m)],
                textposition="outside",
                textfont=dict(family=CT["ff"],size=10,color=CT["font"])
            ))
            fig_wf.add_hline(y=code["wall_u_max"],line_dash="dash",
                             line_color=CT["warn"],line_width=1.5,
                             annotation_text=f"Code Limit: {code['wall_u_max']}",
                             annotation_font=dict(color=CT["warn"],size=10,family=CT["ff"]))
            wl = chlayout("Cumulative U-Value Improvement Pathway",h=400)
            wl["yaxis"]["title"] = "U-Value (W/m²K)"
            fig_wf.update_layout(**wl)
            st.plotly_chart(fig_wf, use_container_width=True)



# ==========================================================
# TAB 6 — FABRIC HEAT LOSS ESTIMATION
# ==========================================================
with tab6:

    st.markdown(
        '<div class="section-title">05 — FABRIC HEAT LOSS ESTIMATION</div>',
        unsafe_allow_html=True
    )

    climate = CLIMATE_DATA[selected_code_name]

    hl  = calculate_fabric_heat_loss(walls, roofs, windows, climate)
    chl = calculate_code_compliant_heat_loss(walls, roofs, windows, code, climate)

    show_heat = climate.get("delta_T_heating", 0) > 0
    show_cool = climate.get("delta_T_cooling", 0) > 0

    # ------------------------------------------------------
    # Decide mode (heating preferred)
    # ------------------------------------------------------
    if show_heat:
        mode = "heating"
        key_q = "q_heating_W"
        total_W = hl.get("total_heat_W", 0)
        wall_W  = hl.get("total_wall_heat", 0)
        roof_W  = hl.get("total_roof_heat", 0)
        win_W   = hl.get("total_win_heat", 0)
        compliant_total_W = chl.get("compliant_total_heat", 0)
    else:
        mode = "cooling"
        key_q = "q_cooling_W"
        total_W = hl.get("total_cool_W", 0)
        wall_W  = hl.get("total_wall_cool", 0)
        roof_W  = hl.get("total_roof_cool", 0)
        win_W   = hl.get("total_win_cool", 0)
        compliant_total_W = chl.get("compliant_total_cool", 0)

    # ======================================================
    # KPI ROW
    # ======================================================
    k1, k2, k3 = st.columns(3)

    with k1:
        metric_card("Total Envelope Area",
                    f"{hl.get('total_env_area',0):.0f} m²",
                    "walls + roofs")

    with k2:
        metric_card(f"Peak {mode.capitalize()}",
                    f"{total_W/1000:.2f} kW",
                    f"ΔT = {climate.get('delta_T_'+mode,0):.1f}K",
                    CT["warn"])

    with k3:
        if compliant_total_W:
            diff = total_W - compliant_total_W
            metric_card("Potential Saving",
                        f"{diff/1000:.2f} kW",
                        "if fully code-compliant",
                        CT["cyan"])
        else:
            metric_card("Code Scenario",
                        "—",
                        "No compliant baseline",
                        CT["muted"])

    st.markdown("<br>", unsafe_allow_html=True)

    # ======================================================
    # MAIN CHART ROW
    # ======================================================
    col_left, col_right = st.columns([3,2])

    # ------------------------------------------------------
    # LEFT — HEAT LOSS BY WALL ASSEMBLY
    # ------------------------------------------------------
    with col_left:

        st.markdown(
            '<div class="section-title">HEAT LOSS BY WALL ASSEMBLY</div>',
            unsafe_allow_html=True
        )

        wall_loss_list = hl.get("wall_loss", [])

        if wall_loss_list:

            sorted_hl = sorted(
                wall_loss_list,
                key=lambda x: x.get(key_q, 0),
                reverse=True
            )

            names = [x["name"][:40] for x in sorted_hl]
            values = [x.get(key_q,0) for x in sorted_hl]

            # 🔥 FIXED HEIGHT (NO SCROLL EXPLOSION)
            chart_height = 500

            fig = go.Figure()

            fig.add_trace(go.Bar(
                y=names,
                x=values,
                orientation="h",
                marker_color=CT["fail"],
                text=[f"{v/1000:.1f} kW" for v in values],
                textposition="outside"
            ))

            layout = chlayout(
                f"Wall Assembly {mode.capitalize()} (W)",
                h=chart_height,
                l=5, r=60, t=40, b=20
            )

            layout["xaxis"]["title"] = f"{mode.capitalize()} (W)"
            layout["bargap"] = 0.25

            fig.update_layout(**layout)

            st.plotly_chart(fig, use_container_width=True)

        else:
            st.info("No wall data available.")

    # ------------------------------------------------------
    # RIGHT — LOSS BREAKDOWN + ACTUAL VS CODE
    # ------------------------------------------------------
    with col_right:

        # LOSS BREAKDOWN
        st.markdown(
            '<div class="section-title">LOSS BREAKDOWN</div>',
            unsafe_allow_html=True
        )

        labels = []
        values = []
        colors = []

        if wall_W > 0:
            labels.append("Walls")
            values.append(wall_W)
            colors.append("rgba(251,113,133,0.8)")

        if roof_W > 0:
            labels.append("Roofs")
            values.append(roof_W)
            colors.append("rgba(124,58,237,0.8)")

        if win_W > 0:
            labels.append("Windows")
            values.append(win_W)
            colors.append("rgba(34,211,238,0.8)")

        if values:

            fig_pie = go.Figure(go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker=dict(colors=colors),
                textinfo="label+percent"
            ))

            layout_pie = chlayout(
                "Peak Contribution Share",
                h=260, l=10, r=10, t=40, b=10
            )

            fig_pie.update_layout(**layout_pie)

            st.plotly_chart(fig_pie, use_container_width=True)

        else:
            st.info("Breakdown not available.")

        # ACTUAL VS CODE
        st.markdown(
            '<div class="section-title">ACTUAL vs. CODE-COMPLIANT</div>',
            unsafe_allow_html=True
        )

        categories = ["Walls","Roofs","Windows","TOTAL"]
        actual_vals = [wall_W, roof_W, win_W, total_W]

        compliant_vals = [
            chl.get("compliant_wall_heat",0),
            chl.get("compliant_roof_heat",0),
            chl.get("compliant_win_heat",0),
            compliant_total_W
        ]

        fig_comp = go.Figure()

        fig_comp.add_trace(go.Bar(
            x=categories,
            y=actual_vals,
            name="Actual",
            marker_color=CT["fail"]
        ))

        fig_comp.add_trace(go.Bar(
            x=categories,
            y=compliant_vals,
            name="If Code-Compliant",
            marker_color="rgba(52,211,153,0.7)"
        ))

        layout_comp = chlayout(
            f"Actual vs Code-Compliant ({mode.capitalize()})",
            h=260, l=20, r=20, t=40, b=20
        )

        layout_comp["barmode"] = "group"

        fig_comp.update_layout(**layout_comp)

        st.plotly_chart(fig_comp, use_container_width=True)

# ══════════════════════════════════════════════════
# TAB 7 — VALIDATION (Research Core)
# ══════════════════════════════════════════════════
# ══════════════════════════════════════════════════
# TAB 7 — VALIDATION (Research Core)
# ══════════════════════════════════════════════════
with tab7:
    st.markdown('<div class="section-title">06 — VALIDATION PANEL (RESEARCH EVIDENCE)</div>',
                unsafe_allow_html=True)

    st.markdown("""
    <div class="info-box">
    🔬 <b>Research Validation Protocol (ISO 6946):</b><br>
    1. Manually calculate U-value for each assembly in a spreadsheet using ISO 6946.<br>
    2. Enter your manual values below as independent ground truth.<br>
    3. Dashboard auto-computes MAPE, RMSE, R² — publication-ready metrics.<br>
    <span style="font-size:.78rem;color:rgba(255,255,255,0.52);">
    Expected: MAPE ≈ 0% (same deterministic formula applied to same inputs).
    Non-zero error reveals IFC extraction uncertainty — report this transparently.</span>
    </div>""", unsafe_allow_html=True)

    if not wall_results:
        st.warning("No wall data available.")
    else:
        # Input grid
        unique_results = []
        seen_val = set()
        for wall, result in wall_results:
            if wall["name"] not in seen_val:
                seen_val.add(wall["name"])
                unique_results.append((wall, result))

        st.markdown(f"**Enter Manual ISO 6946 U-values — {len(unique_results)} unique assembly type(s)**")
        st.markdown("*Default values shown are the tool's output. Change them to your independent calculations.*")

        val_pairs, val_rows = [], []
        n_cols = min(3, len(unique_results))
        cols_v = st.columns(n_cols)

        for idx, (wall, result) in enumerate(unique_results):
            with cols_v[idx % n_cols]:
                manual = st.number_input(
                    f"{wall['name'][:30]}",
                    min_value=0.001, max_value=15.0,
                    value=float(wall["u_value"]),
                    step=0.001, format="%.4f",
                    key=f"v_{wall['id']}",
                    help=f"Tool calculated: {wall['u_value']} W/m²K"
                )
            tool_val = wall["u_value"]
            diff = abs(tool_val - manual)
            pct  = round(diff/manual*100, 4) if manual > 0 else 0
            val_pairs.append({"manual":manual,"tool":tool_val})
            val_rows.append({
                "Wall Assembly": wall["name"],
                "Manual (W/m²K)": round(manual,4),
                "Tool (W/m²K)": tool_val,
                "Abs. Diff": round(diff,6),
                "% Error": f"{pct:.4f}%",
                "Agreement": ("✅ Excellent" if pct<0.5 else
                              "✅ Good" if pct<2.0 else
                              "⚠️ Review" if pct<5.0 else "❌ Check")
            })

        st.markdown('<div class="section-title">COMPARISON TABLE</div>', unsafe_allow_html=True)
        df_val = pd.DataFrame(val_rows)
        st.dataframe(df_val, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Export Validation CSV",
                           df_val.to_csv(index=False),
                           "validation_results.csv", "text/csv")

        # Statistical metrics — always compute and show
        stats = compute_validation_stats(val_pairs)
        if stats and "mape" in stats:
            st.markdown('<div class="section-title">STATISTICAL METRICS — FOR PAPER TABLE</div>',
                        unsafe_allow_html=True)
            sv1,sv2,sv3,sv4,sv5 = st.columns(5)
            with sv1:
                metric_card("MAPE", f"{stats['mape']:.4f}%", "Mean Abs % Error",
                            CT["pass"] if stats["mape"]<2 else CT["warn"])
            with sv2:
                metric_card("RMSE", f"{stats['rmse']:.6f}", "Root Mean Sq Error",
                            CT["pass"] if stats["rmse"]<0.01 else CT["warn"])
            with sv3:
                metric_card("Max Error", f"{stats['max_error_pct']:.4f}%", "Worst deviation",
                            CT["pass"] if stats["max_error_pct"]<2 else CT["warn"])
            with sv4:
                metric_card("R²", f"{stats['r_squared']:.6f}", "Coefficient of det.",
                            CT["pass"] if stats["r_squared"]>0.99 else CT["warn"])
            with sv5:
                verdict = "VALIDATED ✅" if stats["validated"] else "REVIEW ⚠️"
                metric_card("Verdict", verdict, f"n = {stats['n']} types",
                            CT["pass"] if stats["validated"] else CT["warn"])

            # Scatter — manual vs tool
            all_m = [p["manual"] for p in val_pairs]
            all_t = [p["tool"] for p in val_pairs]
            names_l = [r["Wall Assembly"][:22] for r in val_rows]

            fig_sc = go.Figure()
            mn,mx = min(all_m+all_t)*0.88, max(all_m+all_t)*1.10
            fig_sc.add_trace(go.Scatter(
                x=[mn,mx],y=[mn,mx],mode="lines",
                line=dict(color=CT["warn"],dash="dash",width=1.5),
                name="Perfect agreement (1:1)"
            ))
            fig_sc.add_trace(go.Scatter(
                x=all_m,y=all_t,mode="markers+text",
                marker=dict(color=CT["cyan"],size=11,opacity=0.88,
                            line=dict(color="rgba(255,255,255,0.22)",width=1)),
                text=names_l,textposition="top center",
                textfont=dict(size=8,color=CT["muted"]),
                name="Wall assemblies",
                hovertemplate="<b>%{text}</b><br>Manual:%{x:.4f}<br>Tool:%{y:.4f}<extra></extra>"
            ))
            sc_lay = chlayout(
                f"Manual Calculation vs. Tool Output — R² = {stats['r_squared']:.6f}",
                h=380, l=55, r=20, t=48, b=30
            )
            sc_lay["xaxis"]["title"] = "Manual Calculation (W/m²K)"
            sc_lay["yaxis"]["title"] = "Tool Output (W/m²K)"
            sc_lay["xaxis"]["title_font"] = dict(size=10,color=CT["muted"])
            sc_lay["yaxis"]["title_font"] = dict(size=10,color=CT["muted"])
            sc_lay["showlegend"] = True
            sc_lay["legend"] = dict(font=dict(size=10,color=CT["muted"]))
            fig_sc.update_layout(**sc_lay)
            st.plotly_chart(fig_sc, use_container_width=True)

            # Research statement
            st.markdown(f"""
            <div class="info-box">
            📄 <b>Research statement:</b><br>
            "The automated IFC-to-U-value pipeline was validated against independent manual ISO 6946
            calculations across <b>{stats['n']}</b> unique wall assembly types extracted from the
            case study IFC file. The framework achieved a Mean Absolute Percentage Error (MAPE) of
            <b>{stats['mape']:.4f}%</b>, Root Mean Square Error (RMSE) of
            <b>{stats['rmse']:.6f} W/m²K</b>, and a coefficient of determination
            R² = <b>{stats['r_squared']:.6f}</b>, confirming the mathematical accuracy and
            reproducibility of the proposed automated extraction and calculation framework."
            </div>""", unsafe_allow_html=True)

    # ======================================================
    # B) FABRIC LOAD VALIDATION (UAΔT — steady-state conductive)
    # ======================================================
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">07 — FABRIC LOAD VALIDATION (UAΔT)</div>',
                unsafe_allow_html=True)

    st.markdown(f"""
    <div class="info-box">
    🌡️ <b>Fabric Load Validation (Steady-State Conductive):</b><br>
    The dashboard estimates peak envelope load using <code>Q = Σ(U · A · ΔT)</code> (fabric conduction only).<br>
    This validation compares tool outputs against independent spreadsheet calculations using the same extracted
    U-values, areas, and the code-defined ΔT.<br>
    <span style="font-size:.78rem;color:rgba(255,255,255,0.52);">
    Note: This is not a full HVAC load simulation (solar gains, infiltration, internal gains, and dynamics are excluded).
    </span>
    </div>
    """, unsafe_allow_html=True)

    # Recompute loads here to avoid dependence on Tab 6 execution
    climate = CLIMATE_DATA.get(selected_code_name, {})
    delta_heat = float(climate.get("delta_T_heating", 0) or 0)
    delta_cool = float(climate.get("delta_T_cooling", 0) or 0)

    # Prefer heating if available, else cooling
    if delta_heat > 0:
        mode_v = "heating"
        deltaT = delta_heat
        key_q = "q_heating_W"
    else:
        mode_v = "cooling"
        deltaT = delta_cool
        key_q = "q_cooling_W"

    hl_v = calculate_fabric_heat_loss(walls, roofs, windows, climate)

    if mode_v == "heating":
        tool_total = float(hl_v.get("total_heat_W", 0) or 0)
        tool_walls = float(hl_v.get("total_wall_heat", 0) or 0)
        tool_roofs = float(hl_v.get("total_roof_heat", 0) or 0)
        tool_wins  = float(hl_v.get("total_win_heat", 0) or 0)
    else:
        tool_total = float(hl_v.get("total_cool_W", 0) or 0)
        tool_walls = float(hl_v.get("total_wall_cool", 0) or 0)
        tool_roofs = float(hl_v.get("total_roof_cool", 0) or 0)
        tool_wins  = float(hl_v.get("total_win_cool", 0) or 0)

    st.markdown(f"**Mode:** {mode_v.capitalize()} &nbsp;·&nbsp; ΔT = {deltaT:.1f} K")
    st.markdown("**Enter your manual spreadsheet results (W).**")

    lf1, lf2, lf3, lf4 = st.columns(4)
    with lf1:
        man_walls = st.number_input("Manual Walls (W)", min_value=0.0, value=float(tool_walls), step=10.0,
                                    key="man_walls_q")
    with lf2:
        man_roofs = st.number_input("Manual Roofs (W)", min_value=0.0, value=float(tool_roofs), step=10.0,
                                    key="man_roofs_q")
    with lf3:
        man_wins = st.number_input("Manual Windows (W)", min_value=0.0, value=float(tool_wins), step=10.0,
                                   key="man_wins_q")
    with lf4:
        man_total = st.number_input("Manual TOTAL (W)", min_value=0.0, value=float(tool_total), step=10.0,
                                    key="man_total_q")

    load_pairs = [
        {"name": "Walls", "manual": float(man_walls), "tool": float(tool_walls)},
        {"name": "Roofs", "manual": float(man_roofs), "tool": float(tool_roofs)},
        {"name": "Windows", "manual": float(man_wins), "tool": float(tool_wins)},
        {"name": "TOTAL", "manual": float(man_total), "tool": float(tool_total)},
    ]

    # Build table
    load_rows = []
    for p in load_pairs:
        m, t = p["manual"], p["tool"]
        diff = abs(t - m)
        pct  = (diff / m * 100) if m > 0 else 0.0
        load_rows.append({
            "Component": p["name"],
            "Manual (W)": round(m, 2),
            "Tool (W)": round(t, 2),
            "Abs. Diff (W)": round(diff, 4),
            "% Error": f"{pct:.4f}%",
            "Agreement": ("✅ Excellent" if pct < 0.5 else
                          "✅ Good" if pct < 2.0 else
                          "⚠️ Review" if pct < 5.0 else "❌ Check")
        })

    st.markdown('<div class="section-title">FABRIC LOAD COMPARISON TABLE</div>', unsafe_allow_html=True)
    df_load = pd.DataFrame(load_rows)
    st.dataframe(df_load, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Export Fabric Load Validation CSV",
                       df_load.to_csv(index=False),
                       f"fabric_load_validation_{mode_v}.csv", "text/csv")

    # Compute metrics using existing stats function
    load_stats = compute_validation_stats([{"manual": p["manual"], "tool": p["tool"]} for p in load_pairs])

    if load_stats and "mape" in load_stats:
        st.markdown('<div class="section-title">FABRIC LOAD METRICS — FOR PAPER TABLE</div>',
                    unsafe_allow_html=True)
        q1, q2, q3, q4, q5 = st.columns(5)
        with q1:
            metric_card("MAPE", f"{load_stats['mape']:.4f}%", "Mean Abs % Error",
                        CT["pass"] if load_stats["mape"] < 2 else CT["warn"])
        with q2:
            metric_card("RMSE", f"{load_stats['rmse']:.3f}", "W (Root Mean Sq Error)",
                        CT["pass"] if load_stats["rmse"] < 50 else CT["warn"])
        with q3:
            metric_card("Max Error", f"{load_stats['max_error_pct']:.4f}%", "Worst deviation",
                        CT["pass"] if load_stats["max_error_pct"] < 2 else CT["warn"])
        with q4:
            metric_card("R²", f"{load_stats['r_squared']:.6f}", "Coefficient of det.",
                        CT["pass"] if load_stats["r_squared"] > 0.99 else CT["warn"])
        with q5:
            verdict2 = "VALIDATED ✅" if load_stats["validated"] else "REVIEW ⚠️"
            metric_card("Verdict", verdict2, f"n = {load_stats['n']} comps",
                        CT["pass"] if load_stats["validated"] else CT["warn"])

        # Scatter — manual vs tool (Loads)
        xm = [p["manual"] for p in load_pairs]
        yt = [p["tool"] for p in load_pairs]
        lbl = [p["name"] for p in load_pairs]

        fig_q = go.Figure()
        mn2, mx2 = min(xm + yt) * 0.90, max(xm + yt) * 1.10
        fig_q.add_trace(go.Scatter(
            x=[mn2, mx2], y=[mn2, mx2], mode="lines",
            line=dict(color=CT["warn"], dash="dash", width=1.5),
            name="Perfect agreement (1:1)"
        ))
        fig_q.add_trace(go.Scatter(
            x=xm, y=yt, mode="markers+text",
            marker=dict(color=CT["cyan"], size=12, opacity=0.90,
                        line=dict(color="rgba(255,255,255,0.22)", width=1)),
            text=lbl, textposition="top center",
            textfont=dict(size=10, color=CT["muted"]),
            name="Components",
            hovertemplate="<b>%{text}</b><br>Manual:%{x:.1f} W<br>Tool:%{y:.1f} W<extra></extra>"
        ))

        q_lay = chlayout(
            f"Manual vs Tool — Fabric {mode_v.capitalize()} Load (R² = {load_stats['r_squared']:.6f})",
            h=360, l=55, r=20, t=48, b=30
        )
        q_lay["xaxis"]["title"] = f"Manual {mode_v.capitalize()} Load (W)"
        q_lay["yaxis"]["title"] = f"Tool {mode_v.capitalize()} Load (W)"
        q_lay["xaxis"]["title_font"] = dict(size=10, color=CT["muted"])
        q_lay["yaxis"]["title_font"] = dict(size=10, color=CT["muted"])
        q_lay["showlegend"] = True
        q_lay["legend"] = dict(font=dict(size=10, color=CT["muted"]))
        fig_q.update_layout(**q_lay)
        st.plotly_chart(fig_q, use_container_width=True)

        st.markdown(f"""
        <div class="info-box">
        📄 <b>Research statement (fabric load):</b><br>
        "The envelope fabric load aggregation (<code>Σ(U·A·ΔT)</code>) was validated against independent spreadsheet
        calculations at the component level (walls, roofs, windows) and at the total envelope level under the selected
        {selected_code_name} climate (ΔT = <b>{deltaT:.1f} K</b>). The framework achieved MAPE <b>{load_stats['mape']:.4f}%</b>,
        RMSE <b>{load_stats['rmse']:.3f} W</b>, and R² <b>{load_stats['r_squared']:.6f}</b>, confirming computational
        correctness of the steady-state conductive load estimation."
        </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════
# TAB 8 — RAW DATA
# ══════════════════════════════════════════════════
with tab8:
    st.markdown('<div class="section-title">07 — RAW EXTRACTED DATA & TRANSPARENCY REPORT</div>',
                unsafe_allow_html=True)

    # Material confidence — research transparency
    st.markdown(f"""
    <div class="info-box">
    <b>Material Matching Transparency — {conf['total_layers']} layers parsed</b><br>
    🟢 High confidence (exact/partial match): <b>{conf['high']} layers ({conf['high_pct']}%)</b><br>
    🟡 Medium confidence (keyword match):&nbsp; <b>{conf['medium']} layers ({conf['medium_pct']}%)</b><br>
    🔴 Low confidence (default λ=0.50 used):&nbsp; <b>{conf['low']} layers ({conf['low_pct']}%)</b><br>
    <span style="font-size:.76rem;color:rgba(255,255,255,0.48);">
    Report this breakdown in your paper's methodology/limitation section for transparency.</span>
    </div>""", unsafe_allow_html=True)

    rt1,rt2,rt3 = st.tabs(["Walls","Windows","Roofs"])

    with rt1:
        if walls:
            rows = [{"IFC GlobalId":w["id"],"Wall Name":w["name"],
                     "Orientation":w["orientation"],"Area (m²)":w["area_m2"],
                     "U-Value (W/m²K)":w["u_value"],"Thickness (mm)":w["total_thickness_mm"],
                     "Layers":w["layer_count"],
                     "Compliance":check_wall_compliance(w["u_value"],code)["status"]
                               if w["u_value"] else "—"} for w in walls]
            df_w = pd.DataFrame(rows)
            st.dataframe(df_w, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Download Wall CSV",df_w.to_csv(index=False),"wall_data.csv","text/csv")

    with rt2:
        if windows:
            rows = [{"IFC GlobalId":w["id"],"Window":w["name"],
                     "Orientation":w["orientation"],
                     "Width (m)":w.get("width_m"),"Height (m)":w.get("height_m"),
                     "Area (m²)":w.get("area_m2"),
                     "U-Value":w.get("u_value"),"SHGC":w.get("shgc")} for w in windows]
            df_win = pd.DataFrame(rows)
            st.dataframe(df_win, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Download Window CSV",df_win.to_csv(index=False),"window_data.csv","text/csv")
        else:
            st.info("No window data.")

    with rt3:
        if roofs:
            rows = [{"IFC GlobalId":r["id"],"Roof Name":r["name"],
                     "U-Value (W/m²K)":r["u_value"],"Area (m²)":r["area_m2"],
                     "Layers":r["layer_count"],
                     "Compliance":check_roof_compliance(r["u_value"],code)["status"]
                               if r["u_value"] else "—"} for r in roofs]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No roof elements detected in IFC.")

# ─────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style="text-align:center;font-size:.78rem;color:rgba(255,255,255,0.52);
  font-family:'Manrope',sans-serif;padding:.8rem 0;line-height:1.7;">
  <b style="color:rgba(255,255,255,0.75);">© 2025 Md Obidul Haque</b> ·
  BIM Thermal Envelope Dashboard · ISO 6946 U-value Calculation ·
  Automated IFC Parsing (ifcopenshell) · Research Grade Tool
</div>""", unsafe_allow_html=True)
