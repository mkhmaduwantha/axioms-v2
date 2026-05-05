import os

USE_RULE_BASED_DEMAND = True
API_KEY = os.environ.get("OLLAMA_API_KEY", "NOT FOUND")
BASE_URL = "https://ollama.com/v1"
MODEL_NAME = "gpt-oss:20b-cloud"

OSTROM_PRINCIPLES = {
    1: (
        "Clearly defined boundaries: Those who have rights to appropriate from the CPR "
        "are clearly defined, as are its boundaries. Non-members are not permitted to "
        "appropriate resources. The gatekeeper controls membership admission and exclusion."
    ),
    2: (
        "Congruence between appropriation/provision rules and local environment: "
        "The allocation method (queue or ration) should match the resource level. "
        "Use ration when pool < 75% of maximum, queue when plentiful. "
        "Agents must not appropriate beyond their allocation."
    ),
    3: (
        "Collective-choice arrangements: Those affected by the operational rules "
        "participate in selecting and modifying those rules through voting. "
        "Members vote on the resource allocation method (raMethod). "
        "The head must declare the result honestly according to plurality vote."
    ),
    4: (
        "Monitoring: Monitoring of both resource state and appropriator behaviour "
        "is by appointed agents who are accountable to the appropriators or are "
        "appropriators themselves. The monitor must report violations to the head. "
        "Monitoring frequency should be calibrated to the compliance level of the population."
    ),
    5: (
        "Graduated sanctions: Resource appropriators who violate communal rules "
        "receive graduated sanctions before exclusion. First offence = brief inactivity, "
        "second = longer inactivity, third = exclusion. Sanctions allow agents to "
        "revise their behaviour rather than being immediately removed."
    ),
    6: (
        "Conflict resolution: Sanctioned agents may appeal against sanctions. "
        "The head (as arbiter) upholds the appeal if the agent has had a clean record "
        "for the last 30 steps, decrementing the sanction level and offence count. "
        "This handles unintentional violations fairly."
    ),
}


AXIOM_TOOL = {
    "type": "function",
    "function": {
        "name": "check_ostrom_axiom",
        "description": (
            "Check whether an agent has power (pow), permission (per), or obligation (obl) "
            "to perform a specific institutional action, based on the exact Event Calculus "
            "axioms from Pitt et al. 2012. Returns verdict: PERMITTED, NO_POWER, "
            "NO_PERMISSION, or OBLIGATION_VIOLATED."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "apply",
                        "assign_member",
                        "exclude",
                        "demand",
                        "allocate",
                        "appropriate",
                        "vote",
                        "declare",
                        "report_env",
                        "report_violation",
                        "sanction",
                        "appeal",
                        "uphold",
                    ],
                    "description": "The institutional action to check",
                },
                "planned_appropriation": {
                    "type": "number",
                    "description": "For 'appropriate': the amount the agent plans to take",
                },
            },
            "required": ["action"],
        },
    },
}
 