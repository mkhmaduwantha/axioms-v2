from dataclasses import dataclass, field
from enums import AxiomVerdict
# ---------------------------------------------------------------------------
# Ostrom Axiom Engine
# Precisely maps the Event Calculus axioms from Section 5.3 of the paper.
#
# Each check_<action>() method returns an AxiomResult describing:
#   - has_power:      bool   — pow(Agent, Action) holds
#   - has_permission: bool   — per(Agent, Action) holds
#   - has_obligation: bool   — obl(Agent, Action) holds
#   - verdict:        AxiomVerdict
#   - explanation:    str    — natural language mapping of which axiom fired
# ---------------------------------------------------------------------------
 
@dataclass
class AxiomResult:
    action:           str
    has_power:        bool
    has_permission:   bool
    has_obligation:   bool
    verdict:          AxiomVerdict
    principle_ids:    list   # which principles this maps to
    explanation:      str
 
    def to_tool_result(self) -> str:
        lines = [
            f"Action: {self.action}",
            f"Principles: {self.principle_ids}",
            f"pow (institutionalised power): {self.has_power}",
            f"per (permission): {self.has_permission}",
            f"obl (obligation): {self.has_obligation}",
            f"Verdict: {self.verdict.value}",
            f"Explanation: {self.explanation}",
        ]
        return "\n".join(lines)