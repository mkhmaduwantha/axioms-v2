import json
import logging
import threading
import time
from collections import deque
from openai import OpenAI
from config import AXIOM_TOOL
from enums import AxiomVerdict
from OstromAxiomEngine import OstromAxiomEngine

_log = logging.getLogger("axioms.llm")


class RateLimiter:
    """Sliding-window rate limiter. Thread-safe."""

    def __init__(self, requests_per_minute: int):
        self.rpm = requests_per_minute
        self._timestamps: deque = deque()
        self._lock = threading.Lock()

    def wait(self):
        """Block until a request slot is available, then claim it."""
        if self.rpm <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                # Drop timestamps outside the 60-second window
                while self._timestamps and now - self._timestamps[0] >= 60.0:
                    self._timestamps.popleft()

                if len(self._timestamps) < self.rpm:
                    self._timestamps.append(now)
                    return

                # Oldest request that still blocks us
                sleep_for = 60.0 - (now - self._timestamps[0]) + 0.05

            _log.warning(
                "Rate limit reached (%d req/min). Waiting %.1fs before next call.",
                self.rpm, sleep_for,
            )
            time.sleep(sleep_for)


class LLMClient:

    def __init__(self, api_key: str, api_base: str, model: str, rate_limit_rpm: int = 10):
        self.client = OpenAI(
            base_url=api_base,
            api_key=api_key,
        )
        self.model        = model
        self.engine       = OstromAxiomEngine()
        self._rate_limiter = RateLimiter(rate_limit_rpm)
        _log.info(
            "LLMClient initialised: model=%s base_url=%s rate_limit=%d rpm",
            model, api_base, rate_limit_rpm,
        )

    def _tool_loop(self, system: str, user: str, ctx: dict, max_calls: int = 3) -> str:
        _log.debug(
            "LLM CALL START\n"
            "  [SYSTEM]\n%s\n"
            "  [USER]\n%s",
            system, user,
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
        for iteration in range(max_calls + 1):
            self._rate_limiter.wait()
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[AXIOM_TOOL],
                tool_choice="auto",
            )
            msg = resp.choices[0].message
            if msg.tool_calls:
                tool_call_summaries = [
                    f"{tc.function.name}({tc.function.arguments})"
                    for tc in msg.tool_calls
                ]
                _log.debug(
                    "LLM RESPONSE iter=%d [ASSISTANT — tool calls]\n  content: %s\n  calls: %s",
                    iteration,
                    msg.content or "(none)",
                    " | ".join(tool_call_summaries),
                )
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

                    call_ctx = dict(ctx)
                    if "planned_appropriation" in args:
                        call_ctx["planned_appropriation"] = args["planned_appropriation"]

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
                    tool_result_text = result.to_tool_result()
                    _log.info(
                        "Axiom tool result: action=%s verdict=%s", action, result.verdict.value
                    )
                    _log.debug(
                        "LLM TOOL RESULT iter=%d action=%s\n%s",
                        iteration, action, tool_result_text,
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result_text,
                    })
            else:
                response_text = msg.content or ""
                _log.debug(
                    "LLM RESPONSE iter=%d [ASSISTANT — final]\n%s",
                    iteration, response_text,
                )
                return response_text
        _log.warning("_tool_loop exhausted max_calls=%d without final response", max_calls)
        return ""

    def _parse(self, text: str, key: str, fallback):
        try:
            clean = text.strip().strip("```json").strip("```").strip()
            return json.loads(clean)[key]
        except Exception:
            return fallback

from config import API_KEY, BASE_URL, MODEL_NAME, RATE_LIMIT_RPM
llm_client = LLMClient(api_key=API_KEY, api_base=BASE_URL, model=MODEL_NAME, rate_limit_rpm=RATE_LIMIT_RPM)
