from utils.logger import logger   # initialises handlers before any other import
from utils.plotting import plot_results
from LLMClient import llm_client
from enums import AgentRole, AgentStatus
from agents import InstitutionalAgent, HeadAgent, MonitorAgent, GatekeeperAgent
from CPRModel import CPRModel
from OstromAxiomEngine import OstromAxiomEngine
from models import Institution, InstitutionConfig, AgentFlags, AxiomResult, llm_member_flags, llm_head_flags, llm_monitor_flags, llm_gatekeeper_flags

if __name__ == "__main__":

    # logger.info("=== Axiom engine unit tests ===")
    # print("\n=== Axiom engine unit tests ===")
    # engine = OstromAxiomEngine()

    # # P1: demand — sanctioned agent has no power
    # r = engine.check_demand({
    #     "agent_status": "active_member", "demanded": 0, "sanction_level": 1
    # })
    # msg = f"Sanctioned agent demand: {r.verdict.value} — {r.explanation}"
    # print(msg)
    # logger.info(msg)

    # # P2: appropriate — over-allocation has no permission
    # r = engine.check_appropriate({
    #     "agent_status": "active_member", "allocated": 50, "planned_appropriation": 65
    # })
    # msg = f"Over-appropriate: {r.verdict.value} — {r.explanation}"
    # print(msg)
    # logger.info(msg)

    # # P1: exclude — gatekeeper with sanction below threshold has no permission
    # r = engine.check_exclude({
    #     "agent_role": "gatekeeper", "ex_method": "discretionary",
    #     "target_sanction_level": 1, "ex_sanction_level": 3
    # })
    # msg = f"Premature exclusion: {r.verdict.value} — {r.explanation}"
    # print(msg)
    # logger.info(msg)

    # # P6: appeal — agent with no sanction has no power
    # r = engine.check_appeal({"agent_status": "active_member", "sanction_level": 0})
    # msg = f"Appeal without sanction: {r.verdict.value} — {r.explanation}"
    # print(msg)
    # logger.info(msg)

    # # P4: report_violation — non-monitor has no power
    # r = engine.check_report_violation({
    #     "agent_role": "member", "target_status": "active_member"
    # })
    # msg = f"Non-monitor reporting: {r.verdict.value} — {r.explanation}"
    # print(msg)
    # logger.info(msg)

    logger.info("=== Simulation run: fully hardcoded ===")
    print("\n=== Simulation run: fully hardcoded ===")
    # r = CPRModel(
    #     n_members=100, n_nonmembers=20, n_llm_members=0,
    #     noncompliant_member_fraction=0.5, unintentional_violation_frac=0.05,
    #     use_principle_3=True, use_principle_4=True,
    #     use_principle_5=True, use_principle_6=True,
    # ).run(500)
    

    r = CPRModel(
    n_members=7,
    n_nonmembers=2,

    # All regular members are LLM agents
    n_llm_members=7,
    member_llm_flags=llm_member_flags(),  # vote+demand+appropriate+appeal

    # Head: LLM for all member behaviours + allocate + sanction
    head_config={
        "llm": True,
        "flags": llm_head_flags(),        # vote+demand+appropriate+appeal+allocate+sanction
        "compliance_degree": 1.0,
    },

    # Monitor: LLM for all member behaviours + monitor duty
    monitor_config={
        "llm": True,
        "flags": llm_monitor_flags(),     # vote+demand+appropriate+appeal+monitor
        "compliance_degree": 1.0,
    },

    # Gatekeeper: LLM for all member behaviours + exclude duty
    gatekeeper_config={
        "llm": True,
        "flags": llm_gatekeeper_flags(),  # vote+demand+appropriate+appeal+exclude
        "compliance_degree": 1.0,
    },
    unintentional_violation_frac=0.05,
    noncompliant_member_fraction=0.5,
    use_principle_3=True,
    use_principle_4=True,
    use_principle_5=True,
    use_principle_6=True,
    ).run(20)

    print(f"Lifespan: {r['lifespan']}")
    print(f"Final pool: {r['final_resource']:.0f}")
    print(f"Final members: {r['final_members']}")

    summary = (
        f"  Lifespan {r['lifespan']} | Pool {r['final_resource']:.0f} | "
        f"Members {r['final_members']}"
    )

    print(summary)
    logger.info(summary)

    png = plot_results(r, InstitutionConfig())
    print(f"Graph saved to: {png}")
