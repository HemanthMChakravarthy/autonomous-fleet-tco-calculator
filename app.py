"""Streamlit demo: Autonomous Fleet vs Traditional Fleet TCO Calculator.

Run with: streamlit run app.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import numpy as np
import streamlit as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tco_model import (dubai_params, singapore_params, cost_breakdown,
                       breakeven_driver_wage, _robotaxi_total_at_util,
                       _human_total_at_util)

st.set_page_config(page_title="Robotaxi vs Ride-Hailing TCO Calculator", layout="wide")
st.title("Autonomous Fleet vs Traditional Fleet TCO Calculator")
st.caption("TCO per km: robotaxis vs human-driven ride-hailing. "
           "All defaults are illustrative assumptions — calibrate locally before commercial use.")

COMPONENT_LABELS = {
    "vehicle_capex": "Vehicle capex", "energy": "Energy",
    "battery_degradation": "Battery reserve", "maintenance": "Maintenance",
    "insurance": "Insurance", "fleet_ops": "Fleet ops (robotaxi)",
    "infrastructure": "Infrastructure (robotaxi)", "driver_wages": "Driver wages (human)",
}

preset_name = st.sidebar.selectbox("Scenario preset", ["Dubai", "Singapore", "Custom"])
base = {"Dubai": dubai_params(), "Singapore": singapore_params()}[preset_name] \
    if preset_name != "Custom" else dubai_params()

st.sidebar.header("Key variables")
km_day = st.sidebar.slider("Utilization (km/day, both fleets)",
                           50, 600, int(base.km_per_day_robotaxi), 10)
driver_wage = st.sidebar.slider("Driver wage ($/hr)", 2.0, 30.0,
                                float(base.driver_wage_per_hour), 0.5)
energy_cost = st.sidebar.slider("Energy cost ($/kWh)", 0.02, 0.50,
                                float(base.energy_cost_per_kwh), 0.01)
autonomy_premium = st.sidebar.slider("Autonomy stack premium ($)",
                                     5000, 60000, int(base.autonomy_stack_premium), 1000)
pack_cost = st.sidebar.slider("Battery pack replacement cost ($)",
                              3000, 20000, int(base.pack_cost), 500)
infra_capex = st.sidebar.slider("Infrastructure capex ($/vehicle)",
                                0, 30000, int(base.infra_capex_per_vehicle), 500)

p = base
p.km_per_day_robotaxi = float(km_day)
p.km_per_day_human = float(km_day)
p.driver_wage_per_hour = driver_wage
p.energy_cost_per_kwh = energy_cost
p.autonomy_stack_premium = float(autonomy_premium)
p.pack_cost = float(pack_cost)
p.infra_capex_per_vehicle = float(infra_capex)

r, h = cost_breakdown(p)
adv = h["total"] - r["total"]
winner = "Robotaxi" if adv > 0 else "Human-driven"

c1, c2, c3 = st.columns(3)
c1.metric("Robotaxi TCO/km", f"${r['total']:.3f}")
c2.metric("Human-driven TCO/km", f"${h['total']:.3f}")
c3.metric("Robotaxi advantage", f"${adv:.3f}/km ({adv/h['total']:.0%})",
          delta=f"{winner} wins")

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("TCO/km comparison")
    fig, ax = plt.subplots(figsize=(5, 3.5))
    ax.bar(["Robotaxi", "Human-driven"], [r["total"], h["total"]],
           color=["#16a34a", "#dc2626"])
    ax.set_ylabel("$/km")
    for i, v in enumerate([r["total"], h["total"]]):
        ax.text(i, v + 0.02, f"${v:.3f}", ha="center", fontsize=10, weight="bold")
    st.pyplot(fig); plt.close(fig)

with col_b:
    st.subheader("Cost breakdown ($/km)")
    order = list(COMPONENT_LABELS)
    fig, ax = plt.subplots(figsize=(5, 3.5))
    bottom = np.zeros(2)
    for k in order:
        vals = np.array([r[k], h[k]])
        ax.bar(["Robotaxi", "Human-driven"], vals, bottom=bottom,
               label=COMPONENT_LABELS[k])
        bottom += vals
    ax.set_ylabel("$/km")
    ax.legend(fontsize=7, bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    st.pyplot(fig); plt.close(fig)

st.subheader("Breakeven vs utilization")
ks = np.arange(50, 601, 25)
rk = [_robotaxi_total_at_util(p, k) for k in ks]
hk = [_human_total_at_util(p, k) for k in ks]
fig, ax = plt.subplots(figsize=(9, 3.8))
ax.plot(ks, rk, label="Robotaxi")
ax.plot(ks, hk, label="Human-driven", linestyle="--")
ax.set_xlabel("Utilization (km/day)"); ax.set_ylabel("TCO ($/km)")
ax.legend(); ax.grid(alpha=0.3)
st.pyplot(fig); plt.close(fig)

bw = breakeven_driver_wage(p)
st.info(f"Driver wages would need to fall to **${bw:.2f}/hr** before human-driven "
        f"becomes cheaper at {km_day} km/day — the robotaxi edge is a labor-arbitrage edge.")

st.caption("Model: src/tco_model.py · Presets: Dubai, Singapore · "
           "Illustrative assumptions only.")
