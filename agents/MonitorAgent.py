from .InstitutionalAgent import InstitutionalAgent
from enums import AgentRole, AgentStatus
from models import AgentFlags, InstitutionConfig, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags, llm_all_flags, HARDCODED_FLAGS
from utils import _hc_report
import random
# ---------------------------------------------------------------------------
# Monitor Agent
# ---------------------------------------------------------------------------
 
class MonitorAgent(InstitutionalAgent):
 
    def __init__(self, unique_id, model, compliance_degree=1.0,
                 flags=None, llm_client=None):
        super().__init__(
            unique_id=unique_id, model=model,
            role=AgentRole.MONITOR, status=AgentStatus.ACTIVE_MEMBER,
            compliance_degree=compliance_degree,
            flags=flags or AgentFlags(), llm_client=llm_client,
        )
        self.observed_noncompliance_rate: float = 0.0
 
    def monitor_stage(self):
        config     = self.model.config
        members    = [
            a for a in self.model.schedule.agents
            if isinstance(a, InstitutionalAgent) and a.is_member
        ]
        nonmembers = [
            a for a in self.model.schedule.agents
            if isinstance(a, InstitutionalAgent) and
            a.status == AgentStatus.ACTIVE_NONMEMBER
        ]
 
        n_sample = max(1, int(len(members) * config.monitoring_freq))
        sampled  = random.sample(members, min(n_sample, len(members)))
        violations = 0
 
        for agent in sampled:
            self.model.resource_pool -= config.monitoring_cost
 
            if self.flags.monitor and self.llm_client:
                ctx = {
                    **self._ctx(),
                    "target_agent_id":    agent.unique_id,
                    "target_appropriated": agent.appropriated,
                    "target_allocated":   agent.allocated,
                    "target_offences":    agent.offences,
                    "target_status":      agent.status.value,
                    "offences":           agent.offences,
                    "sanction_level":     agent.sanction_level,
                    "steps_since_offence": agent.steps_since_offence,
                    "demanded":           agent.demanded,
                    "allocated":          agent.allocated,
                    "agent_status":       agent.status.value,
                }
                should_report = self.llm_client.decide_report(ctx)
            else:
                should_report = _hc_report(agent.appropriated, agent.allocated)
 
            if should_report:
                self.model.reported_violations.add(agent.unique_id)
                violations += 1
 
        if sampled:
            self.observed_noncompliance_rate = (
                0.8 * self.observed_noncompliance_rate +
                0.2 * (violations / len(sampled))
            )
        self.model._noncompliance_rate = self.observed_noncompliance_rate
 
        # Boundary monitoring — always hardcoded
        n_out    = max(1, int(len(nonmembers) * config.monitoring_freq_out))
        samp_out = random.sample(nonmembers, min(n_out, len(nonmembers)))
        for agent in samp_out:
            self.model.resource_pool -= config.monitoring_cost_out
            if agent.appropriated > 0:
                agent.status = AgentStatus.INACTIVE_NONMEMBER
