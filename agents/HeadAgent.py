import logging
from .InstitutionalAgent import InstitutionalAgent
from enums import AgentRole, AgentStatus
from models import AgentFlags, InstitutionConfig, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags, llm_all_flags, HARDCODED_FLAGS
from utils import _hc_allocate, _hc_sanction, decide_allocation, decide_sanction

_log = logging.getLogger("axioms.agent.head")

class HeadAgent(InstitutionalAgent):

    def __init__(self, unique_id, model, compliance_degree=1.0,
                 flags=None, llm_client=None):
        super().__init__(
            unique_id=unique_id, model=model,
            role=AgentRole.HEAD, status=AgentStatus.ACTIVE_MEMBER,
            compliance_degree=compliance_degree,
            flags=flags or AgentFlags(), llm_client=llm_client,
        )
        _log.debug("HeadAgent %d created.", unique_id)

    def allocate_stage(self):
        agent_map = {
            a.unique_id: a for a in self.model.schedule.agents
            if isinstance(a, InstitutionalAgent)
        }
        if self.flags.allocate and self.llm_client:
            ctx = {**self._ctx(), "demand_queue": self.model.demand_queue}
            llm_allocs = decide_allocation(self.llm_client, ctx)
            if llm_allocs:
                _log.debug(
                    "Step %d: Head (LLM) allocated to %d agents.",
                    self.model.step_count, len(llm_allocs),
                )
                for agent_id, amount in llm_allocs.items():
                    agent = agent_map.get(agent_id)
                    if agent:
                        agent.allocated = max(0.0, float(amount))
                return

        allocations = _hc_allocate(
            self.model.demand_queue,
            self.model.resource_pool,
            self.model.institution.ra_method,
        )
        _log.debug(
            "Step %d: Head allocated to %d agents via %s.",
            self.model.step_count, len(allocations), self.model.institution.ra_method.value,
        )
        for agent_id, amount in allocations.items():
            agent = agent_map.get(agent_id)
            if agent:
                agent.allocated = amount

    def sanction_stage(self):
        config    = self.model.config
        agent_map = {
            a.unique_id: a for a in self.model.schedule.agents
            if isinstance(a, InstitutionalAgent)
        }
        for agent_id in list(self.model.reported_violations):
            agent = agent_map.get(agent_id)
            if agent is None:
                continue

            agent.offences           += 1
            agent.steps_since_offence = 0

            if self.flags.sanction and self.llm_client:
                ctx = {
                    **self._ctx(),
                    "target_agent_id":       agent_id,
                    "target_offences":       agent.offences,
                    "target_sanction_level": agent.sanction_level,
                    "target_appropriated":   agent.appropriated,
                    "target_allocated":      agent.allocated,
                    "offences":              agent.offences,
                    "sanction_level":        agent.sanction_level,
                }
                decision = decide_sanction(self.llm_client, ctx)
            else:
                decision = _hc_sanction(agent.offences, config.ex_sanction_level)

            _log.info(
                "Step %d: Head sanctioned agent %d (offences=%d) → decision=%s",
                self.model.step_count, agent_id, agent.offences, decision,
            )

            if decision == "exclude":
                self.model.gatekeeper_agent.process_exclusion(agent)
            else:
                agent.sanction_level           += 1
                duration                        = config.sanction_durations.get(
                    agent.sanction_level, 5
                )
                agent.status                   = AgentStatus.INACTIVE_MEMBER
                agent.sanction_remaining_steps = duration
                _log.info(
                    "Step %d: Agent %d sanctioned to inactive for %d steps "
                    "(sanction_level=%d).",
                    self.model.step_count, agent_id, duration, agent.sanction_level,
                )

        self.model.reported_violations.clear()

    def process_appeal(self, agent: "InstitutionalAgent"):
        # this need to be LLM reasoning decision
        clean = agent.steps_since_offence >= self.model.config.appeal_window
        if clean:
            agent.sanction_level = max(0, agent.sanction_level - 1)
            agent.offences       = max(0, agent.offences - 1)
            if agent.sanction_level == 0:
                agent.status                   = AgentStatus.ACTIVE_MEMBER
                agent.sanction_remaining_steps = 0
            _log.info(
                "Step %d: Appeal UPHELD for agent %d "
                "(clean_steps=%d sanction_level now %d).",
                self.model.step_count, agent.unique_id,
                agent.steps_since_offence, agent.sanction_level,
            )
        else:
            _log.debug(
                "Step %d: Appeal by agent %d REJECTED (clean_steps=%d < window=%d).",
                self.model.step_count, agent.unique_id,
                agent.steps_since_offence, self.model.config.appeal_window,
            )
