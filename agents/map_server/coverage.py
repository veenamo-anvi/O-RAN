"""COST-231-Hata urban-macro coverage radius (inverted to distance).

compute_coverage_radius_m(band, tx_power_w, generation, antenna_config) -> metres.
hb=25 m, hm=1.5 m, dense-urban +3 dB, UE NF=7 dB, edge SNR=-3 dB.
"""
from __future__ import annotations

import math

GEN_EFFICIENCY = {"5G": 0.22, "4G": 0.32}
ANTENNA_GAIN_DBI = {"64T64R": 24.0, "4T4R": 17.0, "8T8R": 20.0}
BAND_FREQ_MHZ = {"n78": 3500, "n41": 2500, "n28": 700, "B40": 2300, "B3": 1800}
BAND_BW_MHZ = {"n78": 100, "n41": 100, "n28": 20, "B40": 20, "B3": 20}

UE_NOISE_FIGURE_DB = 7.0
EDGE_SNR_DB = -3.0
PENETRATION_LOSS_DB = 18.0
HB_M = 25.0
HM_M = 1.5
DENSE_URBAN_C = 3.0


def _thermal_noise_dbm(bw_mhz: float) -> float:
    return -174.0 + 10 * math.log10(bw_mhz * 1e6) + UE_NOISE_FIGURE_DB


def compute_coverage_radius_m(band: str, tx_power_w: float, generation: str, antenna_config: str) -> float:
    freq = BAND_FREQ_MHZ.get(band, 3500)
    bw = BAND_BW_MHZ.get(band, 20)
    eff = GEN_EFFICIENCY.get(generation, 0.25)
    gain = ANTENNA_GAIN_DBI.get(antenna_config, 17.0)

    rf_w = max(tx_power_w * eff, 0.1)
    eirp_dbm = 10 * math.log10(rf_w * 1000.0) + gain
    noise = _thermal_noise_dbm(bw)
    pl_max = eirp_dbm - (noise - EDGE_SNR_DB) - PENETRATION_LOSS_DB

    logf = math.log10(freq)
    a_hm = (1.1 * logf - 0.7) * HM_M - (1.56 * logf - 0.8)
    A = 46.3 + 33.9 * logf - 13.82 * math.log10(HB_M) - a_hm + DENSE_URBAN_C
    B = 44.9 - 6.55 * math.log10(HB_M)

    d_km = 10 ** ((pl_max - A) / B)
    return round(max(50.0, min(d_km * 1000.0, 15000.0)), 1)


def radius_for_cell(cell: dict) -> float:
    model = compute_coverage_radius_m(
        cell.get("band", "n78"), float(cell.get("tx_power_w", 320) or 320),
        cell.get("generation", "5G"), cell.get("antenna_config", "4T4R"),
    )
    # prefer live radius from KPI telemetry only when within 2x of the model estimate
    live = (cell.get("kpi") or {}).get("coverage_radius_m")
    if live and 0.5 * model <= float(live) <= 2.0 * model:
        return round(float(live), 1)
    return model
