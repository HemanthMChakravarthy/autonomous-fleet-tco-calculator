"""
Total Cost of Ownership (TCO) per kilometer model:
autonomous robotaxi fleet vs. human-driven ride-hailing fleet.

All default numbers are ILLUSTRATIVE assumptions for scenario modelling,
not market quotes. Calibrate with local data before using commercially.
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple, List


@dataclass
class MarketParams:
    """All inputs needed to compute TCO/km for one market."""
    name: str

    # --- Vehicle capex ---
    base_ev_price: float = 35000.0          # USD, vehicle before autonomy hardware
    autonomy_stack_premium: float = 25000.0  # USD, sensors + compute (robotaxi only)
    coe_premium: float = 0.0                # USD, registration premium (e.g. Singapore COE)
    lifetime_years: int = 8
    discount_rate: float = 0.08             # for capex amortization (capital recovery)

    # --- Utilization ---
    km_per_day_robotaxi: float = 300.0
    km_per_day_human: float = 260.0
    service_hours_per_day: float = 16.0

    # --- Energy ---
    consumption_kwh_per_km: float = 0.20
    ac_heat_penalty: float = 0.0             # extra energy fraction (A/C, heat)
    energy_cost_per_kwh: float = 0.15

    # --- Battery degradation ---
    pack_cost: float = 8000.0               # USD, replacement pack
    degradation_per_1000km: float = 0.0008  # capacity fraction lost per 1000 km
    replacement_threshold: float = 0.70     # replace pack below 70% capacity
    heat_degradation_multiplier: float = 1.0

    # --- Opex ---
    maintenance_per_km: float = 0.04
    insurance_per_year: float = 1500.0

    # --- Robotaxi-only ---
    fleet_ops_per_vehicle_day: float = 25.0  # cleaning, remote assistance, dispatch
    infra_capex_per_vehicle: float = 8000.0   # depot + charging share

    # --- Human-driven-only ---
    driver_wage_per_hour: float = 10.0

    notes: str = field(default="", repr=False)


def capital_recovery_factor(rate: float, years: int) -> float:
    """Annualized share of capex: r(1+r)^n / ((1+r)^n - 1)."""
    if rate <= 0:
        return 1.0 / years
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def _annual_km(km_per_day: float) -> float:
    return km_per_day * 365.0


def battery_reserve_per_km(p: MarketParams, annual_km: float) -> Tuple[float, int]:
    """Reserve $/km for pack replacements over vehicle lifetime.

    Capacity fades linearly; a replacement is booked each time capacity
    would fall below the threshold. Returns (cost per km, replacements).
    """
    fade = p.degradation_per_1000km * p.heat_degradation_multiplier
    lifetime_km = annual_km * p.lifetime_years
    if fade <= 0:
        return 0.0, 0
    km_to_replacement = (1.0 - p.replacement_threshold) / fade * 1000.0
    replacements = int(lifetime_km // km_to_replacement)
    return replacements * p.pack_cost / lifetime_km, replacements


def tco_per_km(p: MarketParams, autonomous: bool) -> Dict[str, float]:
    """Return per-km cost breakdown for one fleet type. Keys are $/km."""
    km_day = p.km_per_day_robotaxi if autonomous else p.km_per_day_human
    annual_km = _annual_km(km_day)
    lifetime_km = annual_km * p.lifetime_years
    crf = capital_recovery_factor(p.discount_rate, p.lifetime_years)

    capex = p.base_ev_price + p.coe_premium
    if autonomous:
        capex += p.autonomy_stack_premium

    out = {
        "vehicle_capex": capex * crf / annual_km,
        "energy": p.consumption_kwh_per_km * (1.0 + p.ac_heat_penalty)
                  * p.energy_cost_per_kwh,
        "maintenance": p.maintenance_per_km,
        "insurance": p.insurance_per_year / annual_km,
    }
    battery_cost, _ = battery_reserve_per_km(p, annual_km)
    out["battery_degradation"] = battery_cost

    if autonomous:
        out["fleet_ops"] = p.fleet_ops_per_vehicle_day / km_day
        out["infrastructure"] = p.infra_capex_per_vehicle * crf / annual_km
        out["driver_wages"] = 0.0
    else:
        out["fleet_ops"] = 0.0
        out["infrastructure"] = 0.0
        out["driver_wages"] = (p.driver_wage_per_hour
                               * p.service_hours_per_day / km_day)

    out["total"] = sum(out.values())
    return out


def cost_breakdown(p: MarketParams) -> Tuple[Dict[str, float], Dict[str, float]]:
    """(robotaxi breakdown, human-driven breakdown)."""
    return tco_per_km(p, True), tco_per_km(p, False)


def _robotaxi_total_at_util(p: MarketParams, km_day: float) -> float:
    q = MarketParams(**{**p.__dict__, "km_per_day_robotaxi": km_day})
    return tco_per_km(q, True)["total"]


def _human_total_at_util(p: MarketParams, km_day: float) -> float:
    q = MarketParams(**{**p.__dict__, "km_per_day_human": km_day})
    return tco_per_km(q, False)["total"]


def breakeven_utilization(p: MarketParams,
                         lo: float = 50.0, hi: float = 1000.0,
                         tol: float = 0.5) -> float:
    """km/day above which the robotaxi fleet is cheaper than human-driven.

    Bisection on the (human - robotaxi) cost gap, which shrinks monotonically
    as utilization rises because robotaxi fixed costs amortize faster.
    Returns None if no crossing exists in [lo, hi].
    """
    def gap(k):
        return _human_total_at_util(p, k) - _robotaxi_total_at_util(p, k)
    if gap(lo) >= 0 and gap(hi) >= 0:
        return lo  # robotaxi already cheaper at minimum utilization
    if gap(lo) < 0 and gap(hi) < 0:
        return None  # robotaxi never cheaper in range
    a, b = lo, hi
    while b - a > tol:
        m = (a + b) / 2
        if gap(m) >= 0:
            b = m
        else:
            a = m
    return (a + b) / 2


def breakeven_driver_wage(p: MarketParams) -> float:
    """Driver wage ($/hr) below which human-driven becomes cheaper.

    At base utilization. A low number means the robotaxi advantage is
    structurally robust to labor-cost variation.
    """
    r = tco_per_km(p, True)["total"]
    h = tco_per_km(p, False)
    non_wage = h["total"] - h["driver_wages"]
    km_day = p.km_per_day_human
    # non_wage + wage * hours / km_day = r  =>  wage = (r - non_wage) * km_day / hours
    if r <= non_wage:
        return 0.0
    return (r - non_wage) * km_day / p.service_hours_per_day


SENSITIVITY_VARS: List[Tuple[str, str]] = [
    ("driver_wage_per_hour", "Driver wage ($/hr)"),
    ("km_per_day_robotaxi", "Robotaxi utilization (km/day)"),
    ("autonomy_stack_premium", "Autonomy stack premium ($)"),
    ("energy_cost_per_kwh", "Energy cost ($/kWh)"),
    ("pack_cost", "Battery pack cost ($)"),
    ("fleet_ops_per_vehicle_day", "Fleet ops ($/veh/day)"),
    ("infra_capex_per_vehicle", "Infrastructure capex ($)"),
    ("maintenance_per_km", "Maintenance ($/km)"),
]


def sensitivity(p: MarketParams, pct: float = 0.30) -> List[Dict]:
    """Vary each key input +/-pct; report effect on the robotaxi cost advantage.

    Advantage = human TCO/km - robotaxi TCO/km (positive => robotaxi cheaper).
    """
    base = (tco_per_km(p, False)["total"] - tco_per_km(p, True)["total"])
    rows = []
    for attr, label in SENSITIVITY_VARS:
        vals = {}
        for sign in (-1, 1):
            q = MarketParams(**p.__dict__)
            setattr(q, attr, getattr(q, attr) * (1 + sign * pct))
            vals[sign] = (tco_per_km(q, False)["total"]
                          - tco_per_km(q, True)["total"])
        rows.append({"variable": label, "low": vals[-1], "high": vals[1],
                     "base": base,
                     "swing": abs(vals[1] - vals[-1])})
    rows.sort(key=lambda r: r["swing"], reverse=True)
    return rows


def dubai_params() -> MarketParams:
    return MarketParams(
        name="Dubai",
        base_ev_price=35000.0,
        autonomy_stack_premium=25000.0,
        coe_premium=0.0,
        km_per_day_robotaxi=320.0,
        km_per_day_human=280.0,
        service_hours_per_day=16.0,
        consumption_kwh_per_km=0.20,
        ac_heat_penalty=0.15,          # heavy A/C load
        energy_cost_per_kwh=0.08,      # low subsidized tariff
        heat_degradation_multiplier=1.5,
        maintenance_per_km=0.04,
        insurance_per_year=1500.0,
        fleet_ops_per_vehicle_day=25.0,
        infra_capex_per_vehicle=8000.0,
        driver_wage_per_hour=9.0,
        notes="Illustrative: low energy cost, low driver wages, high heat/AC load.",
    )


def singapore_params() -> MarketParams:
    return MarketParams(
        name="Singapore",
        base_ev_price=35000.0,
        autonomy_stack_premium=25000.0,
        coe_premium=40000.0,           # COE-style registration premium
        km_per_day_robotaxi=240.0,
        km_per_day_human=220.0,
        service_hours_per_day=16.0,
        consumption_kwh_per_km=0.20,
        ac_heat_penalty=0.10,
        energy_cost_per_kwh=0.28,      # high electricity tariff
        heat_degradation_multiplier=1.2,
        maintenance_per_km=0.045,
        insurance_per_year=2500.0,
        fleet_ops_per_vehicle_day=30.0,
        infra_capex_per_vehicle=10000.0,  # high land/depot cost
        driver_wage_per_hour=16.0,
        notes="Illustrative: high energy cost, high wages, COE premium on capex.",
    )


PRESETS = {"dubai": dubai_params, "singapore": singapore_params}
