"""
Autonomous Fleet vs Traditional Fleet TCO Calculator
Professional consulting-grade Streamlit dashboard

Run with: streamlit run app.py
"""
import sys
import os
from copy import deepcopy
import json
from datetime import datetime
import io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from tco_model import (
    dubai_params,
    singapore_params,
    cost_breakdown,
    breakeven_driver_wage,
    _robotaxi_total_at_util,
    _human_total_at_util,
)

# ============================================================================
# PAGE CONFIG & STYLING
# ============================================================================

st.set_page_config(
    page_title="Robotaxi TCO Calculator | Autonomous Fleet Analysis",
    layout="wide",
    initial_sidebar_state="expanded"
)

# McKinsey-inspired color palette
COLORS = {
    "primary": "#003F5C",      # Deep blue
    "accent": "#BC3C29",       # Red/rust
    "success": "#1B9E77",      # Green
    "neutral": "#B8B8B8",      # Gray
    "light": "#F5F5F5",        # Off-white
}

# Custom CSS for professional styling
st.markdown(f"""
    <style>
    /* Override default Streamlit styles */
    .main {{
        background-color: white;
        font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
    }}
    
    h1 {{
        color: {COLORS["primary"]};
        font-size: 2.2rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        letter-spacing: -0.5px;
    }}
    
    h2 {{
        color: {COLORS["primary"]};
        font-size: 1.3rem;
        font-weight: 600;
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
        border-bottom: 2px solid {COLORS["primary"]};
        padding-bottom: 0.5rem;
    }}
    
    .deck-header {{
        color: {COLORS["primary"]};
        font-size: 0.85rem;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }}
    
    .metric-card {{
        background: {COLORS["light"]};
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid {COLORS["primary"]};
        margin-bottom: 0.5rem;
    }}
    
    .decision-banner {{
        background: linear-gradient(135deg, {COLORS["light"]} 0%, white 100%);
        border-left: 5px solid {COLORS["primary"]};
        padding: 1.25rem;
        border-radius: 8px;
        margin-bottom: 1.5rem;
    }}
    
    .decision-banner.win {{
        border-left-color: {COLORS["success"]};
        background: linear-gradient(135deg, rgba(27, 158, 119, 0.05) 0%, white 100%);
    }}
    
    .decision-banner.warning {{
        border-left-color: {COLORS["accent"]};
        background: linear-gradient(135deg, rgba(188, 60, 41, 0.05) 0%, white 100%);
    }}
    
    .metric-title {{
        font-size: 0.8rem;
        color: {COLORS["neutral"]};
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    
    .metric-value {{
        font-size: 2rem;
        font-weight: 700;
        color: {COLORS["primary"]};
        margin-top: 0.25rem;
    }}
    
    .insight-box {{
        background-color: {COLORS["light"]};
        padding: 1rem;
        border-radius: 6px;
        border-left: 4px solid {COLORS["accent"]};
        margin-bottom: 1rem;
        font-size: 0.95rem;
        line-height: 1.5;
    }}
    </style>
    """, unsafe_allow_html=True)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def default_market_params(preset_name: str):
    """Return base market assumptions for the selected preset."""
    if preset_name == "Custom":
        return dubai_params()
    return {"Dubai": dubai_params(), "Singapore": singapore_params()}[preset_name]


def params_to_dict(params) -> dict:
    """Convert MarketParams to dictionary for serialization."""
    return {
        "name": params.name,
        "base_ev_price": params.base_ev_price,
        "autonomy_stack_premium": params.autonomy_stack_premium,
        "coe_premium": params.coe_premium,
        "lifetime_years": params.lifetime_years,
        "discount_rate": params.discount_rate,
        "km_per_day_robotaxi": params.km_per_day_robotaxi,
        "km_per_day_human": params.km_per_day_human,
        "service_hours_per_day": params.service_hours_per_day,
        "consumption_kwh_per_km": params.consumption_kwh_per_km,
        "ac_heat_penalty": params.ac_heat_penalty,
        "energy_cost_per_kwh": params.energy_cost_per_kwh,
        "pack_cost": params.pack_cost,
        "degradation_per_1000km": params.degradation_per_1000km,
        "replacement_threshold": params.replacement_threshold,
        "heat_degradation_multiplier": params.heat_degradation_multiplier,
        "maintenance_per_km": params.maintenance_per_km,
        "insurance_per_year": params.insurance_per_year,
        "fleet_ops_per_vehicle_day": params.fleet_ops_per_vehicle_day,
        "infra_capex_per_vehicle": params.infra_capex_per_vehicle,
        "driver_wage_per_hour": params.driver_wage_per_hour,
    }


def export_scenario_json(params, robotaxi_results, human_results, preset_name: str) -> str:
    """Export scenario as JSON."""
    export = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "scenario_name": preset_name,
            "version": "1.0",
        },
        "inputs": params_to_dict(params),
        "outputs": {
            "robotaxi_tco_per_km": robotaxi_results["total"],
            "human_tco_per_km": human_results["total"],
            "robotaxi_advantage": human_results["total"] - robotaxi_results["total"],
        },
        "robotaxi_breakdown": robotaxi_results,
        "human_breakdown": human_results,
    }
    return json.dumps(export, indent=2)


def generate_csv_export(robotaxi_results, human_results) -> str:
    """Generate CSV export of cost breakdown."""
    df = pd.DataFrame({
        "Component": list(robotaxi_results.keys()),
        "Robotaxi ($/km)": [robotaxi_results[k] for k in robotaxi_results.keys()],
        "Human-driven ($/km)": [human_results[k] for k in human_results.keys()],
    })
    return df.to_csv(index=False)


def create_styled_figure(title: str, figsize=(6, 4)):
    """Create figure with professional styling."""
    fig, ax = plt.subplots(figsize=figsize, facecolor='white', edgecolor='none')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(COLORS["neutral"])
    ax.spines['bottom'].set_color(COLORS["neutral"])
    ax.grid(axis='y', alpha=0.3, linestyle='--', linewidth=0.7)
    ax.set_axisbelow(True)
    return fig, ax


# ============================================================================
# MAIN APP
# ============================================================================

# Header with deck-style subtitle
st.markdown(f"<p class='deck-header'>Fleet Economics Analysis</p>", unsafe_allow_html=True)
st.markdown("# Autonomous vs Traditional Fleet TCO")
st.markdown(
    "Detailed cost comparison: robotaxi vs human-driven ride-hailing in high-density markets. "
    "Calibrate assumptions to your region and use case."
)

# ============================================================================
# SIDEBAR: SCENARIO CONFIG & EXPORT
# ============================================================================

with st.sidebar:
    st.markdown("---")
    st.subheader("⚙️ Scenario Configuration")
    
    preset_name = st.selectbox("Market Preset", ["Dubai", "Singapore", "Custom"], key="preset")
    base = default_market_params(preset_name)
    
    st.markdown("**Key Assumptions**")
    
    km_day = st.slider(
        "Utilization (km/day)",
        50, 600, int(base.km_per_day_robotaxi), 10,
        help="Daily kilometers for both fleet types"
    )
    
    driver_wage = st.slider(
        "Driver wage ($/hr)",
        2.0, 30.0, float(base.driver_wage_per_hour), 0.5,
        help="Fully-loaded cost per driver hour"
    )
    
    energy_cost = st.slider(
        "Energy cost ($/kWh)",
        0.02, 0.50, float(base.energy_cost_per_kwh), 0.01,
        help="Grid electricity tariff"
    )
    
    autonomy_premium = st.slider(
        "Autonomy stack premium ($)",
        5000, 60000, int(base.autonomy_stack_premium), 1000,
        help="Sensors + compute hardware (robotaxi only)"
    )
    
    pack_cost = st.slider(
        "Battery pack replacement ($)",
        3000, 20000, int(base.pack_cost), 500,
        help="Replacement battery pack cost"
    )
    
    infra_capex = st.slider(
        "Infrastructure capex ($/vehicle)",
        0, 30000, int(base.infra_capex_per_vehicle), 500,
        help="Depot + charging infrastructure share per vehicle"
    )
    
    st.markdown("---")
    
    # Build scenario
    p = deepcopy(base)
    p.km_per_day_robotaxi = float(km_day)
    p.km_per_day_human = float(km_day)
    p.driver_wage_per_hour = driver_wage
    p.energy_cost_per_kwh = energy_cost
    p.autonomy_stack_premium = float(autonomy_premium)
    p.pack_cost = float(pack_cost)
    p.infra_capex_per_vehicle = float(infra_capex)
    
    # Export / Share Section
    st.subheader("📥 Export & Share")
    
    col1, col2 = st.columns(2)
    with col1:
        r, h = cost_breakdown(p)
        
        # JSON export
        json_data = export_scenario_json(p, r, h, preset_name)
        st.download_button(
            label="📄 JSON",
            data=json_data,
            file_name=f"tco_scenario_{preset_name.lower()}_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            key="json_export"
        )
    
    with col2:
        # CSV export
        csv_data = generate_csv_export(r, h)
        st.download_button(
            label="📊 CSV",
            data=csv_data,
            file_name=f"tco_breakdown_{preset_name.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            key="csv_export"
        )
    
    # Share link (copyable)
    with st.expander("🔗 Share Scenario URL"):
        st.info(
            "**Note:** Currently deployed locally. For cloud deployment (Streamlit Cloud, "
            "Heroku), you can use shareable URLs to distribute scenarios."
        )

# ============================================================================
# MAIN CONTENT: EXECUTIVE SUMMARY
# ============================================================================

# Recalculate for main content
r, h = cost_breakdown(p)
adv = h["total"] - r["total"]
adv_pct = (abs(adv) / h["total"]) if h["total"] else 0.0

# Determine decision messaging
if abs(adv) < 1e-9:
    decision_text = "The scenarios are effectively tied at the current assumptions."
    decision_class = ""
    winner = "Tie"
    delta_label = "Near tie"
elif adv > 0:
    decision_text = (
        f"Robotaxi fleet is structurally cheaper by **${adv:.3f}/km** ({adv_pct:.0%} cost savings)."
    )
    decision_class = "win"
    winner = "Robotaxi"
    delta_label = f"Robotaxi {adv_pct:.0%} cheaper"
else:
    decision_text = (
        f"Human-driven fleet is cheaper by **${-adv:.3f}/km** ({adv_pct:.0%} cost advantage)."
    )
    decision_class = "warning"
    winner = "Human-driven"
    delta_label = f"Human-driven {adv_pct:.0%} cheaper"

# Executive Summary KPIs
col_left, col_mid, col_right = st.columns(3, gap="medium")

with col_left:
    st.markdown(f"<div class='metric-title'>Robotaxi TCO/km</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric-value'>${r['total']:.3f}</div>", unsafe_allow_html=True)

with col_mid:
    st.markdown(f"<div class='metric-title'>Human-driven TCO/km</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric-value'>${h['total']:.3f}</div>", unsafe_allow_html=True)

with col_right:
    st.markdown(f"<div class='metric-title'>Cost Differential</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric-value'>${abs(adv):.3f}</div>", unsafe_allow_html=True)

# Decision Banner
st.markdown(
    f"<div class='decision-banner {decision_class}'>"
    f"<strong style='color: {COLORS['primary']};'>Executive Decision:</strong><br/>"
    f"{decision_text}"
    f"</div>",
    unsafe_allow_html=True
)

# ============================================================================
# ANALYSIS SECTION: COST STRUCTURE & DYNAMICS
# ============================================================================

st.markdown("## Cost Structure Analysis")

tab1, tab2, tab3, tab4 = st.tabs(["TCO Comparison", "Cost Breakdown", "Sensitivity", "Utilization Dynamics"])

with tab1:
    col1, col2 = st.columns([1.2, 1], gap="large")
    
    with col1:
        # Total Cost Comparison Chart
        fig, ax = create_styled_figure("Total Cost of Ownership Comparison", figsize=(6, 4))
        bars = ax.bar(
            ["Robotaxi", "Human-driven"],
            [r["total"], h["total"]],
            color=[COLORS["primary"], COLORS["accent"]],
            width=0.5,
            edgecolor='white',
            linewidth=2
        )
        ax.set_ylabel("$/km", fontsize=11, fontweight="600")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"${x:.2f}"))
        
        # Add value labels
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'${height:.3f}/km',
                   ha='center', va='bottom', fontweight='bold', fontsize=11)
        
        ax.set_ylim(0, max(r["total"], h["total"]) * 1.15)
        st.pyplot(fig)
        plt.close(fig)
    
    with col2:
        # Summary Table
        summary_df = pd.DataFrame({
            "Metric": ["TCO/km", "Annual Cost\n(10k km)", "Annual Cost\n(100k km)"],
            "Robotaxi": [
                f"${r['total']:.3f}",
                f"${r['total'] * 10000:,.0f}",
                f"${r['total'] * 100000:,.0f}",
            ],
            "Human-driven": [
                f"${h['total']:.3f}",
                f"${h['total'] * 10000:,.0f}",
                f"${h['total'] * 100000:,.0f}",
            ]
        })
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

with tab2:
    # Stacked Cost Breakdown
    fig, ax = create_styled_figure("Cost Breakdown by Component", figsize=(9, 5))
    
    component_order = [
        "vehicle_capex", "energy", "battery_degradation", "maintenance",
        "insurance", "fleet_ops", "infrastructure", "driver_wages"
    ]
    
    component_labels = {
        "vehicle_capex": "Vehicle CapEx",
        "energy": "Energy",
        "battery_degradation": "Battery Reserve",
        "maintenance": "Maintenance",
        "insurance": "Insurance",
        "fleet_ops": "Fleet Ops",
        "infrastructure": "Infrastructure",
        "driver_wages": "Driver Wages",
    }
    
    colors_map = {
        "vehicle_capex": "#003F5C",
        "energy": "#58508D",
        "battery_degradation": "#BC5090",
        "maintenance": "#FF6361",
        "insurance": "#FFA600",
        "fleet_ops": "#1B9E77",
        "infrastructure": "#D95319",
        "driver_wages": "#B8860B",
    }
    
    bottom = np.zeros(2)
    for comp in component_order:
        vals = np.array([r.get(comp, 0), h.get(comp, 0)])
        if np.sum(vals) > 0:
            ax.bar(
                ["Robotaxi", "Human-driven"],
                vals,
                bottom=bottom,
                label=component_labels[comp],
                color=colors_map[comp],
                edgecolor='white',
                linewidth=0.5
            )
            bottom += vals
    
    ax.set_ylabel("$/km", fontsize=11, fontweight="600")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"${x:.2f}"))
    ax.legend(loc='upper left', bbox_to_anchor=(1.01, 1), fontsize=9, frameon=False)
    st.pyplot(fig)
    plt.close(fig)
    
    # Breakdown Table
    breakdown_df = pd.DataFrame({
        "Cost Component": [component_labels[c] for c in component_order],
        "Robotaxi ($/km)": [r.get(c, 0) for c in component_order],
        "Human-driven ($/km)": [h.get(c, 0) for c in component_order],
    })
    
    st.markdown("**Detailed Cost Breakdown**")
    st.dataframe(breakdown_df, use_container_width=True, hide_index=True)

with tab3:
    # Sensitivity Analysis
    st.markdown("**Key Cost Drivers: ±30% Sensitivity**")
    
    sensitivity_vars = [
        ("driver_wage_per_hour", "Driver Wage ($/hr)", -0.30, 0.30),
        ("autonomy_stack_premium", "Autonomy Stack Premium ($)", -0.30, 0.30),
        ("energy_cost_per_kwh", "Energy Cost ($/kWh)", -0.30, 0.30),
        ("km_per_day_robotaxi", "Robotaxi Utilization (km/day)", -0.30, 0.30),
        ("pack_cost", "Battery Pack Cost ($)", -0.30, 0.30),
        ("fleet_ops_per_vehicle_day", "Fleet Ops ($/veh/day)", -0.30, 0.30),
    ]
    
    sensitivity_results = []
    for attr, label, lo_pct, hi_pct in sensitivity_vars:
        base_adv = h["total"] - r["total"]
        
        # Low scenario
        q_lo = deepcopy(p)
        setattr(q_lo, attr, getattr(q_lo, attr) * (1 + lo_pct))
        r_lo, h_lo = cost_breakdown(q_lo)
        adv_lo = h_lo["total"] - r_lo["total"]
        
        # High scenario
        q_hi = deepcopy(p)
        setattr(q_hi, attr, getattr(q_hi, attr) * (1 + hi_pct))
        r_hi, h_hi = cost_breakdown(q_hi)
        adv_hi = h_hi["total"] - r_hi["total"]
        
        swing = abs(adv_hi - adv_lo)
        sensitivity_results.append({
            "Driver": label,
            "Base Advantage": f"${base_adv:.3f}",
            "-30% Impact": f"${adv_lo:.3f}",
            "+30% Impact": f"${adv_hi:.3f}",
            "Swing": f"${swing:.3f}",
        })
    
    sens_df = pd.DataFrame(sensitivity_results).sort_values("Swing", ascending=False, key=abs)
    st.dataframe(sens_df, use_container_width=True, hide_index=True)
    
    # Tornado chart
    fig, ax = create_styled_figure("Sensitivity Tornado: Impact on Robotaxi Advantage", figsize=(9, 5))
    
    labels = [r["Driver"] for r in sensitivity_results]
    swings = [float(r["Swing"].replace("$", "")) for r in sensitivity_results]
    
    sorted_idx = np.argsort(np.abs(swings))[::-1][:8]  # Top 8
    labels_sorted = [labels[i] for i in sorted_idx]
    swings_sorted = [swings[i] for i in sorted_idx]
    
    y_pos = np.arange(len(labels_sorted))
    ax.barh(y_pos, swings_sorted, color=COLORS["primary"], edgecolor='white', linewidth=1)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels_sorted, fontsize=10)
    ax.set_xlabel("Change in Robotaxi Advantage ($/km)", fontsize=11, fontweight="600")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, p: f"${x:.2f}"))
    ax.invert_yaxis()
    
    for i, v in enumerate(swings_sorted):
        ax.text(v + 0.01, i, f"${v:.2f}", va='center', fontsize=9, fontweight="bold")
    
    st.pyplot(fig)
    plt.close(fig)

with tab4:
    # Utilization Dynamics
    st.markdown("**Cost Evolution Across Utilization Levels**")
    
    ks = np.arange(50, 601, 25)
    rk = [_robotaxi_total_at_util(p, k) for k in ks]
    hk = [_human_total_at_util(p, k) for k in ks]
    
    fig, ax = create_styled_figure("TCO/km vs Daily Utilization", figsize=(9, 5))
    ax.plot(ks, rk, label="Robotaxi", linewidth=2.5, color=COLORS["primary"], marker='o', markersize=4)
    ax.plot(ks, hk, label="Human-driven", linewidth=2.5, color=COLORS["accent"], marker='s', markersize=4, linestyle='--')
    ax.fill_between(ks, rk, hk, where=(np.array(hk) > np.array(rk)), alpha=0.1, color=COLORS["primary"], label="Robotaxi advantage")
    ax.set_xlabel("Daily Utilization (km/day)", fontsize=11, fontweight="600")
    ax.set_ylabel("TCO ($/km)", fontsize=11, fontweight="600")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"${x:.2f}"))
    ax.legend(fontsize=10, loc='best', frameon=False)
    ax.grid(alpha=0.3, linestyle='--')
    st.pyplot(fig)
    plt.close(fig)

# ============================================================================
# INSIGHTS & IMPLICATIONS
# ============================================================================

st.markdown("## Key Insights")

# Breakeven driver wage
bw = breakeven_driver_wage(p)

col1, col2 = st.columns(2)

with col1:
    st.markdown("### Labor Arbitrage Thesis")
    if bw <= 0:
        st.markdown(
            f"<div class='insight-box'>"
            f"<strong>Critical Finding:</strong> At current utilization levels, the human-driven "
            f"fleet is already cheaper than robotaxi without wage cuts. The robotaxi business case "
            f"does not hold under these assumptions."
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"<div class='insight-box'>"
            f"<strong>Breakeven Driver Wage:</strong> Driver wages would need to fall to "
            f"<strong>${bw:.2f}/hr</strong> (from current ${p.driver_wage_per_hour:.2f}/hr) for "
            f"human-driven to become cheaper at {int(km_day)} km/day utilization.<br/><br/>"
            f"<strong>Implication:</strong> The robotaxi advantage is <strong>robust to labor-cost variation</strong> "
            f"and represents a structural cost edge driven by elimination of driver wages."
            f"</div>",
            unsafe_allow_html=True
        )

with col2:
    st.markdown("### Cost Structure Summary")
    
    # Determine key drivers
    top_driver = max([("Robotaxi", r), ("Human-driven", h)], key=lambda x: x[1]["total"])
    
    cost_summary = f"""
    **{top_driver[0]} Fleet:**
    - Largest cost: {max(top_driver[1].items(), key=lambda x: x[1])[0].replace('_', ' ').title()}
    - Total TCO: ${top_driver[1]["total"]:.3f}/km
    
    **Market Context ({preset_name}):**
    - Utilization: {int(km_day)} km/day
    - Driver wage: ${p.driver_wage_per_hour:.2f}/hr
    - Energy cost: ${p.energy_cost_per_kwh:.2f}/kWh
    """
    
    st.markdown(cost_summary)

# ============================================================================
# FOOTER & METHODOLOGY
# ============================================================================

st.markdown("---")

col_method, col_about = st.columns(2)

with col_method:
    with st.expander("📋 Methodology & Assumptions", expanded=False):
        st.markdown("""
        **TCO Model:** Per-kilometer cost over 8-year vehicle life, capex amortized with 8% capital recovery rate.
        
        **Key Assumptions by Component:**
        - **Capex:** Base EV + autonomy stack (robotaxi) + registration premium (market-specific)
        - **Energy:** kWh/km × climate penalty × $/kWh tariff
        - **Battery:** Linear degradation with heat adjustment; replacement when capacity falls below 70%
        - **Maintenance:** Fixed $/km (includes tires, fluids, repairs)
        - **Insurance:** Annual premium normalized to km
        - **Fleet Ops:** Robotaxi-specific (cleaning, remote support, dispatch)
        - **Infrastructure:** Robotaxi depot/charging capex share, amortized
        - **Driver:** Human-driven only; fully-loaded hourly wage ÷ daily km
        
        **Preset Calibration (Dubai vs Singapore):**
        - Dubai: Low wages, low energy, high AC load
        - Singapore: High wages, high energy, high land costs (COE premium)
        """)

with col_about:
    with st.expander("ℹ️ About This Tool", expanded=False):
        st.markdown("""
        **Purpose:** Decision-support tool for fleet operators and investors evaluating robotaxi vs 
        traditional ride-hailing economics in high-density markets.
        
        **Data Source:** Illustrative assumptions for scenario modeling. 
        **Not** market quotes—calibrate with local data before commercial deployment.
        
        **Model:** Python TCO framework with Streamlit dashboard
        **Repository:** [autonomous-fleet-tco-calculator](https://github.com/HemanthMChakravarthy/autonomous-fleet-tco-calculator)
        
        **Caveats:**
        - Assumes consistent utilization and operational performance
        - Does not model demand elasticity or competitive dynamics
        - Robotaxi availability assumes mature autonomous tech (not R&D-phase costs)
        - Regional presets are illustrative; calibrate for your market
        """)

st.markdown(
    f"<p style='text-align: center; color: {COLORS['neutral']}; font-size: 0.85rem; margin-top: 2rem;'>"
    f"<strong>Autonomous Fleet TCO Calculator</strong> | Scenario: {preset_name} | "
    f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    f"</p>",
    unsafe_allow_html=True
)
