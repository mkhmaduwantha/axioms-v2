from .InstitutionalAgent import InstitutionalAgent
from enums import AgentRole, AgentStatus
from models import AgentFlags, InstitutionConfig, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags, llm_all_flags, HARDCODED_FLAGS
from utils import _hc_exclude

# ---------------------------------------------------------------------------
# Gatekeeper Agent
# ---------------------------------------------------------------------------
 
class GatekeeperAgent(InstitutionalAgent):
 
    def __init__(self, unique_id, model, compliance_degree=1.0,
                 flags=None, llm_client=None):
        super().__init__(
            unique_id=unique_id, model=model,
            role=AgentRole.GATEKEEPER, status=AgentStatus.ACTIVE_MEMBER,
            compliance_degree=compliance_degree,
            flags=flags or AgentFlags(), llm_client=llm_client,
        )
 
    def process_exclusion(self, agent: "InstitutionalAgent"):
        config = self.model.config
        if self.flags.exclude and self.llm_client:
            ctx = {
                **self._ctx(),
                "target_agent_id":            agent.unique_id,
                "target_offences":            agent.offences,
                "target_sanction_level":      agent.sanction_level,
                "target_steps_since_offence": agent.steps_since_offence,
                "target_has_appealed":        False,
                "target_applied":             False,
                "target_status":              agent.status.value,
                "offences":                   agent.offences,
                "sanction_level":             agent.sanction_level,
                "steps_since_offence":        agent.steps_since_offence,
            }
            should_exclude = self.llm_client.decide_exclude(ctx)
        else:
            should_exclude = _hc_exclude(
                agent.sanction_level, config.ex_sanction_level
            )
 
        if should_exclude:
            agent.status = AgentStatus.ACTIVE_NONMEMBER
        else:
            agent.sanction_level           = config.ex_sanction_level - 1
            agent.status                   = AgentStatus.INACTIVE_MEMBER
            agent.sanction_remaining_steps = config.sanction_durations.get(
                agent.sanction_level, 15
            )