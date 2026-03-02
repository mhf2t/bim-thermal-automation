# 🏗️ BIM Thermal Envelope Dashboard
## Complete Step-by-Step Development & Research Guide

---

## 📁 PROJECT FILE STRUCTURE

```
bim_thermal_dashboard/
│
├── app.py                  ← Main Streamlit dashboard (run this)
├── ifc_parser.py           ← IFC parsing + U-value calculation engine
├── compliance.py           ← Code compliance checking logic
├── thermal_database.csv    ← Material thermal conductivity database
├── requirements.txt        ← Python dependencies
└── GUIDE.md                ← This file
```

---

## STEP 1 — INSTALL PYTHON ENVIRONMENT

### 1.1 Install Python
Download Python 3.10 or 3.11 from https://python.org
Make sure to check "Add Python to PATH" during installation.

### 1.2 Create Virtual Environment
Open terminal/command prompt in your project folder:

```bash
# Navigate to your project folder
cd bim_thermal_dashboard

# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate
```

### 1.3 Install Dependencies
```bash
pip install -r requirements.txt
```

⚠️ ifcopenshell installation note:
If `pip install ifcopenshell` fails, use:
```bash
pip install ifcopenshell --find-links https://s3.amazonaws.com/ifcopenshell-builds/
```
Or download from: https://github.com/IfcOpenShell/IfcOpenShell/releases

---

## STEP 2 — MODEL YOUR BUILDING IN REVIT

This is the MOST CRITICAL step. Your IFC is only as good as your Revit model.

### 2.1 Building Requirements for Your Research
Model ONE building with these characteristics:
- 2–3 storeys (complexity enough for research)
- 4–6 DIFFERENT external wall types (this creates meaningful comparison data)
- Windows on all 4 facades
- A roof assembly

### 2.2 Create Multiple Wall Types (Critical)
In Revit: Architecture tab → Wall → Edit Type → Duplicate

Create these 5 wall types intentionally designed to test compliance:

**Wall Type 1: Concrete No Insulation (designed to FAIL)**
- Layer 1: Concrete, 200mm, λ = 0.51
- Expected U: ~1.9 W/m²K → FAILS all codes

**Wall Type 2: Brick Cavity No Insulation (designed to FAIL)**  
- Layer 1: Clay Brick, 102mm, λ = 0.77
- Layer 2: Air Cavity, 50mm, λ = 0.18
- Layer 3: Clay Brick, 102mm, λ = 0.77
- Layer 4: Plasterboard, 12.5mm, λ = 0.25
- Expected U: ~1.1 W/m²K → FAILS most codes

**Wall Type 3: Brick + Mineral Wool (designed to PASS)**
- Layer 1: Clay Brick, 102mm
- Layer 2: Mineral Wool, 75mm, λ = 0.038
- Layer 3: Clay Brick, 100mm
- Layer 4: Plasterboard, 12.5mm
- Expected U: ~0.28 W/m²K → PASSES most codes

**Wall Type 4: Steel Frame + Insulation (designed to PASS)**
- Layer 1: Render, 15mm
- Layer 2: EPS Insulation, 100mm, λ = 0.038
- Layer 3: Plasterboard, 12.5mm
- Expected U: ~0.35 W/m²K → PASSES most codes

**Wall Type 5: Curtain Wall (designed to FAIL badly)**
- Modeled as curtain wall system
- U-value assigned in Type Properties: 2.8 W/m²K → FAILS all codes

### 2.3 Define Material Layers Correctly
This is where most students make mistakes:

1. Select wall type → Edit Type → Edit Structure (in Type Properties)
2. Click each layer row → set Material from dropdown
3. Material names MUST match names in thermal_database.csv
   - Use: "Concrete", "Clay Brick", "Mineral Wool", "EPS", "Plasterboard"
   - NOT: "Concrete - Cast-in-Place" (tool won't match this)
   - OR: Add your material names to thermal_database.csv

### 2.4 Set External/Internal Flag
Select each wall → Properties panel → look for "IsExternal" parameter
Set external walls = Yes/True
This is how the tool filters envelope vs. internal walls.

### 2.5 Set Window Properties
For each window type:
1. Select window → Edit Type → Add parameters
2. Add parameter: "ThermalTransmittance" (Number type) = your U-value
3. Add parameter: "SolarHeatGainCoefficient" (Number type) = your SHGC value
   - Double glazing typical: U=2.8, SHGC=0.39
   - Low-E double: U=1.6, SHGC=0.25
   - Triple glazing: U=0.8, SHGC=0.20

### 2.6 Set True North
Manage tab → Project Information → set True North angle
This allows the tool to determine N/S/E/W facade orientation.

---

## STEP 3 — EXPORT IFC FROM REVIT

### 3.1 Export Settings (Critical)
File → Export → IFC

In the IFC Export dialog:
- IFC Version: **IFC4** (preferred) or IFC2x3
- File Type: IFC
- ✅ Export base quantities (MUST be checked)
- ✅ Export Revit property sets
- ✅ Export IFC common property sets
- Space boundaries: 1st level

### 3.2 Export Setup File
Save your export settings as a setup file so you can re-export consistently.

### 3.3 Verify Your IFC
Open the exported IFC in a free viewer to check:
- **BIMVision** (free): https://bimvision.eu/
- **IFC++ Viewer** (free): online IFC viewer
- Check that walls show material layers in properties

---

## STEP 4 — RUN THE DASHBOARD

### 4.1 Start Streamlit
```bash
# Make sure your virtual environment is active
# Navigate to project folder
cd bim_thermal_dashboard

# Run the dashboard
streamlit run app.py
```

Your browser will automatically open to: http://localhost:8501

### 4.2 Upload Your IFC
- Drag and drop your .ifc file into the upload zone
- Wait 10–30 seconds for parsing (depends on model size)
- Dashboard auto-generates all panels

### 4.3 Select Your Compliance Code
In the left sidebar, choose:
- **MS1525:2019** if your building is in Malaysia
- **ASHRAE 90.1 Zone 1A** for hot humid tropical
- **UK Part L** for temperate European climate

All charts and compliance checks update instantly.

---

## STEP 5 — VALIDATE YOUR RESULTS (Research Evidence)

### 5.1 Manual Calculation Spreadsheet
Before running the tool, calculate U-values manually in Excel using ISO 6946.

ISO 6946 Formula:
```
U = 1 / (Rsi + R1 + R2 + ... + Rn + Rso)

Where:
  Rsi = 0.13 m²K/W (interior surface resistance)
  Rso = 0.04 m²K/W (exterior surface resistance)  
  Rn  = d/λ (thickness in metres / thermal conductivity)
```

Example — Brick Cavity + Mineral Wool wall:
```
Layer             d(m)    λ(W/mK)   R(m²K/W)
Clay Brick outer  0.102   0.77      0.1325
Mineral Wool      0.075   0.038     1.9737
Clay Brick inner  0.100   0.77      0.1299
Plasterboard      0.0125  0.25      0.0500
Rsi                                 0.1300
Rso                                 0.0400
─────────────────────────────────────────────
R_total                             2.4561
U = 1/2.4561 =                      0.407 W/m²K
```

### 5.2 Enter Manual Values in Validation Tab
Go to Tab 5 (Validation) in the dashboard.
Enter your Excel-calculated values.
The tool shows % error between manual and automated calculation.
Expected result: 0.00% error (same formula, same inputs).

### 5.3 Validation Result Table (Copy to Paper)
The validation table in Tab 5 is ready to paste into your journal paper as Table 3 or Table 4.

---

## STEP 6 — TROUBLESHOOTING COMMON ISSUES

### Issue: "No wall U-values could be calculated"
**Cause:** Material layers not defined in Revit wall assemblies
**Fix:** Go to each wall type in Revit → Edit Type → Edit Structure → add materials with thickness

### Issue: "Material matched with LOW confidence"
**Cause:** Material name in Revit doesn't match thermal_database.csv
**Fix:** Either rename materials in Revit to match the CSV, OR add your material name to thermal_database.csv

### Issue: "All orientations show Unknown"
**Cause:** IFC doesn't export local placement correctly
**Fix:** Try IFC2x3 export instead of IFC4, or check your Revit coordinate system

### Issue: "No windows found"
**Cause:** Windows not exported or not classified as IfcWindow
**Fix:** In Revit export settings, ensure all categories are included

### Issue: ifcopenshell import error
**Fix:** 
```bash
pip uninstall ifcopenshell
pip install ifcopenshell==0.7.0
```

---

## STEP 7 — RESEARCH PAPER MAPPING

Every dashboard panel maps directly to your paper:

| Dashboard Panel | Paper Section | Figure/Table Number |
|---|---|---|
| Project Overview Cards | Section 3 - Results | Table 1 - Building Summary |
| U-Value Bar Chart | Section 3.1 | Figure 3 - Compliance Assessment |
| Layer Detail Tables | Section 3.1 | Table 2 - Assembly U-values |
| Facade Radar Chart | Section 3.2 | Figure 4 - Facade Performance |
| WWR Gauges | Section 3.3 | Figure 5 - WWR Analysis |
| Scenario Waterfall | Section 3.4 | Figure 6 - Compliance Pathway |
| Validation Table | Section 4 - Validation | Table 3 - Tool Accuracy |
| Validation Metrics | Section 4 | Table 4 - MAPE Results |

### Screenshot Instructions
1. Use Windows Snipping Tool or Mac Screenshot
2. Capture each chart at full dashboard width
3. Save as PNG at 150dpi minimum for journal submission
4. Plotly charts can also be exported directly: click camera icon top right of each chart

---

## STEP 8 — EXTENDING THE TOOL (Future Work)

These extensions become your paper's "Future Work" section and potential follow-up papers:

**Extension 1:** Real-time Revit integration via Revit API (eliminate IFC export step)

**Extension 2:** Weather file integration for dynamic thermal analysis 

**Extension 3:** Cost estimation — add insulation cost database to calculate ROI of compliance upgrades

**Extension 4:** Cloud deployment on Streamlit Cloud (free) for public access tool

**Extension 5:** Machine learning layer — predict U-value compliance from early-stage design parameters before full wall assembly is defined

---

## QUICK REFERENCE — THERMAL CONDUCTIVITY VALUES

| Material | λ (W/mK) | Common Use |
|---|---|---|
| Normal Concrete | 0.51 | Structural walls/slabs |
| Clay Brick | 0.77 | Masonry walls |
| EPS Insulation | 0.038 | Wall/roof insulation |
| Mineral Wool | 0.038 | Wall/roof insulation |
| XPS Insulation | 0.034 | Below-ground/flat roof |
| PIR Board | 0.022 | High-performance roofs |
| Plasterboard | 0.25 | Interior finish |
| Timber/Softwood | 0.13 | Structural/cladding |
| Glass | 1.00 | Single glazing |
| Air Cavity | 0.18 | Cavity walls |

---

## COMPLIANCE THRESHOLDS QUICK REFERENCE

| Code | Wall U-max | Roof U-max | Window U-max |
|---|---|---|---|
| MS1525:2019 | 0.40 W/m²K | 0.30 W/m²K | 3.00 W/m²K |
| ASHRAE 90.1 Zone 1A | 0.701 W/m²K | 0.273 W/m²K | 3.692 W/m²K |
| UK Part L 2021 | 0.26 W/m²K | 0.18 W/m²K | 1.60 W/m²K |
| Green Star AU | 0.35 W/m²K | 0.25 W/m²K | 2.00 W/m²K |

---

*BIM Thermal Envelope Dashboard — Research Tool*  
*ISO 6946 Calculation · ifcopenshell Parsing · Streamlit Interface*
