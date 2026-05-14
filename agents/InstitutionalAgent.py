import logging
import mesa
import random
from typing import Optional
from enums import AgentRole, AgentStatus, RAMethod
from models import AgentFlags, Institution, InstitutionConfig, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags, llm_all_flags, HARDCODED_FLAGS
from LLMClient import LLMClient
from config import _compliance_profile, WORLD_DESCRIPTION
from utils import _hc_vote, _hc_demand, _hc_appropriate, _hc_appeal, _hc_allocate, _hc_sanction, _hc_exclude, _hc_report, decide_vote, decide_demand, decide_appropriate, decide_appeal, decide_allocation, decide_sanction, decide_exclude, decide_report

_log = logging.getLogger("axioms.agent")

class InstitutionalAgent(mesa.Agent):

    def __init__(
        self,
        unique_id:         int,
        model,
        role:              AgentRole            = AgentRole.MEMBER,
        status:            AgentStatus          = AgentStatus.ACTIVE_MEMBER,
        compliance_degree: float                = 1.0,
        flags:             Optional[AgentFlags] = None,
        llm_client:        Optional[LLMClient]  = None,
    ):
        super().__init__(unique_id, model)
        self.role              = role
        self.status            = status
        self.compliance_degree = compliance_degree
        self.flags             = flags or AgentFlags()
        self.llm_client        = llm_client
        self.system_prompt     = (
            f"{WORLD_DESCRIPTION}\n\n"
            f"You are agent_{unique_id} in a common-pool resource institution.\n"
            f"{_compliance_profile(compliance_degree)}\n"
            "You may call check_ostrom_axiom before any decision."
        )

        # Fluents — Table III
        self.demanded:                 float = 0.0
        self.allocated:                float = 0.0
        self.appropriated:             float = 0.0
        self.sanction_level:           int   = 0
        self.offences:                 int   = 0
        self.sanction_remaining_steps: int   = 0
        self.steps_since_offence:      int   = 0
        self.has_voted_this_round:     bool  = False

        # Short-term in-memory history (last 8 events, always available to LLM)
        self.event_log:                list  = []

    def _log_event(self, text: str):
        """Append an event to this agent's short-term history (capped at 8 entries)."""
        self.event_log.append(text)
        if len(self.event_log) > 8:
            self.event_log.pop(0)

    @property
    def is_active_member(self):
        return self.status == AgentStatus.ACTIVE_MEMBER

    @property
    def is_member(self):
        return self.status in (
            AgentStatus.ACTIVE_MEMBER, AgentStatus.INACTIVE_MEMBER
        )

    def _ctx(self) -> dict:
        return {
            "agent_id":            self.unique_id,
            "system_prompt":       self.system_prompt,
            "recent_history":      "\n".join(self.event_log) if self.event_log else "",
            "agent_status":        self.status.value,
            "agent_role":          self.role.value,
            "sanction_level":      self.sanction_level,
            "offences":            self.offences,
            "steps_since_offence": self.steps_since_offence,
            "compliance_degree":   self.compliance_degree,
            "demanded":            self.demanded,
            "allocated":           self.allocated,
            "resource_pool":       self.model.resource_pool,
            "p_max":               self.model.config.p_max,
            "n_active_members":    self.model.count_active_members(),
            "ra_method":           self.model.institution.ra_method.value,
            "ex_sanction_level":   self.model.config.ex_sanction_level,
            "appeal_window":       self.model.config.appeal_window,
            "queue_demand_mean":   self.model.config.queue_demand_mean,
            "ac_method":           self.model.config.ac_method,
            "ex_method":           self.model.config.ex_method,
            "adr_method":          "arb",
            "ballot_open":              True,
            "ballot_closed":            False,
            "agent_has_voted_this_round": self.has_voted_this_round,
            "n_votes_cast":             len(self.model.vote_queue),
            "monitoring_freq":              self.model.config.monitoring_freq,
            "monitoring_freq_steps":        1,
            "steps_since_last_report":      1,
            "observed_noncompliance_rate":  getattr(
                self.model, "_noncompliance_rate", 0.0
            ),
        }

    def vote_stage(self):
        self.has_voted_this_round = False
        if not self.is_active_member:
            return
        ctx  = self._ctx()
        vote = (
            decide_vote(self.llm_client, ctx)
            if self.flags.vote and self.llm_client
            else _hc_vote(ctx)
        )
        self.model.vote_queue.append(vote)
        self.has_voted_this_round = True
        vote_val = vote.value if hasattr(vote, "value") else vote
        _log.debug(
            "Step %d: Agent %d voted %s.",
            self.model.step_count, self.unique_id, vote_val,
        )
        self._log_event(
            f"Step {self.model.step_count}: voted {vote_val} "
            f"(pool={self.model.resource_pool:.4f}, method_at_vote={self.model.institution.ra_method.value})."
        )

    def demand_stage(self):
        self.demanded = 0.0
        if not self.is_active_member:
            return
        # 90% participation rate in queue mode — mirrors paper behaviour for all agents
        if (self.model.institution.ra_method == RAMethod.QUEUE
                and random.random() >= 0.90):
            self.model.demand_queue.append((self.unique_id, 0.0))
            _log.debug(
                "Step %d: Agent %d abstained from demand (10%% abstention).",
                self.model.step_count, self.unique_id,
            )
            return
        ctx = self._ctx()
        self.demanded = (
            decide_demand(self.llm_client, ctx)
            if self.flags.demand and self.llm_client
            else _hc_demand(ctx)
        )
        self.demanded = max(0.0, self.demanded)
        self.model.demand_queue.append((self.unique_id, self.demanded))
        _log.debug(
            "Step %d: Agent %d demanded %.4f.",
            self.model.step_count, self.unique_id, self.demanded,
        )
        self._log_event(
            f"Step {self.model.step_count}: demanded {self.demanded:.4f} "
            f"(pool={self.model.resource_pool:.1f}, method={self.model.institution.ra_method.value})."
        )

    def appropriate_stage(self):
        self.appropriated = 0.0
        if self.status == AgentStatus.ACTIVE_NONMEMBER:
            if self.compliance_degree < 1.0:
                self.appropriated = (
                    self.model.config.queue_demand_mean * random.uniform(0, 0.5)
                )
                if self.appropriated > 0:
                    _log.debug(
                        "Step %d: Non-member agent %d appropriated %.2f (non-compliant).",
                        self.model.step_count, self.unique_id, self.appropriated,
                    )
            return
        if not self.is_active_member:
            return
        ctx = self._ctx()
        self.appropriated = (
            decide_appropriate(self.llm_client, ctx)
            if self.flags.appropriate and self.llm_client
            else _hc_appropriate(ctx)
        )
        self.appropriated = max(0.0, min(self.appropriated, self.model.resource_pool))
        tolerance = 1e-6
        violated = self.appropriated > self.allocated + tolerance
        if violated:
            _log.warning(
                "Step %d: Agent %d over-appropriated: took=%.4f allocated=%.4f.",
                self.model.step_count, self.unique_id, self.appropriated, self.allocated,
            )
        event = (
            f"Step {self.model.step_count}: demanded {self.demanded:.4f}, "
            f"allocated {self.allocated:.4f}, appropriated {self.appropriated:.4f}. "
            f"{'VIOLATION' if violated else 'Compliant'}. "
            f"Sanction level: {self.sanction_level}."
        )
        self._log_event(event)
        if self.llm_client and self.flags.appropriate:
            self.llm_client.mem_add(event, user_id=f"agent_{self.unique_id}")

    def sanction_tick_stage(self):
        if self.status == AgentStatus.INACTIVE_MEMBER:
            self.sanction_remaining_steps -= 1
            if self.sanction_remaining_steps <= 0:
                self.status         = AgentStatus.ACTIVE_MEMBER
                self.sanction_level = 0
                _log.info(
                    "Step %d: Agent %d sanction expired — restored to active.",
                    self.model.step_count, self.unique_id,
                )
                self._log_event(
                    f"Step {self.model.step_count}: sanction expired, restored to active member."
                )
        if self.status == AgentStatus.ACTIVE_MEMBER:
            self.steps_since_offence += 1

    def appeal_stage(self):
        if self.status != AgentStatus.INACTIVE_MEMBER or self.sanction_level == 0:
            return
        ctx = self._ctx()
        will_appeal = (
            decide_appeal(self.llm_client, ctx)
            if self.flags.appeal and self.llm_client
            else _hc_appeal(ctx)
        )
        if will_appeal:
            _log.info(
                "Step %d: Agent %d appealing sanction (level=%d, clean_steps=%d).",
                self.model.step_count, self.unique_id,
                self.sanction_level, self.steps_since_offence,
            )
            self._log_event(
                f"Step {self.model.step_count}: filed appeal "
                f"(sanction_level={self.sanction_level}, clean_steps={self.steps_since_offence})."
            )
            self.model.head_agent.process_appeal(self)

    # Role stubs
    def allocate_stage(self):  pass
    def monitor_stage(self):   pass
    def sanction_stage(self):  pass
    def exclude_stage(self):   pass
