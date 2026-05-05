import mesa
import random
from typing import Optional
from enums import AgentRole, AgentStatus, RAMethod
from models import AgentFlags, Institution, InstitutionConfig, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags, llm_all_flags, HARDCODED_FLAGS
from LLMClient import LLMClient
from utils import _hc_vote, _hc_demand, _hc_appropriate, _hc_appeal, _hc_allocate, _hc_sanction, _hc_exclude

# ---------------------------------------------------------------------------
# Base institutional agent
# ---------------------------------------------------------------------------
 
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
 
        # Fluents — Table III
        self.demanded:                 float = 0.0
        self.allocated:                float = 0.0
        self.appropriated:             float = 0.0
        self.sanction_level:           int   = 0
        self.offences:                 int   = 0
        self.sanction_remaining_steps: int   = 0
        self.steps_since_offence:      int   = 0
        self.has_voted_this_round:     bool  = False
 
    @property
    def is_active_member(self):
        return self.status == AgentStatus.ACTIVE_MEMBER
 
    @property
    def is_member(self):
        return self.status in (
            AgentStatus.ACTIVE_MEMBER, AgentStatus.INACTIVE_MEMBER
        )
 
    def _ctx(self) -> dict:
        """Full context for hardcoded helpers and LLM tool calls."""
        return {
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
            # voting context
            "ballot_open":              True,
            "ballot_closed":            False,
            "agent_has_voted_this_round": self.has_voted_this_round,
            "n_votes_cast":             len(self.model.vote_queue),
            # monitoring context
            "monitoring_freq":              self.model.config.monitoring_freq,
            "monitoring_freq_steps":        1,
            "steps_since_last_report":      1,
            "observed_noncompliance_rate":  getattr(
                self.model, "_noncompliance_rate", 0.0
            ),
        }
 
    # Member stages
 
    def vote_stage(self):
        self.has_voted_this_round = False
        if not self.is_active_member:
            return
        ctx  = self._ctx()
        vote = (
            self.llm_client.decide_vote(ctx)
            if self.flags.vote and self.llm_client
            else _hc_vote(ctx)
        )
        self.model.vote_queue.append(vote)
        self.has_voted_this_round = True
 
    def demand_stage(self):
        self.demanded = 0.0
        if not self.is_active_member:
            return
        ctx = self._ctx()
        self.demanded = (
            self.llm_client.decide_demand(ctx)
            if self.flags.demand and self.llm_client
            else _hc_demand(ctx)
        )
        self.demanded = max(0.0, self.demanded)
        self.model.demand_queue.append((self.unique_id, self.demanded))
 
    def appropriate_stage(self):
        self.appropriated = 0.0
        if self.status == AgentStatus.ACTIVE_NONMEMBER:
            if self.compliance_degree < 1.0:
                self.appropriated = (
                    self.model.config.queue_demand_mean * random.uniform(0, 0.5)
                )
            return
        if not self.is_active_member:
            return
        ctx = self._ctx()
        self.appropriated = (
            self.llm_client.decide_appropriate(ctx)
            if self.flags.appropriate and self.llm_client
            else _hc_appropriate(ctx)
        )
        self.appropriated = max(0.0, min(self.appropriated, self.model.resource_pool))
 
    def sanction_tick_stage(self):
        if self.status == AgentStatus.INACTIVE_MEMBER:
            self.sanction_remaining_steps -= 1
            if self.sanction_remaining_steps <= 0:
                self.status         = AgentStatus.ACTIVE_MEMBER
                self.sanction_level = 0
        if self.status == AgentStatus.ACTIVE_MEMBER:
            self.steps_since_offence += 1
 
    def appeal_stage(self):
        if self.status != AgentStatus.INACTIVE_MEMBER or self.sanction_level == 0:
            return
        ctx = self._ctx()
        will_appeal = (
            self.llm_client.decide_appeal(ctx)
            if self.flags.appeal and self.llm_client
            else _hc_appeal(ctx)
        )
        if will_appeal:
            self.model.head_agent.process_appeal(self)
 
    # Role stubs
    def allocate_stage(self):  pass
    def monitor_stage(self):   pass
    def sanction_stage(self):  pass
    def exclude_stage(self):   pass