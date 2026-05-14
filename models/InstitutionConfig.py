from dataclasses import dataclass, field
from enums import RAMethod

@dataclass
class InstitutionConfig:
    ra_method:               RAMethod = RAMethod.RATION
    ex_sanction_level:       int      = 3
    monitoring_freq:         float    = 0.10
    monitoring_freq_out:     float    = 0.01
    monitoring_cost:         int      = 50
    monitoring_cost_out:     int      = 5
    sanction_durations:      dict     = field(
        default_factory=lambda: {1: 5, 2: 10, 3: 15}
    )
    appeal_window:           int      = 30
    p_max:                   int      = 1000
    # replenishment_moderate:  float    = 0.45
    # replenishment_low:       float    = 0.35
    # replenishment_high:      float    = 0.50
    replenishment_moderate:  float    = 0.40
    replenishment_low:       float    = 0.30
    replenishment_high:      float    = 0.45
    replenishment_phase_len: int      = 5            # rounds per replenishment phase
    queue_demand_mean:       int      = 50
    ac_method:               str      = "attribute"   # "attribute" | "discretionary"
    ex_method:               str      = "discretionary"  # "discretionary" | "jury"
 