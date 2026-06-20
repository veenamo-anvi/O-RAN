# 03.2 — InfluxDB Measurements

> **Parent:** [Dev Environment](./spec.md) › [Root Spec](../spec.md)

| Measurement | Tags | Key Fields |
|---|---|---|
| `cell_kpi` | cell_id, area, band, pci, du_id, cu_id, vendor, generation | connected_ues, dl/ul_throughput_mbps, rsrp_dbm, rsrq_db, sinr_db, power_w, prb_dl/ul_pct, packet_loss_pct, cqi, mcs, bler_pct, latency_ms, jitter_ms, interference_dbm |
| `du_kpi` | du_id, cu_id | active_ues, cell_count, cpu_pct, memory_pct, fronthaul_latency_us, processing_delay_ms, f1_msg_per_sec |
| `cu_kpi` | cu_id | du_count, rrc_connected, rrc_idle, rrc_setup_rate, inter_du_ho_rate, pdcp_dl_gbps, pdcp_ul_gbps, f1_latency_ms, n2_latency_ms, n3_latency_ms, e1_latency_ms, cpu_pct, memory_pct |
| `core_kpi` | component, instance_id | **AMF**: registered_ues, active_sessions, nas_msg_per_sec, paging_per_sec, handover_per_sec · **SMF**: active_pdu_sessions, session_setup_rate, ip_pool_utilization_pct · **UPF**: dl/ul_throughput_gbps, active_tunnels, packet_drop_rate (field set varies by `component`) |
| `ue_mobility` | ue_id, source_cell, target_cell, event_type | rsrp_source, rsrp_target, ho_duration_ms, velocity_kmh |
| `ue_usage` | ue_id, cell_id, slice_type | dl_bytes, ul_bytes, latency_ms, jitter_ms, packet_loss |
| `alerts` | severity, cell_id, du_id, alert_type | message, metric_value, threshold, ai_confidence |
| `son_actions` | cell_id, du_id, action_type | message, confidence (written for every autonomous SON decision) |
| `topology_event` | event_type | cell_id/du_id, from/to component |
