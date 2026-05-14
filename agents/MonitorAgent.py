import logging
import random
from .InstitutionalAgent import InstitutionalAgent
from enums import AgentRole, AgentStatus
from models import AgentFlags, InstitutionConfig, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags, llm_all_flags, HARDCODED_FLAGS
from utils import _hc_report, decide_report

_log = logging.getLogger("axioms.agent.monitor")

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
        _log.debug("MonitorAgent %d created.", unique_id)

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
            _log.debug(
                "Step %d: Monitor sampling agent %d — "
                "appropriated=%.2f allocated=%.2f",
                self.model.step_count, agent.unique_id,
                agent.appropriated, agent.allocated,
            )
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
                should_report = decide_report(self.llm_client, ctx)
            else:
                should_report = _hc_report(agent.appropriated, agent.allocated)

            if should_report:
                self.model.reported_violations.add(agent.unique_id)
                violations += 1
                _log.warning(
                    "Step %d: Monitor reports agent %d — "
                    "appropriated=%.2f allocated=%.2f",
                    self.model.step_count, agent.unique_id,
                    agent.appropriated, agent.allocated,
                )

        if sampled:
            self.observed_noncompliance_rate = (
                0.8 * self.observed_noncompliance_rate +
                0.2 * (violations / len(sampled))
            )
        self.model._noncompliance_rate = self.observed_noncompliance_rate

        _log.debug(
            "Step %d: Monitor sampled %d members, found %d violations "
            "(noncompliance_rate=%.3f).",
            self.model.step_count, len(sampled), violations,
            self.observed_noncompliance_rate,
        )

        # Boundary monitoring — always hardcoded
        n_out    = max(1, int(len(nonmembers) * config.monitoring_freq_out))
        samp_out = random.sample(nonmembers, min(n_out, len(nonmembers)))
        boundary_exclusions = 0
        for agent in samp_out:
            self.model.resource_pool -= config.monitoring_cost_out
            if agent.appropriated > 0:
                agent.status = AgentStatus.INACTIVE_NONMEMBER
                boundary_exclusions += 1
                _log.info(
                    "Step %d: Non-member agent %d caught appropriating (%.2f) — "
                    "set inactive.",
                    self.model.step_count, agent.unique_id, agent.appropriated,
                )
        if boundary_exclusions:
            _log.info(
                "Step %d: Boundary monitoring excluded %d non-member(s).",
                self.model.step_count, boundary_exclusions,
            )
