# ══════════════════════════════════════════════════
# TAB 7 — VALIDATION (Research Core)
#   - Part A: U-value validation (ISO 6946)
#   - Part B: Fabric load validation (UAΔT)
# ══════════════════════════════════════════════════
with tab7:
    st.markdown(
        '<div class="section-title">06 — VALIDATION PANEL (RESEARCH EVIDENCE)</div>',
        unsafe_allow_html=True
    )

    # ======================================================
    # A) U-VALUE VALIDATION (ISO 6946)
    # ======================================================
    st.markdown(
        """
        <div class="info-box">
        🔬 <b>Research Validation Protocol (ISO 6946 — U-values):</b><br>
        1. Manually calculate U-value for each assembly in a spreadsheet using ISO 6946.<br>
        2. Enter your manual values below as independent ground truth.<br>
        3. Dashboard auto-computes MAPE, RMSE, R² — publication-ready metrics.<br>
        <span style="font-size:.78rem;color:rgba(255,255,255,0.52);">
        Expected: MAPE ≈ 0% (same deterministic formula applied to same inputs).
        Non-zero error reveals IFC extraction uncertainty — report this transparently.</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    if not wall_results:
        st.warning("No wall data available.")
    else:
        # Input grid (unique assembly types)
        unique_results = []
        seen_val = set()
        for wall, result in wall_results:
            if wall.get("name") and wall["name"] not in seen_val:
                seen_val.add(wall["name"])
                unique_results.append((wall, result))

        st.markdown(f"**Enter Manual ISO 6946 U-values — {len(unique_results)} unique assembly type(s)**")
        st.markdown("*Default values shown are the tool's output. Change them to your independent calculations.*")

        val_pairs, val_rows = [], []

        n_cols = min(3, max(1, len(unique_results)))
        cols_v = st.columns(n_cols)

        for idx, (wall, result) in enumerate(unique_results):
            tool_val = float(wall.get("u_value") or 0.0)

            with cols_v[idx % n_cols]:
                manual = st.number_input(
                    f"{wall.get('name','Wall')[:30]}",
                    min_value=0.001,
                    max_value=15.0,
                    value=float(tool_val if tool_val > 0 else 0.001),
                    step=0.001,
                    format="%.4f",
                    key=f"v_{wall.get('id', idx)}",
                    help=f"Tool calculated: {tool_val:.4f} W/m²K"
                )

            diff = abs(tool_val - manual)
            pct = round(diff / manual * 100, 4) if manual > 0 else 0.0

            val_pairs.append({"manual": float(manual), "tool": float(tool_val)})
            val_rows.append({
                "Wall Assembly": wall.get("name", f"Wall_{idx}"),
                "Manual (W/m²K)": round(float(manual), 4),
                "Tool (W/m²K)": round(float(tool_val), 4),
                "Abs. Diff": round(float(diff), 6),
                "% Error": f"{pct:.4f}%",
                "Agreement": (
                    "✅ Excellent" if pct < 0.5 else
                    "✅ Good" if pct < 2.0 else
                    "⚠️ Review" if pct < 5.0 else
                    "❌ Check"
                )
            })

        st.markdown('<div class="section-title">U-VALUE COMPARISON TABLE</div>', unsafe_allow_html=True)
        df_val = pd.DataFrame(val_rows)
        st.dataframe(df_val, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Export U-Value Validation CSV",
            df_val.to_csv(index=False),
            "u_value_validation_results.csv",
            "text/csv"
        )

        # Stats + scatter (guarded)
        try:
            stats = compute_validation_stats(val_pairs)
        except Exception as e:
            stats = None
            st.warning(f"Could not compute U-value validation stats (MAPE/RMSE/R²): {e}")

        if stats and "mape" in stats:
            st.markdown('<div class="section-title">U-VALUE METRICS — FOR PAPER TABLE</div>', unsafe_allow_html=True)

            sv1, sv2, sv3, sv4, sv5 = st.columns(5)
            with sv1:
                metric_card("MAPE", f"{stats['mape']:.4f}%", "Mean Abs % Error",
                            CT["pass"] if stats["mape"] < 2 else CT["warn"])
            with sv2:
                metric_card("RMSE", f"{stats['rmse']:.6f}", "Root Mean Sq Error",
                            CT["pass"] if stats["rmse"] < 0.01 else CT["warn"])
            with sv3:
                metric_card("Max Error", f"{stats['max_error_pct']:.4f}%", "Worst deviation",
                            CT["pass"] if stats["max_error_pct"] < 2 else CT["warn"])
            with sv4:
                metric_card("R²", f"{stats['r_squared']:.6f}", "Coefficient of det.",
                            CT["pass"] if stats["r_squared"] > 0.99 else CT["warn"])
            with sv5:
                verdict = "VALIDATED ✅" if stats.get("validated", False) else "REVIEW ⚠️"
                metric_card("Verdict", verdict, f"n = {stats.get('n', 0)} types",
                            CT["pass"] if stats.get("validated", False) else CT["warn"])

            # Scatter — manual vs tool (U-values)
            try:
                all_m = [p["manual"] for p in val_pairs]
                all_t = [p["tool"] for p in val_pairs]
                names_l = [r["Wall Assembly"][:22] for r in val_rows]

                fig_sc = go.Figure()
                mn = min(all_m + all_t) * 0.88
                mx = max(all_m + all_t) * 1.10

                fig_sc.add_trace(go.Scatter(
                    x=[mn, mx], y=[mn, mx], mode="lines",
                    line=dict(color=CT["warn"], dash="dash", width=1.5),
                    name="Perfect agreement (1:1)"
                ))
                fig_sc.add_trace(go.Scatter(
                    x=all_m, y=all_t, mode="markers+text",
                    marker=dict(color=CT["cyan"], size=11, opacity=0.88,
                                line=dict(color="rgba(255,255,255,0.22)", width=1)),
                    text=names_l, textposition="top center",
                    textfont=dict(size=8, color=CT["muted"]),
                    name="Wall assemblies",
                    hovertemplate="<b>%{text}</b><br>Manual:%{x:.4f}<br>Tool:%{y:.4f}<extra></extra>"
                ))

                sc_lay = chlayout(
                    f"Manual vs Tool — U-Value Validation (R² = {stats['r_squared']:.6f})",
                    h=380, l=55, r=20, t=48, b=30
                )
                sc_lay["xaxis"]["title"] = "Manual Calculation (W/m²K)"
                sc_lay["yaxis"]["title"] = "Tool Output (W/m²K)"
                sc_lay["xaxis"]["title_font"] = dict(size=10, color=CT["muted"])
                sc_lay["yaxis"]["title_font"] = dict(size=10, color=CT["muted"])
                sc_lay["showlegend"] = True
                sc_lay["legend"] = dict(font=dict(size=10, color=CT["muted"]))
                fig_sc.update_layout(**sc_lay)

                st.plotly_chart(fig_sc, use_container_width=True)

            except Exception as e:
                st.warning(f"Could not draw U-value scatter plot: {e}")

            st.markdown(
                f"""
                <div class="info-box">
                📄 <b>Research statement (U-values):</b><br>
                "The automated IFC-to-U-value pipeline was validated against independent manual ISO 6946
                calculations across <b>{stats.get('n', 0)}</b> unique wall assembly types extracted from the case study IFC file.
                The framework achieved MAPE <b>{stats.get('mape',0):.4f}%</b>, RMSE <b>{stats.get('rmse',0):.6f} W/m²K</b>,
                and R² <b>{stats.get('r_squared',0):.6f}</b>, confirming mathematical accuracy and reproducibility."
                </div>
                """,
                unsafe_allow_html=True
            )

    # ======================================================
    # B) FABRIC LOAD VALIDATION (UAΔT — steady-state conductive)
    # ======================================================
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">07 — FABRIC LOAD VALIDATION (UAΔT)</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="info-box">
        🌡️ <b>Fabric Load Validation (Steady-State Conductive):</b><br>
        The dashboard estimates envelope conductive load using <code>Q = Σ(U · A · ΔT)</code> (fabric conduction only).<br>
        Compare tool outputs against independent spreadsheet calculations using the same extracted U-values, areas,
        and the code-defined ΔT.<br>
        <span style="font-size:.78rem;color:rgba(255,255,255,0.52);">
        Not a full HVAC simulation (solar gains, infiltration, internal gains, and dynamic effects are excluded).
        </span>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --- climate / deltaT ---
    climate = CLIMATE_DATA.get(selected_code_name, {})
    delta_heat = float(climate.get("delta_T_heating", 0) or 0)
    delta_cool = float(climate.get("delta_T_cooling", 0) or 0)

    if delta_heat <= 0 and delta_cool <= 0:
        st.info("Fabric load validation is unavailable because ΔT is not defined for this code/climate in CLIMATE_DATA.")
    else:
        # choose heating if available
        if delta_heat > 0:
            mode_v = "heating"
            deltaT = delta_heat
        else:
            mode_v = "cooling"
            deltaT = delta_cool

        # --- recompute loads here (so Tab 7 works independently) ---
        try:
            hl_v = calculate_fabric_heat_loss(walls, roofs, windows, climate) or {}
        except Exception as e:
            hl_v = {}
            st.error(f"Fabric load calculation failed: {e}")

        if mode_v == "heating":
            tool_total = float(hl_v.get("total_heat_W", 0) or 0)
            tool_walls = float(hl_v.get("total_wall_heat", 0) or 0)
            tool_roofs = float(hl_v.get("total_roof_heat", 0) or 0)
            tool_wins = float(hl_v.get("total_win_heat", 0) or 0)
        else:
            tool_total = float(hl_v.get("total_cool_W", 0) or 0)
            tool_walls = float(hl_v.get("total_wall_cool", 0) or 0)
            tool_roofs = float(hl_v.get("total_roof_cool", 0) or 0)
            tool_wins = float(hl_v.get("total_win_cool", 0) or 0)

        st.markdown(f"**Mode:** {mode_v.capitalize()} &nbsp;·&nbsp; ΔT = {deltaT:.1f} K")
        st.markdown("**Enter your manual spreadsheet results (W).**")

        lf1, lf2, lf3, lf4 = st.columns(4)
        with lf1:
            man_walls = st.number_input(
                "Manual Walls (W)",
                min_value=0.0,
                value=float(tool_walls),
                step=10.0,
                key=f"man_walls_q_{mode_v}"
            )
        with lf2:
            man_roofs = st.number_input(
                "Manual Roofs (W)",
                min_value=0.0,
                value=float(tool_roofs),
                step=10.0,
                key=f"man_roofs_q_{mode_v}"
            )
        with lf3:
            man_wins = st.number_input(
                "Manual Windows (W)",
                min_value=0.0,
                value=float(tool_wins),
                step=10.0,
                key=f"man_wins_q_{mode_v}"
            )
        with lf4:
            man_total = st.number_input(
                "Manual TOTAL (W)",
                min_value=0.0,
                value=float(tool_total),
                step=10.0,
                key=f"man_total_q_{mode_v}"
            )

        load_pairs = [
            {"name": "Walls", "manual": float(man_walls), "tool": float(tool_walls)},
            {"name": "Roofs", "manual": float(man_roofs), "tool": float(tool_roofs)},
            {"name": "Windows", "manual": float(man_wins), "tool": float(tool_wins)},
            {"name": "TOTAL", "manual": float(man_total), "tool": float(tool_total)},
        ]

        # Table
        load_rows = []
        for p in load_pairs:
            m, t = p["manual"], p["tool"]
            diff = abs(t - m)
            pct = (diff / m * 100) if m > 0 else 0.0
            load_rows.append({
                "Component": p["name"],
                "Manual (W)": round(m, 2),
                "Tool (W)": round(t, 2),
                "Abs. Diff (W)": round(diff, 4),
                "% Error": f"{pct:.4f}%",
                "Agreement": (
                    "✅ Excellent" if pct < 0.5 else
                    "✅ Good" if pct < 2.0 else
                    "⚠️ Review" if pct < 5.0 else
                    "❌ Check"
                )
            })

        st.markdown('<div class="section-title">FABRIC LOAD COMPARISON TABLE</div>', unsafe_allow_html=True)
        df_load = pd.DataFrame(load_rows)
        st.dataframe(df_load, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Export Fabric Load Validation CSV",
            df_load.to_csv(index=False),
            f"fabric_load_validation_{mode_v}.csv",
            "text/csv"
        )

        # Stats (guarded) — NOTE: only 4 points, but still ok
        try:
            stats_in = [{"manual": p["manual"], "tool": p["tool"]} for p in load_pairs]
            load_stats = compute_validation_stats(stats_in) if len(stats_in) >= 2 else None
        except Exception as e:
            load_stats = None
            st.warning(f"Could not compute fabric-load stats (MAPE/RMSE/R²): {e}")

        if load_stats and "mape" in load_stats:
            st.markdown('<div class="section-title">FABRIC LOAD METRICS</div>', unsafe_allow_html=True)
            q1, q2, q3, q4 = st.columns(4)
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

            # Scatter — manual vs tool
            try:
                xm = [p["manual"] for p in load_pairs]
                yt = [p["tool"] for p in load_pairs]
                lbl = [p["name"] for p in load_pairs]

                fig_q = go.Figure()
                mn2 = min(xm + yt) * 0.90
                mx2 = max(xm + yt) * 1.10

                fig_q.add_trace(go.Scatter(
                    x=[mn2, mx2], y=[mn2, mx2],
                    mode="lines",
                    line=dict(color=CT["warn"], dash="dash", width=1.5),
                    name="Perfect agreement (1:1)"
                ))
                fig_q.add_trace(go.Scatter(
                    x=xm, y=yt,
                    mode="markers+text",
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

                fig_q.update_layout(**q_lay)
                st.plotly_chart(fig_q, use_container_width=True)

            except Exception as e:
                st.warning(f"Could not draw fabric-load scatter plot: {e}")

            st.markdown(
                f"""
                <div class="info-box">
                📄 <b>Research statement (fabric load):</b><br>
                "The envelope fabric load aggregation (<code>Σ(U·A·ΔT)</code>) was validated against independent spreadsheet
                calculations at the component level (walls, roofs, windows) and at the total envelope level under the selected
                {selected_code_name} climate (ΔT = <b>{deltaT:.1f} K</b>). The framework achieved MAPE <b>{load_stats['mape']:.4f}%</b>,
                RMSE <b>{load_stats['rmse']:.3f} W</b>, and R² <b>{load_stats['r_squared']:.6f}</b>, confirming computational correctness
                of the steady-state conductive load estimation."
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.info("Metrics/plot will appear once validation stats compute successfully (needs ≥2 data points).")
