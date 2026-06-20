"""The HAND-ROLLED agent loop -- no ADK, no framework. The whole spine is here: model call -> tool
dispatch -> repeat until the model stops calling tools (or max_steps). A failure here is OURS, and
therefore fixable -- that is the entire point of the clean room.

    run_agent(system_instruction, user_input, history) -> (final_text, messages)

`messages` is the full OpenAI-format transcript so a caller can continue the conversation (and so
Step 2's tiered memory can compact it)."""
import base64
import json
import os

from model_client import model_complete
from tools import TOOL_SPECS, dispatch

# Loop-breaker thresholds. The Nth identical (tool, args) call gets ONE advisory ("change approach");
# if the agent ignores it and calls the identical thing AGAIN, the turn is HARD-STOPPED instead of
# spinning to max_steps. RIG_LOOP_LIMIT overrides the advisory threshold N (the teeth bite at N+1).
try:
    _LOOP_ADVISE = max(2, int(os.environ.get("RIG_LOOP_LIMIT", "3")))
except ValueError:
    _LOOP_ADVISE = 3


def _vision_messages(messages, image_bytes, mime="image/png"):
    """A copy of `messages` where the last user message ALSO carries the image as a vision content,
    so a vision model can SEE it (perception) -- WITHOUT the image being stored in the persistent
    working set. The blob still lives only on disk; this puts it in front of the model for one turn."""
    out = [dict(m) for m in messages]
    for m in reversed(out):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            b64 = base64.b64encode(image_bytes).decode()
            m["content"] = [{"type": "text", "text": m["content"]},
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]
            break
    return out


def run_agent(system_instruction, user_input, history=None, tools=True, max_steps=8, verbose=True):
    """Run one turn to completion. history: prior messages to continue a conversation."""
    messages = list(history or [])
    if system_instruction and not (messages and messages[0].get("role") == "system"):
        messages.insert(0, {"role": "system", "content": system_instruction})
    if user_input is not None:
        messages.append({"role": "user", "content": user_input})

    specs = TOOL_SPECS if tools else None
    for _ in range(max_steps):
        msg = model_complete(messages, tools=specs)
        assistant = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls]
        messages.append(assistant)

        if not msg.tool_calls:                       # no tools requested -> the turn is done
            return (msg.content or ""), messages

        for tc in msg.tool_calls:                    # dispatch each tool call, append the result
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if verbose:
                print(f"   -> {name}({json.dumps(args)[:120]})")
            result = dispatch(name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)[:8000]})

    return "(max steps reached without a final answer)", messages


def run_turn(memory, user_input, image=None, mime="image/png", tools=True, max_steps=8, verbose=True,
             steps=None, perceive=False, model=None):
    """A MEMORY-AWARE turn (Step 2): add the user message (blobs evicted to disk), compact on the token
    budget, then run the loop against the COMPACTED context. Returns the final text; the transcript
    lives in `memory`. If `steps` is a list, tool_call/tool_result records are appended for the UI.
    perceive=True shows the image to the vision model THIS turn (genesis) -- it is still evicted to
    disk, so it never rides in subsequent turns."""
    memory.add_user(user_input, image=image, mime=mime)
    memory.maybe_compact()                          # token-budget compaction BEFORE the model sees it
    specs = TOOL_SPECS if tools else None
    vision = image if (perceive and image) else None
    last_text = ""                                  # remember the latest narration for a graceful cap-hit
    call_counts = {}                                # loop-breaker: (tool, args) -> times called this turn
    for i in range(max_steps):
        msgs = memory.context()
        if vision and i == 0:
            # perception: the image goes in front of the model ONCE (the first call), then it works
            # from what it described -- never re-uploaded every step (that made the turn crawl).
            msgs = _vision_messages(msgs, vision, mime)
        msg = model_complete(msgs, tools=specs, model=model)
        if msg.content:
            last_text = msg.content
        assistant = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls]
        memory.add_assistant(assistant)
        if not msg.tool_calls:
            return msg.content or ""
        for idx, tc in enumerate(msg.tool_calls):
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if verbose:
                print(f"   -> {name}({json.dumps(args)[:120]})")
            if steps is not None:
                steps.append({"author": "agent", "kind": "tool_call", "tool": name, "args": args})
            sig = name + "|" + json.dumps(args, sort_keys=True)[:300]
            call_counts[sig] = call_counts.get(sig, 0) + 1
            n = call_counts[sig]
            if n > _LOOP_ADVISE:
                # TEETH: the agent was warned to change approach and called the identical tool AGAIN.
                # Don't dispatch, and don't keep spinning to max_steps -- hard-stop the turn. Give every
                # tool_call in this assistant message a response first so the transcript stays valid.
                blocker = (f"LOOP BREAKER (hard stop): {name} was called with identical arguments {n} "
                           f"times despite a warning to change approach. The turn is being stopped.")
                memory.add_tool(tc.id, blocker)
                for other in msg.tool_calls[idx + 1:]:
                    memory.add_tool(other.id, "(skipped -- turn stopped by the loop breaker)")
                if steps is not None:
                    steps.append({"author": "agent", "kind": "tool_result", "tool": name, "result": blocker})
                stop = (f"_(Stopped — I kept calling `{name}` with the same arguments and stopped making "
                        f"progress; the result wasn't changing, so retrying won't help. Tell me how you'd "
                        f"like to proceed, or I can try a different approach.)_")
                return (last_text + "\n\n" + stop) if last_text else stop
            if n == _LOOP_ADVISE:                   # one advisory before the teeth bite on the next repeat
                result = (f"LOOP BREAKER: you have called {name} with identical arguments {n} times and it "
                          f"keeps returning the same result. Do NOT call it again — change your approach (a "
                          f"different tool or arguments), or stop and report the blocker to the user. "
                          f"Calling it again with the same arguments will stop the turn.")
            else:
                result = dispatch(name, args)
            memory.add_tool(tc.id, result)
            if steps is not None:
                steps.append({"author": "agent", "kind": "tool_result", "tool": name, "result": str(result)[:8000]})
    tail = "_(Paused at the step limit — I was still mid-task. Say \"continue\" to resume.)_"
    return (last_text + "\n\n" + tail) if last_text else tail
