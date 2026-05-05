from dataclasses import dataclass, field

@dataclass
class AgentFlags:
    # Member behaviours (all agents)
    vote:        bool = False   # vote on raMethod
    demand:      bool = False   # how much to demand
    appropriate: bool = False   # how much to appropriate
    appeal:      bool = False   # whether to appeal sanction
 
    # Head role duties
    allocate:    bool = False   # how to allocate resources
    sanction:    bool = False   # what sanction to apply
 
    # Monitor role duties
    monitor:     bool = False   # whether to report a violation
 
    # Gatekeeper role duties
    exclude:     bool = False   # whether to exclude an agent

HARDCODED_FLAGS = AgentFlags()

def llm_member_flags() -> AgentFlags:
    """LLM for all member behaviours, hardcoded for role duties."""
    return AgentFlags(vote=True, demand=True, appropriate=True, appeal=True)
 
def llm_head_flags() -> AgentFlags:
    """LLM for member behaviours + head duties."""
    return AgentFlags(
        vote=True, demand=True, appropriate=True, appeal=True,
        allocate=True, sanction=True,
    )
 
def llm_monitor_flags() -> AgentFlags:
    """LLM for member behaviours + monitor duties."""
    return AgentFlags(
        vote=True, demand=True, appropriate=True, appeal=True,
        monitor=True,
    )
 
def llm_gatekeeper_flags() -> AgentFlags:
    """LLM for member behaviours + gatekeeper duties."""
    return AgentFlags(
        vote=True, demand=True, appropriate=True, appeal=True,
        exclude=True,
    )
 
def llm_all_flags() -> AgentFlags:
    """LLM for everything."""
    return AgentFlags(
        vote=True, demand=True, appropriate=True, appeal=True,
        allocate=True, sanction=True, monitor=True, exclude=True,
    )
 