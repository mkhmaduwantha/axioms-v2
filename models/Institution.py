from dataclasses import dataclass, field
from enums import RAMethod

@dataclass
class Institution:
    ra_method: RAMethod = RAMethod.RATION