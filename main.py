from LLMClient import llm_client
from enums import AgentRole, AgentStatus
from agents import InstitutionalAgent, HeadAgent, MonitorAgent, GatekeeperAgent
from CPRModel import CPRModel
from OstromAxiomEngine import OstromAxiomEngine
from models import Institution, InstitutionConfig, AgentFlags, AxiomResult, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags

if __name__ == "__main__":
 
    print("\n=== Axiom engine unit tests ===")
    engine = OstromAxiomEngine()
 
    # P1: demand — sanctioned agent has no power
    r = engine.check_demand({
        "agent_status": "active_member", "demanded": 0, "sanction_level": 1
    })
    print(f"Sanctioned agent demand: {r.verdict.value} — {r.explanation}")
 
    # P2: appropriate — over-allocation has no permission
    r = engine.check_appropriate({
        "agent_status": "active_member", "allocated": 50, "planned_appropriation": 65
    })
    print(f"Over-appropriate: {r.verdict.value} — {r.explanation}")
 
    # P1: exclude — gatekeeper with sanction below threshold has no permission
    r = engine.check_exclude({
        "agent_role": "gatekeeper", "ex_method": "discretionary",
        "target_sanction_level": 1, "ex_sanction_level": 3
    })
    print(f"Premature exclusion: {r.verdict.value} — {r.explanation}")
 
    # P6: appeal — agent with no sanction has no power
    r = engine.check_appeal({"agent_status": "active_member", "sanction_level": 0})
    print(f"Appeal without sanction: {r.verdict.value} — {r.explanation}")
 
    # P4: report_violation — non-monitor has no power
    r = engine.check_report_violation({
        "agent_role": "member", "target_status": "active_member"
    })
    print(f"Non-monitor reporting: {r.verdict.value} — {r.explanation}")
 
    print("\n=== Simulation run: fully hardcoded ===")
    r = CPRModel(
        n_members=100, n_nonmembers=20,
        noncompliant_member_fraction=0.0,
        use_principle_3=True, use_principle_4=False,
        use_principle_5=False, use_principle_6=False,
    ).run(200)
    print(f"  Lifespan {r['lifespan']} | Pool {r['final_resource']:.0f} | Members {r['final_members']}")