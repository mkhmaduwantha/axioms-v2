from enum import Enum

class AxiomVerdict(str, Enum):
    PERMITTED            = "PERMITTED"
    NO_POWER             = "NO_POWER"             # agent lacks pow() for this action
    NO_PERMISSION        = "NO_PERMISSION"         # agent lacks per() for this action
    OBLIGATION_VIOLATED  = "OBLIGATION_VIOLATED"   # agent has obl() but is not performing it