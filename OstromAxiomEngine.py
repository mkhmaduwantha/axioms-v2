import functools
import logging
from enums import AgentRole, AgentStatus, RAMethod, AxiomVerdict
from models import AxiomResult

_log = logging.getLogger("axioms.engine")

class OstromAxiomEngine:
    """
    Implements the exact EC axioms from Pitt et al. 2012, Section 5.3.
 
    Principle 1 — Clearly defined boundaries (Section 5.3.1)
    =========================================================
    apply(A, I) — agent can apply to join:
        pow(A, apply(A,I)) ← role_of(A, member, I) = false
 
    assign(G, A, member, I) — gatekeeper admits agent:
        pow(G, assign) ← applied(A,I)=true ∧ acMethod=attribute ∧
                          role_of(G,gatekeeper,I) ∧ role_conditions(A,I)
        pow(G, assign) ← applied(A,I)=true ∧ acMethod=discretionary ∧
                          role_of(G,gatekeeper,I)
 
    exclude(G, A, member, I) — gatekeeper excludes agent:
        pow(G, exclude) ← role_of(G,gatekeeper,I) ∧ exMethod=discretionary
        pow(G, exclude) ← role_of(G,gatekeeper,I) ∧ exMethod=jury ∧
                           ballot(exclude(A),I)=V ∧ winner_determination(WDM,V,true)
        per(G, exclude) ← role_of(G,gatekeeper,I) ∧
                           sanction_level(A,I)=S ∧ ex_sanction_level(I)=S
 
    Principle 2 — Congruence (Section 5.3.2)
    =========================================
    demand(A, R, I):
        pow(A, demand) ← role_of(A,member,I) ∧ demanded(A,I)=0 ∧
                          sanction_level(A,I)=0
 
    allocate(C, A, R, I) — head allocates:
        pow(C, allocate(queue))  ← demanded(A,I)=R ∧ demand_q has (A,R) ∧
                                    role_of(C,head,I) ∧ raMethod=queue
        pow(C, allocate(ration)) ← demanded(A,I)=R ∧ demand_q has (A,R) ∧
                                    role_of(C,head,I) ∧ raMethod=ration(R') ∧
                                    ((R>R' ∧ R'=R') ∨ (R≤R' ∧ R'=R))
        obl(C, allocate) ← demanded(A,I)=R ∧ demand_q has (A,R) ∧
                            role_of(C,head,I) ∧ raMethod=queue  [similarly for ration]
 
    appropriate(A, R, I):
        No explicit pow axiom — physical capability.
        Violation = appropriated > allocated (congruence breach).
 
    Principle 3 — Collective choice (Section 5.3.3)
    ================================================
    vote(A, X, M, I):
        pow(A, vote) ← status(M,I)=open ∧ role_of(A,member,I) ∧
                        A not in voted(M,I)
 
    declare(C, W, M, I):
        obl(C, declare) ← role_of(C,head,I) ∧ status(M,I)=closed ∧
                           vote_q(M,I)=Q ∧ winner_determination(WDM,Q,W)
 
    Principle 4 — Monitoring (Section 5.3.4)
    =========================================
    report(B, P, I) — monitor reports resource level:
        pow(B, report_env) ← role_of(B,monitor,I)
        obl(B, report_env) ← role_of(B,monitor,I) ∧
                               reported(B,I)=(_, T') ∧
                               monitoring_frequency(I)=F ∧ T' < T+F
 
    report(B, A, R, I) — monitor reports appropriation violation:
        pow(B, report_violation) ← role_of(B,monitor,I) ∧
                                    role_of(A,member,I)
 
    Principle 5 — Graduated sanctions (Section 5.3.5)
    ==================================================
    sanction(C, A, S, I):
        pow(C, sanction) ← role_of(C,head,I) ∧ offences(A,I)=S
        [sanction_level increases by 1 per offence; exclusion when level=ex_sanction_level]
 
    Principle 6 — Conflict resolution (Section 5.3.6)
    ==================================================
    appeal(A, S, I):
        pow(A, appeal) ← role_of(A,member,I) ∧ sanction_level(A,I)=S
 
    uphold(C, A, S, I):
        pow(C, uphold) ← role_of(C,head,I) ∧ adrMethod=arb ∧
                          appealed(A,S,I)=true
    """

    def __init__(self):
        for _name in [n for n in dir(self) if n.startswith("check_")]:
            _orig = getattr(self, _name)
            @functools.wraps(_orig)
            def _wrapped(*args, _fn=_orig, _action=_name, **kwargs):
                result = _fn(*args, **kwargs)
                _log.debug(
                    "action=%s verdict=%s principles=%s | %s",
                    result.action, result.verdict.value, result.principle_ids, result.explanation,
                )
                return result
            setattr(self, _name, _wrapped)
 
    # ------------------------------------------------------------------
    # Principle 1 axioms
    # ------------------------------------------------------------------
 
    def check_apply(self, ctx: dict) -> AxiomResult:
        """
        pow(A, apply(A,I)) ← role_of(A, member, I) = false
        Agent can apply to join only if NOT already a member.
        """
        is_member = ctx.get("agent_status") in (
            AgentStatus.ACTIVE_MEMBER.value,
            AgentStatus.INACTIVE_MEMBER.value,
        )
        has_power = not is_member
 
        if has_power:
            verdict     = AxiomVerdict.PERMITTED
            explanation = (
                "Agent is not a member so has power to apply (Principle 1). "
                "apply(A,I) initiates applied(A,I)=true."
            )
        else:
            verdict     = AxiomVerdict.NO_POWER
            explanation = (
                "Agent is already a member. "
                "pow(A, apply) requires role_of(A, member, I)=false — not satisfied."
            )
        return AxiomResult("apply", has_power, True, False, verdict, [1], explanation)
 
    def check_assign_member(self, ctx: dict) -> AxiomResult:
        """
        pow(G, assign(G,A,member,I)) ←
            applied(A,I)=true ∧ acMethod=attribute ∧
            role_of(G,gatekeeper,I) ∧ role_conditions(member,A,I)
        OR
            applied(A,I)=true ∧ acMethod=discretionary ∧
            role_of(G,gatekeeper,I)
        """
        is_gatekeeper    = ctx.get("agent_role") == AgentRole.GATEKEEPER.value
        target_applied   = ctx.get("target_applied", False)
        ac_method        = ctx.get("ac_method", "discretionary")
        role_conditions  = ctx.get("target_role_conditions_met", True)
 
        if not is_gatekeeper:
            return AxiomResult(
                "assign_member", False, False, False, AxiomVerdict.NO_POWER, [1],
                "pow(G, assign) requires role_of(G, gatekeeper, I) — agent is not gatekeeper."
            )
        if not target_applied:
            return AxiomResult(
                "assign_member", False, False, False, AxiomVerdict.NO_POWER, [1],
                "pow(G, assign) requires applied(A,I)=true — target has not applied."
            )
        if ac_method == "attribute" and not role_conditions:
            return AxiomResult(
                "assign_member", False, False, False, AxiomVerdict.NO_POWER, [1],
                "acMethod=attribute but role_conditions(member,A,I)=false — "
                "applicant does not meet attribute conditions."
            )
 
        return AxiomResult(
            "assign_member", True, True, False, AxiomVerdict.PERMITTED, [1],
            f"pow(G, assign) holds: gatekeeper, target applied, acMethod={ac_method} "
            f"conditions satisfied."
        )
 
    def check_exclude(self, ctx: dict) -> AxiomResult:
        """
        pow(G, exclude) ←
            role_of(G,gatekeeper,I) ∧ exMethod=discretionary
        OR
            role_of(G,gatekeeper,I) ∧ exMethod=jury ∧ ballot result true
 
        per(G, exclude) ←
            role_of(G,gatekeeper,I) ∧
            sanction_level(A,I)=S ∧ ex_sanction_level(I)=S
        (permission only when sanction level has reached exclusion threshold)
        """
        is_gatekeeper     = ctx.get("agent_role") == AgentRole.GATEKEEPER.value
        ex_method         = ctx.get("ex_method", "discretionary")
        ballot_result     = ctx.get("ballot_result_exclude", False)
        target_sl         = ctx.get("target_sanction_level", 0)
        ex_sl             = ctx.get("ex_sanction_level", 3)
 
        # Power check
        if not is_gatekeeper:
            return AxiomResult(
                "exclude", False, False, False, AxiomVerdict.NO_POWER, [1],
                "pow(G, exclude) requires role_of(G, gatekeeper, I) — not gatekeeper."
            )
        if ex_method == "jury" and not ballot_result:
            return AxiomResult(
                "exclude", False, False, False, AxiomVerdict.NO_POWER, [1],
                "exMethod=jury but ballot(exclude(A),I) has not returned true. "
                "No power to exclude without jury vote."
            )
 
        has_power = True
 
        # Permission check — per(G, exclude) requires sanction_level = ex_sanction_level
        has_permission = target_sl >= ex_sl
        if not has_permission:
            return AxiomResult(
                "exclude", True, False, False, AxiomVerdict.NO_PERMISSION, [1, 5],
                f"pow holds but per(G, exclude) requires sanction_level(A,I)={ex_sl} "
                f"(ex_sanction_level). Current sanction_level={target_sl}. "
                "Graduated sanctions (Principle 5) must be exhausted first."
            )
 
        return AxiomResult(
            "exclude", True, True, False, AxiomVerdict.PERMITTED, [1, 5],
            f"pow and per both hold. exMethod={ex_method}, "
            f"sanction_level={target_sl} = ex_sanction_level={ex_sl}. "
            "Exclusion is permitted."
        )
 
    # ------------------------------------------------------------------
    # Principle 2 axioms
    # ------------------------------------------------------------------
 
    def check_demand(self, ctx: dict) -> AxiomResult:
        """
        pow(A, demand(A,R,I)) ←
            role_of(A, member, I) = true
            ∧ demanded(A,I) = 0        (has not yet demanded this timeslice)
            ∧ sanction_level(A,I) = 0  (not currently sanctioned)
        """
        is_member      = ctx.get("agent_status") == AgentStatus.ACTIVE_MEMBER.value
        already_demanded = ctx.get("demanded", 0) > 0
        sanction_level = ctx.get("sanction_level", 0)
 
        if not is_member:
            return AxiomResult(
                "demand", False, False, False, AxiomVerdict.NO_POWER, [1, 2],
                "pow(A, demand) requires role_of(A, member, I)=true. "
                "Agent is not an active member."
            )
        if already_demanded:
            return AxiomResult(
                "demand", False, False, False, AxiomVerdict.NO_POWER, [2],
                "pow(A, demand) requires demanded(A,I)=0. "
                "Agent has already demanded this timeslice."
            )
        if sanction_level > 0:
            return AxiomResult(
                "demand", False, False, False, AxiomVerdict.NO_POWER, [2, 5],
                f"pow(A, demand) requires sanction_level(A,I)=0. "
                f"Current sanction_level={sanction_level}. "
                "Sanctioned agents lose power to demand (Principle 5)."
            )
 
        return AxiomResult(
            "demand", True, True, False, AxiomVerdict.PERMITTED, [2],
            "pow(A, demand) holds: member, not yet demanded, not sanctioned."
        )
 
    def check_allocate(self, ctx: dict) -> AxiomResult:
        """
        pow(C, allocate(C,A,R,I)) ←
            demanded(A,I)=R ∧ demand_q has (A,R)
            ∧ role_of(C, head, I) = true
            ∧ raMethod(I) = queue  [or ration with appropriate R' calculation]
 
        obl(C, allocate) ← same conditions
        (head is obligated to allocate empowered demands)
        """
        is_head         = ctx.get("agent_role") == AgentRole.HEAD.value
        target_demanded = ctx.get("target_demanded", 0)
        in_demand_queue = ctx.get("target_in_demand_queue", True)
        ra_method       = ctx.get("ra_method", "")
 
        if not is_head:
            return AxiomResult(
                "allocate", False, False, False, AxiomVerdict.NO_POWER, [2],
                "pow(C, allocate) requires role_of(C, head, I). Agent is not head."
            )
        if target_demanded <= 0:
            return AxiomResult(
                "allocate", False, False, False, AxiomVerdict.NO_POWER, [2],
                "pow(C, allocate) requires demanded(A,I)=R with R>0. "
                "Target has not made a demand."
            )
        if not in_demand_queue:
            return AxiomResult(
                "allocate", False, False, False, AxiomVerdict.NO_POWER, [2],
                "pow(C, allocate) requires demand_q(I) to contain (A,R). "
                "Target demand not in queue."
            )
        if ra_method not in (RAMethod.QUEUE.value, RAMethod.RATION.value):
            return AxiomResult(
                "allocate", False, False, False, AxiomVerdict.NO_POWER, [2],
                f"pow(C, allocate) requires a valid raMethod. "
                f"Current raMethod='{ra_method}' not recognised."
            )
 
        # Head is both empowered AND obligated
        return AxiomResult(
            "allocate", True, True, True, AxiomVerdict.PERMITTED, [2],
            f"pow and obl(C, allocate) hold. role=head, raMethod={ra_method}, "
            f"target demanded {target_demanded:.1f} and is in demand queue. "
            "Head is obligated to allocate this demand."
        )
 
    def check_appropriate(self, ctx: dict) -> AxiomResult:
        """
        Appropriation is a PHYSICAL action (no pow axiom in paper).
        However, congruence (Principle 2) creates a normative constraint:
        appropriating > allocated is a VIOLATION detectable by monitor.
 
        The paper tracks this via offences(A,I) incremented by report(B,A,R,I).
        We return:
          - PERMITTED if appropriated <= allocated  (congruent)
          - NO_PERMISSION if appropriated > allocated (violates congruence,
            even though physically possible — per is implicitly bounded by allocation)
        """
        allocated    = ctx.get("allocated", 0)
        to_take      = ctx.get("planned_appropriation", allocated)
        is_member    = ctx.get("agent_status") == AgentStatus.ACTIVE_MEMBER.value
 
        if not is_member:
            return AxiomResult(
                "appropriate", False, False, False, AxiomVerdict.NO_POWER, [1],
                "Appropriation by non-members violates Principle 1 (boundary rules). "
                "Only members have entitlement to appropriate."
            )
 
        congruent = to_take <= allocated + 0.01
        if not congruent:
            return AxiomResult(
                "appropriate", True, False, False, AxiomVerdict.NO_PERMISSION, [2],
                f"Physical capability exists (no pow restriction) but "
                f"per is implicitly bounded by allocation. "
                f"Planned appropriation {to_take:.1f} > allocated {allocated:.1f}. "
                "This violates Principle 2 (congruence) and will be detected by monitor."
            )
 
        return AxiomResult(
            "appropriate", True, True, False, AxiomVerdict.PERMITTED, [2],
            f"Appropriation {to_take:.1f} <= allocated {allocated:.1f}. "
            "Congruent with allocation rule (Principle 2)."
        )
 
    # ------------------------------------------------------------------
    # Principle 3 axioms
    # ------------------------------------------------------------------
 
    def check_vote(self, ctx: dict) -> AxiomResult:
        """
        pow(A, vote(A,X,M,I)) ←
            status(M,I) = open
            ∧ role_of(A, member, I) = true
            ∧ A not in voted(M,I)   (has not already voted)
        """
        ballot_open = ctx.get("ballot_open", True)
        is_member   = ctx.get("agent_status") == AgentStatus.ACTIVE_MEMBER.value
        has_voted   = ctx.get("agent_has_voted_this_round", False)
 
        if not ballot_open:
            return AxiomResult(
                "vote", False, False, False, AxiomVerdict.NO_POWER, [3],
                "pow(A, vote) requires status(M,I)=open. Ballot is not open."
            )
        if not is_member:
            return AxiomResult(
                "vote", False, False, False, AxiomVerdict.NO_POWER, [3],
                "pow(A, vote) requires role_of(A, member, I)=true. "
                "Non-members cannot vote (Principle 3)."
            )
        if has_voted:
            return AxiomResult(
                "vote", False, False, False, AxiomVerdict.NO_POWER, [3],
                "pow(A, vote) requires A not in voted(M,I). "
                "Agent has already voted this round (one-member-one-vote)."
            )
 
        return AxiomResult(
            "vote", True, True, False, AxiomVerdict.PERMITTED, [3],
            "pow(A, vote) holds: ballot open, agent is member, not yet voted."
        )
 
    def check_declare(self, ctx: dict) -> AxiomResult:
        """
        obl(C, declare(C,W,M,I)) ←
            role_of(C, head, I) = true
            ∧ status(M,I) = closed
            ∧ vote_q(M,I) = Q
            ∧ winner_determination(WDM, Q, W)
        Head is OBLIGATED to declare the correct result after ballot closes.
        """
        is_head       = ctx.get("agent_role") == AgentRole.HEAD.value
        ballot_closed = ctx.get("ballot_closed", False)
        votes_cast    = ctx.get("n_votes_cast", 0)
 
        if not is_head:
            return AxiomResult(
                "declare", False, False, False, AxiomVerdict.NO_POWER, [3],
                "obl(C, declare) requires role_of(C, head, I). Not head."
            )
        if not ballot_closed:
            return AxiomResult(
                "declare", True, False, False, AxiomVerdict.NO_PERMISSION, [3],
                "Head has power to declare but status(M,I) is not closed yet. "
                "Must wait for ballot to close."
            )
        if votes_cast == 0:
            return AxiomResult(
                "declare", True, False, False, AxiomVerdict.NO_PERMISSION, [3],
                "Ballot closed but vote_q(M,I) is empty. No votes to declare on."
            )
 
        return AxiomResult(
            "declare", True, True, True, AxiomVerdict.PERMITTED, [3],
            f"obl(C, declare) holds: head, ballot closed, {votes_cast} votes in queue. "
            "Head is obligated to declare winner via winner_determination."
        )
 
    # ------------------------------------------------------------------
    # Principle 4 axioms
    # ------------------------------------------------------------------
 
    def check_report_env(self, ctx: dict) -> AxiomResult:
        """
        pow(B, report(B,P,I)) ← role_of(B, monitor, I) = true
 
        obl(B, report(B,_,I)) ←
            role_of(B, monitor, I)
            ∧ reported(B,I) = (_, T')
            ∧ monitoring_frequency(I) = F
            ∧ T' < T + F
        (monitor is obligated to report resource level at each monitoring frequency)
        """
        is_monitor       = ctx.get("agent_role") == AgentRole.MONITOR.value
        steps_since_last = ctx.get("steps_since_last_report", 0)
        monitoring_freq_steps = ctx.get("monitoring_freq_steps", 1)
 
        if not is_monitor:
            return AxiomResult(
                "report_env", False, False, False, AxiomVerdict.NO_POWER, [4],
                "pow(B, report) requires role_of(B, monitor, I). Agent is not monitor."
            )
 
        obligation_due = steps_since_last >= monitoring_freq_steps
        verdict        = AxiomVerdict.PERMITTED
 
        if obligation_due:
            verdict = AxiomVerdict.PERMITTED  # permitted and obligated
            explanation = (
                f"pow(B, report_env) holds (is monitor). "
                f"obl(B, report) also holds: {steps_since_last} steps since last report "
                f">= monitoring_frequency={monitoring_freq_steps}. "
                "Monitor is obligated to report resource level now."
            )
        else:
            explanation = (
                f"pow(B, report_env) holds (is monitor). "
                f"obl not yet triggered: {steps_since_last} steps since last report "
                f"< monitoring_frequency={monitoring_freq_steps}."
            )
 
        return AxiomResult(
            "report_env", True, True, obligation_due, verdict, [4], explanation
        )
 
    def check_report_violation(self, ctx: dict) -> AxiomResult:
        """
        pow(B, report(B,A,R,I)) ←
            role_of(B, monitor, I) = true
            ∧ role_of(A, member, I) = true
        Monitor is empowered to report any member's appropriation.
        """
        is_monitor        = ctx.get("agent_role") == AgentRole.MONITOR.value
        target_is_member  = ctx.get("target_status") in (
            AgentStatus.ACTIVE_MEMBER.value,
            AgentStatus.INACTIVE_MEMBER.value,
        )
 
        if not is_monitor:
            return AxiomResult(
                "report_violation", False, False, False, AxiomVerdict.NO_POWER, [4],
                "pow(B, report) requires role_of(B, monitor, I). Not monitor."
            )
        if not target_is_member:
            return AxiomResult(
                "report_violation", False, False, False, AxiomVerdict.NO_POWER, [4],
                "pow(B, report(B,A,R,I)) requires role_of(A, member, I). "
                "Target is not a member — use boundary monitoring instead."
            )
 
        return AxiomResult(
            "report_violation", True, True, False, AxiomVerdict.PERMITTED, [4],
            "pow(B, report(B,A,R,I)) holds: monitor reporting on a member's appropriation."
        )
 
    # ------------------------------------------------------------------
    # Principle 5 axioms
    # ------------------------------------------------------------------
 
    def check_sanction(self, ctx: dict) -> AxiomResult:
        """
        pow(C, sanction(C,A,S,I)) ←
            role_of(C, head, I) = true
            ∧ offences(A,I) = S
        (head is empowered to sanction at level S when agent has S offences)
 
        Graduated structure (paper Section 5.3.5):
            sanction level 1 → inactive (cannot demand), duration=5 steps
            sanction level 2 → inactive, duration=10 steps
            sanction level >= ex_sanction_level → permitted to exclude
        """
        is_head    = ctx.get("agent_role") == AgentRole.HEAD.value
        offences   = ctx.get("target_offences", 0)
        ex_sl      = ctx.get("ex_sanction_level", 3)
 
        if not is_head:
            return AxiomResult(
                "sanction", False, False, False, AxiomVerdict.NO_POWER, [5],
                "pow(C, sanction) requires role_of(C, head, I). Not head."
            )
        if offences == 0:
            return AxiomResult(
                "sanction", False, False, False, AxiomVerdict.NO_POWER, [5],
                "pow(C, sanction) requires offences(A,I)=S with S>0. "
                "No offences recorded — no power to sanction."
            )
 
        # Determine what graduated sanction applies
        if offences >= ex_sl:
            sanction_desc = (
                f"offences={offences} >= ex_sanction_level={ex_sl}. "
                "Exclusion is now permitted (per(G, exclude) will hold)."
            )
        else:
            duration = {1: 5, 2: 10, 3: 15}.get(offences, 5)
            sanction_desc = (
                f"offences={offences}. Graduated sanction: "
                f"inactive for {duration} steps, demand power withdrawn."
            )
 
        return AxiomResult(
            "sanction", True, True, False, AxiomVerdict.PERMITTED, [5],
            f"pow(C, sanction(C,A,{offences},I)) holds: head, offences(A,I)={offences}. "
            + sanction_desc
        )
 
    # ------------------------------------------------------------------
    # Principle 6 axioms
    # ------------------------------------------------------------------
 
    def check_appeal(self, ctx: dict) -> AxiomResult:
        """
        pow(A, appeal(A,S,I)) ←
            role_of(A, member, I) = true
            ∧ sanction_level(A,I) = S  (S > 0)
        """
        is_member      = ctx.get("agent_status") in (
            AgentStatus.ACTIVE_MEMBER.value,
            AgentStatus.INACTIVE_MEMBER.value,
        )
        sanction_level = ctx.get("sanction_level", 0)
 
        if not is_member:
            return AxiomResult(
                "appeal", False, False, False, AxiomVerdict.NO_POWER, [6],
                "pow(A, appeal) requires role_of(A, member, I). Not a member."
            )
        if sanction_level == 0:
            return AxiomResult(
                "appeal", False, False, False, AxiomVerdict.NO_POWER, [6],
                "pow(A, appeal(A,S,I)) requires sanction_level(A,I)=S with S>0. "
                "No active sanction to appeal."
            )
 
        return AxiomResult(
            "appeal", True, True, False, AxiomVerdict.PERMITTED, [6],
            f"pow(A, appeal(A,{sanction_level},I)) holds: "
            f"member with active sanction level {sanction_level}."
        )
 
    def check_uphold(self, ctx: dict) -> AxiomResult:
        """
        pow(C, uphold(C,A,S,I)) ←
            role_of(C, head, I) = true
            ∧ adrMethod(I) = arb             (head is arbiter)
            ∧ appealed(A,S,I) = true
 
        Effect if upheld:
            sanction_level(A,I) = S - 1
            offences(A,I) = O - 1
        """
        is_head        = ctx.get("agent_role") == AgentRole.HEAD.value
        adr_method     = ctx.get("adr_method", "arb")
        has_appealed   = ctx.get("target_has_appealed", False)
        clean_steps    = ctx.get("target_steps_since_offence", 0)
        appeal_window  = ctx.get("appeal_window", 30)
 
        if not is_head:
            return AxiomResult(
                "uphold", False, False, False, AxiomVerdict.NO_POWER, [6],
                "pow(C, uphold) requires role_of(C, head, I). Not head."
            )
        if adr_method != "arb":
            return AxiomResult(
                "uphold", False, False, False, AxiomVerdict.NO_POWER, [6],
                f"pow(C, uphold) requires adrMethod(I)=arb. "
                f"Current adrMethod={adr_method}."
            )
        if not has_appealed:
            return AxiomResult(
                "uphold", False, False, False, AxiomVerdict.NO_POWER, [6],
                "pow(C, uphold) requires appealed(A,S,I)=true. "
                "Agent has not appealed."
            )
 
        # Clean record heuristic from paper Section 6.2:
        # head upholds if agent has not been reported in last 30 steps
        likely_upheld = clean_steps >= appeal_window
        if likely_upheld:
            explanation = (
                f"pow(C, uphold) holds: head, adrMethod=arb, agent has appealed. "
                f"Agent clean for {clean_steps} steps >= {appeal_window} window. "
                "Appeal likely to be upheld — sanction_level and offences decremented."
            )
        else:
            explanation = (
                f"pow(C, uphold) holds: head, adrMethod=arb, agent has appealed. "
                f"However agent only clean for {clean_steps}/{appeal_window} steps. "
                "Head may reject appeal."
            )
 
        return AxiomResult(
            "uphold", True, True, False, AxiomVerdict.PERMITTED, [6], explanation
        )
 