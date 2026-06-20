"""Generic orchestration patterns we OWN -- not framework objects, just small functions over
run_agent. These are the agent PATTERNS kept from the ADK shape (sequential / parallel / loop /
hybrid), minus the harness. Compose them for multi-agent flows without importing a framework."""
from concurrent.futures import ThreadPoolExecutor

from agent import run_agent


def run_sequential(steps):
    """steps: [(system_instruction, input), ...]. Each step sees the previous step's output appended.
    Returns the list of step outputs. (An 'Arranger of Doers' -- e.g. Intake -> Validate -> Writer.)"""
    outputs, carry = [], ""
    for si, inp in steps:
        prompt = inp + (f"\n\n--- prior step output ---\n{carry}" if carry else "")
        text, _ = run_agent(si, prompt)
        outputs.append(text)
        carry = text
    return outputs


def run_parallel(tasks, max_workers=4):
    """tasks: [(system_instruction, input), ...]. Run concurrently; outputs returned in order.
    (The boardroom shape: N independent assessors, one barrier.)"""
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(run_agent, si, inp) for si, inp in tasks]
        return [f.result()[0] for f in futures]


def run_loop(system_instruction, initial_input, done, max_iters=5):
    """Feed the agent its own output until done(text) is True (or max_iters). (Refine-until-good.)"""
    text = initial_input
    for _ in range(max_iters):
        text, _ = run_agent(system_instruction, text)
        if done(text):
            break
    return text


def run_hybrid(plan, synthesize_si):
    """A coordinator: run `plan` (a list of (si, input) tasks) in parallel, then synthesise the
    outputs with one more agent. (Router -> parallel -> synthesise.)"""
    parts = run_parallel(plan)
    joined = "\n\n".join(f"[result {i}]\n{p}" for i, p in enumerate(parts))
    final, _ = run_agent(synthesize_si, "Synthesise these results into one answer:\n\n" + joined)
    return final
