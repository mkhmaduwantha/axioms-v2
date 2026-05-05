from openai import OpenAI
from config import AXIOM_TOOL
from enums import AxiomVerdict
from OstromAxiomEngine import OstromAxiomEngine
import json

class LLMClient:
 
    def __init__(self, api_key: str, api_base: str, model: str):
        self.client = OpenAI(
            base_url=api_base,
            api_key=api_key,
        )
        self.model  = model
        self.engine = OstromAxiomEngine()
 
    def _tool_loop(self, system: str, user: str, ctx: dict, max_calls: int = 3) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
        for _ in range(max_calls + 1):
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[AXIOM_TOOL],
                tool_choice="auto",
            )
            msg = resp.choices[0].message
            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id, "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })
                for tc in msg.tool_calls:
                    args   = json.loads(tc.function.arguments)
                    action = args.get("action", "demand")
 
                    # Merge planned_appropriation into ctx if provided
                    call_ctx = dict(ctx)
                    if "planned_appropriation" in args:
                        call_ctx["planned_appropriation"] = args["planned_appropriation"]
 
                    # Dispatch to correct engine method
                    dispatch = {
                        "apply":             self.engine.check_apply,
                        "assign_member":     self.engine.check_assign_member,
                        "exclude":           self.engine.check_exclude,
                        "demand":            self.engine.check_demand,
                        "allocate":          self.engine.check_allocate,
                        "appropriate":       self.engine.check_appropriate,
                        "vote":              self.engine.check_vote,
                        "declare":           self.engine.check_declare,
                        "report_env":        self.engine.check_report_env,
                        "report_violation":  self.engine.check_report_violation,
                        "sanction":          self.engine.check_sanction,
                        "appeal":            self.engine.check_appeal,
                        "uphold":            self.engine.check_uphold,
                    }
                    result = dispatch.get(action, self.engine.check_demand)(call_ctx)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result.to_tool_result(),
                    })
            else:
                return msg.content or ""
        return ""
 
    def _parse(self, text: str, key: str, fallback):
        try:
            clean = text.strip().strip("```json").strip("```").strip()
            return json.loads(clean)[key]
        except Exception:
            return fallback

from config import API_KEY, BASE_URL, MODEL_NAME
llm_client = LLMClient(api_key=API_KEY, api_base=BASE_URL, model=MODEL_NAME)