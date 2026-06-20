"""GATE -- B4 loop-breaker TEETH. The old loop-breaker only ADVISED ("don't call it again"); a stuck
agent could ignore the message and spin to max_steps. This proves the teeth: an agent that calls the
identical (tool, args) past the advisory threshold is HARD-STOPPED -- the tool stops executing and the
turn ends with a blocker report, well before max_steps.

A fake model that always emits the SAME tool call stands in for a stuck agent (no real LLM/SAP).

    uv run python gate_loop_breaker.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import agent
from agent import _LOOP_ADVISE

MAX_STEPS = 20


class _Fn:
    def __init__(self, name, arguments): self.name = name; self.arguments = arguments


class _TC:
    def __init__(self, i, name, arguments): self.id = f"call_{i}"; self.function = _Fn(name, arguments)


class _Msg:
    def __init__(self, content, tool_calls): self.content = content; self.tool_calls = tool_calls


class StubMemory:
    """Just enough of TieredMemory for run_turn -- no tokens, no compaction, fully deterministic."""
    def __init__(self): self.msgs = [{"role": "system", "content": "sys"}]
    def add_user(self, text, image=None, mime=None): self.msgs.append({"role": "user", "content": text})
    def maybe_compact(self): pass
    def context(self): return self.msgs
    def add_assistant(self, a): self.msgs.append(a)
    def add_tool(self, tid, result): self.msgs.append({"role": "tool", "tool_call_id": tid, "content": str(result)})


model_calls = {"n": 0}
dispatch_calls = {"n": 0}


def fake_model_complete(messages, tools=None, model=None):
    # a stuck agent: always narrate + emit the IDENTICAL tool call, forever.
    model_calls["n"] += 1
    return _Msg("working on it", [_TC(model_calls["n"], "list_allowed_values", '{"field": "Plant"}')])


def fake_dispatch(name, args):
    dispatch_calls["n"] += 1
    return "Plant is not a coded field."          # the unchanging result that would cause the loop


agent.model_complete = fake_model_complete
agent.dispatch = fake_dispatch

mem = StubMemory()
out = agent.run_turn(mem, "extend the FG to a plant", tools=True, max_steps=MAX_STEPS, verbose=False)

tool_msgs = [m["content"] for m in mem.msgs if m.get("role") == "tool"]
advisories = [t for t in tool_msgs if t.startswith("LOOP BREAKER:")]
hard_stops = [t for t in tool_msgs if "hard stop" in t]

# Executes for the calls below the advisory threshold (n=1..N-1), then ONE advisory at n=N, then the
# teeth bite at n=N+1 -> hard stop. So: dispatch ran _LOOP_ADVISE-1 times; model_complete ran N+1 times.
a1 = dispatch_calls["n"] == _LOOP_ADVISE - 1
a2 = len(advisories) == 1
a3 = len(hard_stops) == 1
a4 = "Stopped" in out
a5 = model_calls["n"] == _LOOP_ADVISE + 1 and model_calls["n"] < MAX_STEPS

print(f"=== GATE (advisory threshold N={_LOOP_ADVISE}, max_steps={MAX_STEPS}) ===")
print(f"  model_complete calls: {model_calls['n']}   tool executions: {dispatch_calls['n']}")
print(f"  (1) tool executed only below threshold (N-1={_LOOP_ADVISE - 1} times)  : {a1}")
print(f"  (2) exactly one advisory before the teeth                      : {a2}")
print(f"  (3) exactly one HARD-STOP loop-breaker                         : {a3}")
print(f"  (4) turn returned a 'Stopped' blocker report to the user       : {a4}")
print(f"  (5) stopped at N+1 steps, did NOT spin to max_steps            : {a5}")
print(f"\n  ALL PASS: {all([a1, a2, a3, a4, a5])}")
