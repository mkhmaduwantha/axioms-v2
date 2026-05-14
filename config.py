import os

USE_RULE_BASED_DEMAND = True
API_KEY    = os.environ.get("OLLAMA_API_KEY", "NOT FOUND")
# BASE_URL   = "https://ollama.com/v1"
BASE_URL   = "http://host.docker.internal:11434/v1"  # For local Ollama server
MODEL_NAME = "gpt-oss:20b"

# Ollama cloud free-tier rate limit (requests per minute).
# Set to 0 to disable rate limiting.
RATE_LIMIT_RPM = int(os.environ.get("RATE_LIMIT_RPM", "0"))

# Set to False to skip axiom tool calls — LLM decides directly from context.
USE_TOOL_CALLING = os.environ.get("USE_TOOL_CALLING", "true").lower() != "false"

# Replenishment phase sequence — repeats with % len.
# Each entry is 50 steps long.  "moderate" = medium.
WORLD_DESCRIPTION = """\
═══════════════════════════════════════════════
THE WORLD
═══════════════════════════════════════════════

There is a shared resource pool (like a water reservoir).
The pool has a maximum capacity of 10,000 units.
The pool starts full at 10,000 units.
All agents share this single pool.

If the pool hits 0, the institution collapses and everyone gets nothing.
If all members are excluded, the institution collapses.

═══════════════════════════════════════════════
TIME
═══════════════════════════════════════════════

The simulation runs in timeslices (rounds).
Each round, the following happens in order:
  1. Vote on how to allocate resources
  2. Demand resources
  3. Receive allocation
  4. Appropriate (take) resources
  5. Get monitored
  6. Receive sanctions if you violated rules
  7. Appeal sanctions if you think they are unfair
  8. Pool gets replenished

═══════════════════════════════════════════════
REPLENISHMENT
═══════════════════════════════════════════════

At the end of every round the pool is partially refilled.
The refill rate changes every few rounds:
  - High period:     pool refills by a large amount (>4,500 units)
  - Moderate period: pool refills by a medium amount (~4,000 units)
  - Low period:      pool refills by a small amount (~3,000 units)

The pool can never exceed 10,000 units.
You cannot control or predict the refill rate — it is set by the environment.\
"""

REPLENISHMENT_PATTERN = [
    "high", "high", "moderate", "low",
    "high", "high", "low", "moderate", "low", "high",
]

COMPLIANCE_PROFILES = {
    "fully_compliant": (
        "You are a fully cooperative member of this institution. "
        "You always appropriate exactly your allocation and never take more. "
        "You believe the institution's rules are fair and follow them strictly."
    ),
    "unintentional": (
        "You are a cooperative member who genuinely tries to follow the rules "
        "but sometimes misjudges the pool size or your allocation. "
        "You never intend to violate but occasionally make errors."
    ),
    "mildly_noncompliant": (
        "You are a self-interested member who generally follows the rules "
        "but will opportunistically take slightly more than your allocation "
        "when you think the risk of detection is low. "
        "You weigh short-term gain against sanction risk."
    ),
    "noncompliant": (
        "You are a self-interested, opportunistic member. "
        "You routinely attempt to appropriate more than your allocation "
        "when you believe you can get away with it. "
        "You treat sanctions as a cost of doing business."
    ),
}

def _compliance_profile(compliance_degree: float) -> str:
    if compliance_degree >= 1.0:
        return COMPLIANCE_PROFILES["fully_compliant"]
    elif compliance_degree >= 0.95:
        return COMPLIANCE_PROFILES["unintentional"]
    elif compliance_degree >= 0.88:
        return COMPLIANCE_PROFILES["mildly_noncompliant"]
    else:
        return COMPLIANCE_PROFILES["noncompliant"]

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
 