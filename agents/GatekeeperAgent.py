import logging
from .InstitutionalAgent import InstitutionalAgent
from enums import AgentRole, AgentStatus
from models import AgentFlags, InstitutionConfig, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags, llm_all_flags, HARDCODED_FLAGS
from utils import _hc_exclude, decide_exclude

_log = logging.getLogger("axioms.agent.gatekeeper")

class GatekeeperAgent(InstitutionalAgent):

    def __init__(self, unique_id, model, compliance_degree=1.0,
                 flags=None, llm_client=None):
        super().__init__(
            unique_id=unique_id, model=model,
            role=AgentRole.GATEKEEPER, status=AgentStatus.ACTIVE_MEMBER,
            compliance_degree=compliance_degree,
            flags=flags or AgentFlags(), llm_client=llm_client,
        )
        _log.debug("GatekeeperAgent %d created.", unique_id)

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
            should_exclude = decide_exclude(self.llm_client, ctx)
        else:
            should_exclude = _hc_exclude(
                agent.sanction_level, config.ex_sanction_level
            )

        if should_exclude:
            agent.status = AgentStatus.ACTIVE_NONMEMBER
            _log.info(
                "Step %d: Gatekeeper EXCLUDED agent %d "
                "(sanction_level=%d offences=%d).",
                self.model.step_count, agent.unique_id,
                agent.sanction_level, agent.offences,
            )
            event = (
                f"Step {self.model.step_count}: EXCLUDED from institution. "
                f"Sanction level {agent.sanction_level}, offences {agent.offences}."
            )
            agent._log_event(event)
            if self.llm_client:
                self.llm_client.mem_add(event, user_id=f"agent_{agent.unique_id}")
        else:
            agent.sanction_level           = config.ex_sanction_level - 1
            agent.status                   = AgentStatus.INACTIVE_MEMBER
            agent.sanction_remaining_steps = config.sanction_durations.get(
                agent.sanction_level, 15
            )
            _log.info(
                "Step %d: Gatekeeper spared agent %d — set inactive "
                "(sanction_level=%d, duration=%d).",
                self.model.step_count, agent.unique_id,
                agent.sanction_level, agent.sanction_remaining_steps,
            )
            event = (
                f"Step {self.model.step_count}: exclusion triggered but spared. "
                f"Inactive for {agent.sanction_remaining_steps} steps "
                f"(sanction_level={agent.sanction_level})."
            )
            agent._log_event(event)
            if self.llm_client:
                self.llm_client.mem_add(event, user_id=f"agent_{agent.unique_id}")
