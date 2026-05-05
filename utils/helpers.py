import json
import random
from LLMClient import llm_client
from models import InstitutionConfig, AgentFlags, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags, llm_all_flags, HARDCODED_FLAGS
from enums import RAMethod

def decide_vote(self, ctx: dict) -> RAMethod:
        raw = self._tool_loop(
            "You are a CPR member voting on the resource allocation method. "
            "Call check_ostrom_axiom with action='vote' to confirm you have power. "
            "Options: 'queue' or 'ration'. "
            "Respond ONLY with JSON: {\"vote\": \"queue\"} or {\"vote\": \"ration\"}",
            f"Pool: {ctx['resource_pool']:.0f}/{ctx['p_max']} | "
            f"Current method: {ctx['ra_method']} | Members: {ctx['n_active_members']}",
            ctx,
        )
        vote = self._parse(raw, "vote", "ration")
        try:
            return RAMethod(vote)
        except ValueError:
            return _hc_vote(ctx)
 
def decide_demand(self, ctx: dict) -> float:
    raw = self._tool_loop(
        "You are a CPR member deciding how much to demand. "
        "Call check_ostrom_axiom with action='demand' first to confirm you have power. "
        "If NO_POWER is returned, demand 0. "
        "Respond ONLY with JSON: {\"demand\": <number>}",
        f"Pool: {ctx['resource_pool']:.0f}/{ctx['p_max']} | "
        f"Members: {ctx['n_active_members']} | Method: {ctx['ra_method']}\n"
        f"Sanction level: {ctx['sanction_level']} | Role: {ctx['agent_role']}",
        ctx,
    )
    return float(self._parse(raw, "demand", _hc_demand(ctx)))

def decide_appropriate(self, ctx: dict) -> float:
    raw = self._tool_loop(
        "You are a CPR member deciding how much to appropriate. "
        "Call check_ostrom_axiom with action='appropriate' and planned_appropriation "
        "set to your intended amount. If NO_PERMISSION, take only your allocation. "
        "Respond ONLY with JSON: {\"appropriate\": <number>}",
        f"Demanded: {ctx['demanded']:.1f} | Allocated: {ctx['allocated']:.1f}\n"
        f"Pool: {ctx['resource_pool']:.0f} | Role: {ctx['agent_role']}\n"
        f"Sanction: {ctx['sanction_level']} | Offences: {ctx['offences']}",
        ctx,
    )
    return float(self._parse(raw, "appropriate", ctx["allocated"]))

def decide_appeal(self, ctx: dict) -> bool:
    raw = self._tool_loop(
        "You are a sanctioned CPR member deciding whether to appeal. "
        "Call check_ostrom_axiom with action='appeal' to check if you have power. "
        "If PERMITTED, decide whether appealing is strategically wise. "
        "Respond ONLY with JSON: {\"appeal\": true} or {\"appeal\": false}",
        f"Sanction level: {ctx['sanction_level']} | "
        f"Clean steps: {ctx['steps_since_offence']}/{ctx['appeal_window']}",
        ctx,
    )
    return bool(self._parse(raw, "appeal", False))

# ---- Head decisions ----

def decide_allocation(self, ctx: dict) -> dict:
    demands_str = "\n".join(
        f"  Agent {aid}: demands {d:.1f}"
        for aid, d in ctx.get("demand_queue", [])
    )
    raw = self._tool_loop(
        "You are the head of a CPR institution. "
        "Call check_ostrom_axiom with action='allocate' to verify your power and obligation. "
        "Total allocations must not exceed the pool. "
        "Respond ONLY with JSON: "
        "{\"allocations\": [{\"agent_id\": <int>, \"amount\": <number>}, ...]}",
        f"Pool: {ctx['resource_pool']:.0f} | Method: {ctx['ra_method']}\n"
        f"Demands:\n{demands_str}",
        ctx,
    )
    try:
        clean = raw.strip().strip("```json").strip("```").strip()
        data  = json.loads(clean)
        return {item["agent_id"]: item["amount"] for item in data["allocations"]}
    except Exception:
        return {}

def decide_sanction(self, ctx: dict) -> str:
    raw = self._tool_loop(
        "You are the head applying a sanction. "
        "Call check_ostrom_axiom with action='sanction' to confirm power and see "
        "what graduated sanction is warranted. "
        "Respond ONLY with JSON: "
        "{\"sanction\": \"inactive\"} or {\"sanction\": \"exclude\"}",
        f"Agent {ctx['target_agent_id']}: "
        f"{ctx['target_offences']} offences | "
        f"current level {ctx['target_sanction_level']} | "
        f"exclusion threshold {ctx['ex_sanction_level']}",
        ctx,
    )
    decision = self._parse(raw, "sanction", "inactive")
    return decision if decision in ("inactive", "exclude") else "inactive"

# ---- Monitor decisions ----

def decide_report(self, ctx: dict) -> bool:
    raw = self._tool_loop(
        "You are the monitor deciding whether to report an agent. "
        "Call check_ostrom_axiom with action='report_violation' to confirm power. "
        "Report if appropriated > allocated. "
        "Respond ONLY with JSON: {\"report\": true} or {\"report\": false}",
        f"Agent {ctx['target_agent_id']}: "
        f"appropriated {ctx['target_appropriated']:.1f}, "
        f"allocated {ctx['target_allocated']:.1f}",
        ctx,
    )
    return bool(self._parse(raw, "report", True))

# ---- Gatekeeper decisions ----

def decide_exclude(self, ctx: dict) -> bool:
    raw = self._tool_loop(
        "You are the gatekeeper deciding whether to exclude a member. "
        "Call check_ostrom_axiom with action='exclude' to check pow and per. "
        "You only have permission when sanction_level >= ex_sanction_level. "
        "Respond ONLY with JSON: {\"exclude\": true} or {\"exclude\": false}",
        f"Agent {ctx['target_agent_id']}: "
        f"sanction level {ctx['target_sanction_level']} | "
        f"threshold {ctx['ex_sanction_level']} | "
        f"offences {ctx['target_offences']}",
        ctx,
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
    if ctx.get("ra_method") == RAMethod.QUEUE.value:
        return (
            max(0, random.gauss(ctx.get("queue_demand_mean", 50), 5))
            if random.random() < 0.90 else 0.0
        )
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
    return appropriated > allocated + 0.01
 
def _hc_exclude(sanction_level: int, ex_sanction_level: int) -> bool:
    return sanction_level >= ex_sanction_level