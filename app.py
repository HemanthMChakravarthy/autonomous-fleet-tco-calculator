"""Streamlit demo: Autonomous Fleet vs Traditional Fleet TCO Calculator.

Run with: streamlit run app.py
"""
import sys
import os
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tco_model import (
    dubai_params,
    singapore_params,
    cost_breakdown,
    breakeven_driver_wage,
    _robotaxi_total_at_util,
    _human_total_at_util,
)


st.set_page_config(page_title="Robotaxi vs Ride-Hailing TCO Calculator", layout="wide")
st.title("Autonomous Fleet vs Traditional Fleet TCO Calculator")
st.caption(
    "TCO per km: robotaxis vs human-driven ride-hailing. "
    "All defaults are illustrative assumptions — calibrate locally before commercial use."
)

COMPONENT_LABELS = {
    "vehicle_capex": "Vehicle capex",
    "energy": "Energy",
    "battery_degradation": "Battery reserve",
    "maintenance": "Maintenance",
    "insurance": "Insurance",
    "fleet_ops": "Fleet ops (robotaxi)",
    "infrastructure": "Infrastructure (robotaxi)",
    "driver_wages": "Driver wages (human)",
}


def default_market_params(preset_name: str):
    """Return base market assumptions for the selected preset."""
    if preset_name == "Custom":
        st.sidebar.caption("Custom mode starts from Dubai defaults so you can calibrate a scenario.")
        return dubai_params()
    return {"Dubai": dubai_params(), "Singapore": singapore_params()}[preset_name]


preset_name = st.sidebar.selectbox("Scenario preset", ["Dubai", "Singapore", "Custom"])
base = default_market_params(preset_name)

st.sidebar.header("Key variables")
km_day = st.sidebar.slider(
    "Utilization (km/day, both fleets)",
    50,
    600,
    int(base.km_per_day_robotaxi),
    10,
)
driver_wage = st.sidebar.slider(
    "Driver wage ($/hr)",
    2.0,
    30.0,
    float(base.driver_wage_per_hour),
    0.5,
)
energy_cost = st.sidebar.slider(
    "Energy cost ($/kWh)",
    0.02,
    0.50,
    float(base.energy_cost_per_kwh),
    0.01,
)
autonomy_premium = st.sidebar.slider(
    "Autonomy stack premium ($)",
    5000,
    60000,
    int(base.autonomy_stack_premium),
    1000,
)
pack_cost = st.sidebar.slider(
    "Battery pack replacement cost ($)",
    3000,
    20000,
    int(base.pack_cost),
    500,
)
infra_capex = st.sidebar.slider(
    "Infrastructure capex ($/vehicle)",
    0,
    30000,
    int(base.infra_capex_per_vehicle),
    500,
)

p = deepcopy(base)
p.km_per_day_robotaxi = float(km_day)
p.km_per_day_human = float(km_day)
p.driver_wage_per_hour = driver_wage
p.energy_cost_per_kwh = energy_cost
p.autonomy_stack_premium = float(autonomy_premium)
p.pack_cost = float(pack_cost)
p.infra_capex_per_vehicle = float(infra_capex)

r, h = cost_breakdown(p)
adv = h["total"] - r["total"]
adv_abs = abs(adv)
adv_pct = (adv_abs / h["total"]) if h["total"] else 0.0

if abs(adv) < 1e-9:
    decision_text = "The scenarios are effectively tied at the current assumptions."
    delta_label = "Near tie"
    metric_label = "Scenario gap"
    metric_value = "$0.000/km"
    alert_kind = "info"
elif adv > 0:
    decision_text = (
        f"Robotaxi is cheaper by ${adv:.3f}/km ({adv_pct:.0%} lower cost than human-driven)."
    )
    delta_label = "Robotaxi wins"
    metric_label = "Robotaxi advantage"
    metric_value = f"${adv:.3f}/km"
    alert_kind = "success"
else:
    decision_text = (
        f"Human-driven is cheaper by ${-adv:.3f}/km ({adv_pct:.0%} lower cost than robotaxi)."
    )
    delta_label = "Human-driven wins"
    metric_label = "Human-driven advantage"
    metric_value = f"${-adv:.3f}/km"
    alert_kind = "warning"

c1, c2, c3 = st.columns(3)
c1.metric("Robotaxi TCO/km", f"${r['total']:.3f}")
c2.metric("Human-driven TCO/km", f"${h['total']:.3f}")
c3.metric(metric_label, metric_value, delta=delta_label)

st.markdown(f"<div style='padding: 0.5rem 0.75rem; border-left: 4px solid #7c3aed; background: #f5f3ff; border-radius: 6px;'>"
            f"<strong>Decision:</strong> {decision_text}</div>", unsafe_allow_html=True)

summary_df = pd.DataFrame(
    [
        {"Fleet": "Robotaxi", "TCO/km": r["total"]},
        {"Fleet": "Human-driven", "TCO/km": h["total"]},
    ]
)
with st.expander("Key figures", expanded=False):
    st.dataframe(summary_df, hide_index=True, use_container_width=True)

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("TCO/km comparison")
    fig, ax = plt.subplots(figsize=(5, 3.5))
    ax.bar(["Robotaxi", "Human-driven"], [r["total"], h["total"]], color=["#16a34a", "#dc2626"])
    ax.set_ylabel("$/km")
    for i, v in enumerate([r["total"], h["total"]]):
        ax.text(i, v + 0.02, f"${v:.3f}", ha="center", fontsize=10, weight="bold")
    st.pyplot(fig)
    plt.close(fig)

with col_b:
    st.subheader("Cost breakdown ($/km)")
    order = list(COMPONENT_LABELS)
    fig, ax = plt.subplots(figsize=(5, 3.5))
    bottom = np.zeros(2)
    for k in order:
        vals = np.array([r[k], h[k]])
        ax.bar(["Robotaxi", "Human-driven"], vals, bottom=bottom, label=COMPONENT_LABELS[k])
        bottom += vals
    ax.set_ylabel("$/km")
    ax.legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

st.subheader("Breakeven vs utilization")
ks = np.arange(50, 601, 25)
rk = [_robotaxi_total_at_util(p, k) for k in ks]
hk = [_human_total_at_util(p, k) for k in ks]
fig, ax = plt.subplots(figsize=(9, 3.8))
ax.plot(ks, rk, label="Robotaxi")
ax.plot(ks, hk, label="Human-driven", linestyle="--")
ax.set_xlabel("Utilization (km/day)")
ax.set_ylabel("TCO ($/km)")
ax.legend()
ax.grid(alpha=0.3)
st.pyplot(fig)
plt.close(fig)

bw = breakeven_driver_wage(p)
if bw <= 0:
    st.info(
        "At the current utilization, the human-driven fleet is already cheaper than the robotaxi case "
        "without needing further wage cuts."
    )
else:
    st.info(
        f"Driver wages would need to fall to **${bw:.2f}/hr** before human-driven becomes cheaper at "
        f"{km_day} km/day — the robotaxi edge is a labor-arbitrage edge."
    )

st.caption(f"Model: src/tco_model.py · Preset: {preset_name} · Illustrative assumptions only.")
