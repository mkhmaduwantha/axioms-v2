import json
import logging
import random
from LLMClient import llm_client
from models import InstitutionConfig, AgentFlags, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags, llm_all_flags, HARDCODED_FLAGS
from enums import RAMethod

_log = logging.getLogger("axioms.llm")

_DEFAULT_SYSTEM = "You are an agent in a common-pool resource institution. You may call check_ostrom_axiom before any decision."


def _base(ctx: dict) -> str:
    """Return the agent's system prompt, falling back to a generic default."""
    return ctx.get("system_prompt", _DEFAULT_SYSTEM)


def _log_reasoning(fn_name: str, agent_id, reasoning: str):
    if reasoning:
        _log.info("Agent %s [%s] reasoning: %s", agent_id, fn_name, reasoning)


# ---- Member decisions ----

def decide_vote(self, ctx: dict) -> RAMethod:
    system = (
        _base(ctx) + "\n\n"
        "You are voting on the resource allocation method. "
        "Call check_ostrom_axiom with action='vote' to confirm you have power. "
        "Queue: first-come first-served — agents who demand early get their full amount until the pool runs out. "
        "Ration: the pool is divided equally among all demanding agents, so everyone gets a fair share but less when the pool is low. "
        "Options: 'queue' or 'ration'.\n"
        "Respond ONLY with JSON: {\"vote\": \"queue\", \"reasoning\": \"<brief why>\"}"
    )
    history = ctx.get("recent_history", "")
    user = (
        f"Pool: {ctx['resource_pool']:.4f}/{ctx['p_max']} | "
        f"Current method: {ctx['ra_method']} | Members: {ctx['n_active_members']}"
    )
    if history:
        user += f"\n\nYour recent history:\n{history}"
    raw = self._tool_loop(system, user, ctx)
    _log_reasoning("vote", ctx.get("agent_id"), self._parse(raw, "reasoning", ""))
    vote = self._parse(raw, "vote", "ration")
    try:
        return RAMethod(vote)
    except ValueError:
        return _hc_vote(ctx)


def decide_demand(self, ctx: dict) -> float:
    system = (
        _base(ctx) + "\n\n"
        "You are deciding how much resource to demand this round. "
        "Call check_ostrom_axiom with action='demand' first to confirm you have power. "
        "If NO_POWER is returned, demand 0.\n"
        "Respond ONLY with JSON: {\"demand\": <number>, \"reasoning\": \"<brief why>\"}"
    )
    history = ctx.get("recent_history", "")
    user = (
        f"Pool: {ctx['resource_pool']:.4f}/{ctx['p_max']} | "
        f"Members: {ctx['n_active_members']} | Method: {ctx['ra_method']}\n"
        f"Sanction level: {ctx['sanction_level']} | Role: {ctx['agent_role']}"
    )
    if history:
        user += f"\n\nYour recent history:\n{history}"
    raw = self._tool_loop(system, user, ctx)
    _log_reasoning("demand", ctx.get("agent_id"), self._parse(raw, "reasoning", ""))
    return float(self._parse(raw, "demand", _hc_demand(ctx)))


def decide_appropriate(self, ctx: dict) -> float:
    history = self.mem_search(
        "violations sanctions consequences appropriation",
        user_id=f"agent_{ctx.get('agent_id', 'unknown')}",
    )
    system = (
        _base(ctx) + "\n\n"
        "You are deciding how much to appropriate from the pool. "
        "Call check_ostrom_axiom with action='appropriate' and planned_appropriation "
        "set to your intended amount. If NO_PERMISSION, take only your allocation.\n"
        "Respond ONLY with JSON: {\"appropriate\": <number>, \"reasoning\": \"<brief why>\"}"
    )
    if history:
        system += f"\n\nYour institutional history:\n{history}"
    history = ctx.get("recent_history", "")
    user = (
        f"Demanded: {ctx['demanded']:.4f} | Allocated: {ctx['allocated']:.4f}\n"
        f"Pool: {ctx['resource_pool']:.4f} | Role: {ctx['agent_role']}\n"
        f"Sanction: {ctx['sanction_level']} | Offences: {ctx['offences']}"
    )
    if history:
        user += f"\n\nYour recent history:\n{history}"
    raw = self._tool_loop(system, user, ctx)
    _log_reasoning("appropriate", ctx.get("agent_id"), self._parse(raw, "reasoning", ""))
    return float(self._parse(raw, "appropriate", ctx["allocated"]))


def decide_appeal(self, ctx: dict) -> bool:
    history = self.mem_search(
        "appeal outcomes sanctions upheld rejected",
        user_id=f"agent_{ctx.get('agent_id', 'unknown')}",
    )
    system = (
        _base(ctx) + "\n\n"
        "You are deciding whether to appeal your current sanction. "
        "Call check_ostrom_axiom with action='appeal' to check if you have power. "
        "If PERMITTED, decide whether appealing is strategically wise.\n"
        "Respond ONLY with JSON: {\"appeal\": true, \"reasoning\": \"<brief why>\"}"
    )
    if history:
        system += f"\n\nYour appeal and sanction history:\n{history}"
    history = ctx.get("recent_history", "")
    user = (
        f"Sanction level: {ctx['sanction_level']} | "
        f"Clean steps: {ctx['steps_since_offence']}/{ctx['appeal_window']}"
    )
    if history:
        user += f"\n\nYour recent history:\n{history}"
    raw = self._tool_loop(system, user, ctx)
    _log_reasoning("appeal", ctx.get("agent_id"), self._parse(raw, "reasoning", ""))
    return bool(self._parse(raw, "appeal", False))


# ---- Head decisions ----

def decide_allocation(self, ctx: dict) -> dict:
    demands_str = "\n".join(
        f"  Agent {aid}: demands {d:.1f}"
        for aid, d in ctx.get("demand_queue", [])
    )
    system = (
        _base(ctx) + "\n\n"
        "You are the head of a CPR institution allocating resources. "
        "Call check_ostrom_axiom with action='allocate' to verify your power and obligation. "
        "Total allocations must not exceed the pool.\n"
        "Respond ONLY with JSON: "
        "{\"allocations\": [{\"agent_id\": <int>, \"amount\": <number>}, ...], "
        "\"reasoning\": \"<brief why>\"}"
    )
    raw = self._tool_loop(
        system,
        f"Pool: {ctx['resource_pool']:.0f} | Method: {ctx['ra_method']}\n"
        f"Demands:\n{demands_str}",
        ctx,
    )
    _log_reasoning("allocation", ctx.get("agent_id"), self._parse(raw, "reasoning", ""))
    try:
        clean = raw.strip().strip("```json").strip("```").strip()
        data  = json.loads(clean)
        return {item["agent_id"]: item["amount"] for item in data["allocations"]}
    except Exception:
        return {}


def decide_sanction(self, ctx: dict) -> str:
    history = self.mem_search(
        "violations appropriation sanctions offences",
        user_id=f"agent_{ctx.get('target_agent_id', 'unknown')}",
    )
    system = (
        _base(ctx) + "\n\n"
        "You are the head deciding what sanction to apply to a violating member. "
        "Call check_ostrom_axiom with action='sanction' to confirm power and see "
        "what graduated sanction is warranted.\n"
        "Respond ONLY with JSON: "
        "{\"sanction\": \"inactive\", \"reasoning\": \"<brief why>\"} "
        "or {\"sanction\": \"exclude\", \"reasoning\": \"<brief why>\"}"
    )
    if history:
        system += f"\n\nAgent's full institutional history:\n{history}"
    raw = self._tool_loop(
        system,
        f"Agent {ctx['target_agent_id']}: "
        f"{ctx['target_offences']} offences | "
        f"current level {ctx['target_sanction_level']} | "
        f"exclusion threshold {ctx['ex_sanction_level']}",
        ctx,
    )
    _log_reasoning(
        f"sanction→agent_{ctx.get('target_agent_id')}", ctx.get("agent_id"),
        self._parse(raw, "reasoning", ""),
    )
    decision = self._parse(raw, "sanction", "inactive")
    return decision if decision in ("inactive", "exclude") else "inactive"


# ---- Monitor decisions ----

def decide_report(self, ctx: dict) -> bool:
    system = (
        _base(ctx) + "\n\n"
        "You are the monitor deciding whether to report an agent for a violation. "
        "Call check_ostrom_axiom with action='report_violation' to confirm power. "
        "Report if appropriated > allocated.\n"
        "Respond ONLY with JSON: {\"report\": true, \"reasoning\": \"<brief why>\"}"
    )
    raw = self._tool_loop(
        system,
        f"Agent {ctx['target_agent_id']}: "
        f"appropriated {ctx['target_appropriated']:.1f}, "
        f"allocated {ctx['target_allocated']:.1f}",
        ctx,
    )
    _log_reasoning(
        f"report→agent_{ctx.get('target_agent_id')}", ctx.get("agent_id"),
        self._parse(raw, "reasoning", ""),
    )
    return bool(self._parse(raw, "report", True))


# ---- Gatekeeper decisions ----

def decide_exclude(self, ctx: dict) -> bool:
    history = self.mem_search(
        "sanctions exclusion offences institutional record",
        user_id=f"agent_{ctx.get('target_agent_id', 'unknown')}",
    )
    system = (
        _base(ctx) + "\n\n"
        "You are the gatekeeper deciding whether to exclude a member. "
        "Call check_ostrom_axiom with action='exclude' to check pow and per. "
        "You only have permission when sanction_level >= ex_sanction_level.\n"
        "Respond ONLY with JSON: {\"exclude\": true, \"reasoning\": \"<brief why>\"}"
    )
    if history:
        system += f"\n\nAgent's full institutional record:\n{history}"
    raw = self._tool_loop(
        system,
        f"Agent {ctx['target_agent_id']}: "
        f"sanction level {ctx['target_sanction_level']} | "
        f"threshold {ctx['ex_sanction_level']} | "
        f"offences {ctx['target_offences']}",
        ctx,
    )
    _log_reasoning(
        f"exclude→agent_{ctx.get('target_agent_id')}", ctx.get("agent_id"),
        self._parse(raw, "reasoning", ""),
    )
    return bool(self._parse(raw, "exclude", True))


# ---------------------------------------------------------------------------
# Hardcoded decision functions
# ---------------------------------------------------------------------------

def _hc_vote(ctx: dict) -> RAMethod:
    return (
        RAMethod.QUEUE
        if ctx.get("resource_pool", 0) >= 0.75 * ctx.get("p_max", 10000)
        else RAMethod.RATION
    )

def _hc_demand(ctx: dict) -> float:
    # Note: the 90% queue-mode abstention gate is applied in demand_stage before
    # this function is called, so all agents reaching here should demand > 0.
    if ctx.get("ra_method") == RAMethod.QUEUE.value:
        return max(0, random.gauss(ctx.get("queue_demand_mean", 50), 5))
    estimated = ctx.get("resource_pool", 0) / max(ctx.get("n_active_members", 1), 1)
    return max(0, estimated * random.uniform(0.9, 1.1))

def _hc_appropriate(ctx: dict) -> float:
    allocated = ctx.get("allocated", 0)
    if ctx.get("compliance_degree", 1.0) >= 1.0:
        return allocated
    return allocated * random.uniform(1.0, 1.20)

def _hc_appeal(ctx: dict) -> bool:
    return ctx.get("sanction_level", 0) > 0

def _hc_allocate(demand_queue: list, pool: float, ra_method: RAMethod) -> dict:
    allocations = {}
    if ra_method == RAMethod.QUEUE:
        for agent_id, demand in demand_queue:
            if pool >= demand:
                allocations[agent_id] = demand
                pool -= demand
            else:
                allocations[agent_id] = 0.0
    elif ra_method == RAMethod.RATION:
        demanding = [(aid, d) for aid, d in demand_queue if d > 0]
        if not demanding:
            return allocations
        ration = pool / len(demanding)
        for agent_id, demand in demanding:
            allocations[agent_id] = min(demand, ration)
    return allocations

def _hc_sanction(offences: int, ex_sanction_level: int) -> str:
    return "exclude" if offences >= ex_sanction_level else "inactive"

def _hc_report(appropriated: float, allocated: float) -> bool:
    tolerance = max(0.05, allocated * 0.005)
    return appropriated > allocated + tolerance

def _hc_exclude(sanction_level: int, ex_sanction_level: int) -> bool:
    return sanction_level >= ex_sanction_level
