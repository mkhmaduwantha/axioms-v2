import logging
import mesa
import random
from typing import Optional

from agents import InstitutionalAgent, HeadAgent, MonitorAgent, GatekeeperAgent
from models import AgentFlags, HARDCODED_FLAGS, Institution, InstitutionConfig, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags, llm_all_flags
from enums import AgentRole, AgentStatus, RAMethod
from LLMClient import llm_client as _default_llm_client

_log = logging.getLogger("axioms.model")

class CPRModel(mesa.Model):

    def __init__(
        self,
        n_members:    int   = 100,
        n_nonmembers: int   = 20,
        n_llm_members: int  = 0,
        head_config:        Optional[dict] = None,
        monitor_config:     Optional[dict] = None,
        gatekeeper_config:  Optional[dict] = None,
        member_llm_flags:   Optional[AgentFlags] = None,
        noncompliant_member_fraction:    float = 0.0,
        noncompliant_nonmember_fraction: float = 0.5,
        unintentional_violation_frac:    float = 0.0,
        use_principle_3: bool = True,
        use_principle_4: bool = True,
        use_principle_5: bool = True,
        use_principle_6: bool = True,
        config: Optional[InstitutionConfig] = None,
    ):
        super().__init__()
        self.config              = config or InstitutionConfig()
        self.institution         = Institution()
        self.resource_pool:float = self.config.p_max
        self.step_count:int      = 0
        self._noncompliance_rate:float = 0.0
        self.use_principle_3     = use_principle_3
        self.use_principle_4     = use_principle_4
        self.use_principle_5     = use_principle_5
        self.use_principle_6     = use_principle_6
        self.demand_queue:list   = []
        self.vote_queue:list     = []
        self.reported_violations:set = set()
        self.schedule            = mesa.time.BaseScheduler(self)

        _log.info(
            "CPRModel init: members=%d nonmembers=%d llm_members=%d "
            "P3=%s P4=%s P5=%s P6=%s",
            n_members, n_nonmembers, n_llm_members,
            use_principle_3, use_principle_4, use_principle_5, use_principle_6,
        )

        hc = head_config       or {}
        mc = monitor_config    or {}
        gc = gatekeeper_config or {}

        needs_llm = any([
            n_llm_members, hc.get("llm"), mc.get("llm"), gc.get("llm")
        ])
        _llm_client = _default_llm_client if needs_llm else None
        if needs_llm:
            _log.info("LLM client attached for simulation (model=%s).", _llm_client.model)

        agent_id = 0
        for i in range(n_members):
            is_llm          = i < n_llm_members
            is_noncompliant = i < int(n_members * noncompliant_member_fraction)
            compliance = 1.0
            if is_noncompliant:
                compliance = random.uniform(0.80, 0.99)
            elif random.random() < unintentional_violation_frac:
                compliance = random.uniform(0.98, 1.05)
            self.schedule.add(InstitutionalAgent(
                unique_id=agent_id, model=self,
                role=AgentRole.MEMBER, status=AgentStatus.ACTIVE_MEMBER,
                compliance_degree=compliance,
                flags=member_llm_flags if is_llm else HARDCODED_FLAGS,
                llm_client=_llm_client if is_llm else None,
            ))
            agent_id += 1

        for i in range(n_nonmembers):
            is_noncompliant = i < int(n_nonmembers * noncompliant_nonmember_fraction)
            self.schedule.add(InstitutionalAgent(
                unique_id=agent_id, model=self,
                role=AgentRole.MEMBER, status=AgentStatus.ACTIVE_NONMEMBER,
                compliance_degree=random.uniform(0.80, 0.99) if is_noncompliant else 1.0,
            ))
            agent_id += 1

        self.head_agent = HeadAgent(
            unique_id=agent_id, model=self,
            compliance_degree=hc.get("compliance_degree", 1.0),
            flags=hc.get("flags", HARDCODED_FLAGS),
            llm_client=_llm_client if hc.get("llm") else None,
        )
        self.schedule.add(self.head_agent)
        agent_id += 1

        self.monitor_agent = MonitorAgent(
            unique_id=agent_id, model=self,
            compliance_degree=mc.get("compliance_degree", 1.0),
            flags=mc.get("flags", HARDCODED_FLAGS),
            llm_client=_llm_client if mc.get("llm") else None,
        )
        self.schedule.add(self.monitor_agent)
        agent_id += 1

        self.gatekeeper_agent = GatekeeperAgent(
            unique_id=agent_id, model=self,
            compliance_degree=gc.get("compliance_degree", 1.0),
            flags=gc.get("flags", HARDCODED_FLAGS),
            llm_client=_llm_client if gc.get("llm") else None,
        )
        self.schedule.add(self.gatekeeper_agent)
        _log.info("All agents created. Total schedule size: %d", len(self.schedule.agents))

        self.datacollector = mesa.DataCollector(
            model_reporters={
                "ResourcePool":  "resource_pool",
                "ActiveMembers": lambda m: m.count_active_members(),
                "Excluded":      lambda m: m.count_excluded(),
                "RAMethod":      lambda m: m.institution.ra_method.value,
                "TotalViolations": lambda m: sum(
                    1 for a in m.schedule.agents
                    if isinstance(a, InstitutionalAgent) and
                    a.appropriated > a.allocated + 0.01
                ),
            },
            agent_reporters={
                "Role":         lambda a: a.role.value   if isinstance(a, InstitutionalAgent) else "n/a",
                "Status":       lambda a: a.status.value if isinstance(a, InstitutionalAgent) else "n/a",
                "Demanded":     lambda a: a.demanded     if isinstance(a, InstitutionalAgent) else 0,
                "Allocated":    lambda a: a.allocated    if isinstance(a, InstitutionalAgent) else 0,
                "Appropriated": lambda a: a.appropriated if isinstance(a, InstitutionalAgent) else 0,
                "Sanction":     lambda a: a.sanction_level if isinstance(a, InstitutionalAgent) else 0,
                "Offences":     lambda a: a.offences    if isinstance(a, InstitutionalAgent) else 0,
            },
        )

    def count_active_members(self) -> int:
        return sum(
            1 for a in self.schedule.agents
            if isinstance(a, InstitutionalAgent) and a.is_active_member
        )

    def count_excluded(self) -> int:
        return sum(
            1 for a in self.schedule.agents
            if isinstance(a, InstitutionalAgent) and
            a.status == AgentStatus.ACTIVE_NONMEMBER
        )

    def _declare_ra_method(self):
        if self.use_principle_3 and self.vote_queue:
            q = self.vote_queue.count(RAMethod.QUEUE)
            r = self.vote_queue.count(RAMethod.RATION)
            new_method = RAMethod.QUEUE if q > r else RAMethod.RATION
            if new_method != self.institution.ra_method:
                _log.info(
                    "Step %d: RA method changed %s → %s (votes: queue=%d ration=%d)",
                    self.step_count, self.institution.ra_method.value,
                    new_method.value, q, r,
                )
            self.institution.ra_method = new_method
        elif not self.use_principle_3 and self.step_count % 50 == 0:
            self.institution.ra_method = (
                RAMethod.QUEUE
                if self.resource_pool >= 0.75 * self.config.p_max
                else RAMethod.RATION
            )
            _log.debug(
                "Step %d: RA method auto-set to %s (pool=%.0f)",
                self.step_count, self.institution.ra_method.value, self.resource_pool,
            )

    def _current_refill(self) -> float:
        phase = (self.step_count // 50) % 3
        return self.config.p_max * [
            self.config.replenishment_moderate,
            self.config.replenishment_low,
            self.config.replenishment_high,
        ][phase]

    def step(self):
        self.step_count  += 1
        self.demand_queue = []
        self.vote_queue   = []
        all_agents        = list(self.schedule.agents)

        for a in all_agents:    a.vote_stage()
        self._declare_ra_method()
        for a in all_agents:    a.demand_stage()
        self.head_agent.allocate_stage()
        for a in all_agents:    a.appropriate_stage()

        total_appropriated = sum(
            a.appropriated for a in all_agents if isinstance(a, InstitutionalAgent)
        )
        self.resource_pool -= total_appropriated

        if self.use_principle_4:
            self.monitor_agent.monitor_stage()
            if not self.use_principle_5:
                for agent_id in list(self.reported_violations):
                    agent = next(
                        (a for a in all_agents if a.unique_id == agent_id), None
                    )
                    if agent:
                        self.gatekeeper_agent.process_exclusion(agent)
                self.reported_violations.clear()
            else:
                self.head_agent.sanction_stage()

        for a in all_agents:    a.sanction_tick_stage()

        if self.use_principle_6 and self.use_principle_4:
            for a in all_agents:    a.appeal_stage()

        refill = self._current_refill()
        self.resource_pool = min(self.config.p_max, self.resource_pool + refill)
        self.datacollector.collect(self)

        violations = sum(
            1 for a in all_agents
            if isinstance(a, InstitutionalAgent) and a.appropriated > a.allocated + 0.01
        )
        _log.info(
            "Step %4d | pool=%7.1f | members=%d | violations=%d | "
            "noncompliance_rate=%.2f | ra=%s",
            self.step_count, self.resource_pool,
            self.count_active_members(), violations,
            self._noncompliance_rate,
            self.institution.ra_method.value,
        )
        if violations > 0:
            _log.warning(
                "Step %d: %d violation(s) detected this step.", self.step_count, violations
            )

    def run(self, max_steps: int = 500) -> dict:
        _log.info("Simulation run starting: max_steps=%d", max_steps)
        for _ in range(max_steps):
            if self.resource_pool <= 0:
                _log.warning(
                    "Resource pool depleted at step %d. Simulation ending.", self.step_count
                )
                break
            if self.count_active_members() == 0:
                _log.warning(
                    "No active members at step %d. Simulation ending.", self.step_count
                )
                break
            self.step()

        result = {
            "lifespan":       self.step_count,
            "final_resource": self.resource_pool,
            "final_members":  self.count_active_members(),
            "model_df":       self.datacollector.get_model_vars_dataframe(),
            "agent_df":       self.datacollector.get_agent_vars_dataframe(),
        }
        _log.info(
            "Simulation complete: lifespan=%d final_pool=%.1f final_members=%d",
            result["lifespan"], result["final_resource"], result["final_members"],
        )
        return result
