Two ways to control it:

In config.py (default on):


USE_TOOL_CALLING = True   # or False
Via environment variable (overrides config, useful in Docker):


USE_TOOL_CALLING=false python main.py
When disabled, _tool_loop skips the tool loop entirely — one direct LLM call, no axiom checks, just the JSON response. The system prompts still include the world description and compliance profile, so the LLM still reasons from context.