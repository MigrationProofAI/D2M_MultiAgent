"""The MODEL SEAM -- the one place that knows the provider. Swap OpenAI / GenAI-Hub here and
nothing else in the rig changes. The whole rig calls `model_complete()` (the loop) or
`summarize()` (Step 2).

PROVIDERS (set MODEL_PROVIDER):
  - "anthropic" (DEFAULT here) -> Claude (Sonnet) on SAP GenAI Hub, native Messages API. Cost = SAP's.
  - "genaihub"                 -> SAP GenAI Hub via the BTP `aicore` destination. Cost = SAP's, not yours.
  - "openai"                   -> OpenAI chat-completions. YOUR key (opt-in only). Avoid in D2M_MultiAgent.

D2M_MultiAgent runs on BTP / AI Core ONLY -- no out-of-pocket OpenAI spend. The default is "anthropic"
so a naked `python web.py` can never silently fall back to OpenAI. (NOTE: mcp_server/vector.py and
learning.py still import openai directly for embeddings/reflection -- see STARTING_POINT.md task #1.)

Both return the SAME object shape the rig depends on: a message with `.content` and `.tool_calls`,
where each tool_call has `.id` and `.function.{name,arguments}`. (agent.py reads exactly that.)

PER-TIER mapping (so the cheap, high-frequency loop does NOT run on the expensive model):
  - the main loop  -> AICORE_DEPLOY_MAIN     (keep this CHEAP: gpt-4o-mini -> gaps stay visible)
  - summaries      -> AICORE_DEPLOY_SUMMARY   (a stronger model is fine; low frequency)
  - genesis/vision -> AICORE_DEPLOY_GENESIS   (a stronger model is fine; low frequency)
The rig passes its logical model name (MODEL / SUMMARY_MODEL / GENESIS_MODEL) into model_complete;
on the genaihub path we translate that logical name to the matching deployment id below.
"""
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "anthropic").lower()   # AI Core only; "openai" is opt-in

# EXTENDED THINKING (anthropic provider only). Off by default -> behaviour identical to today. When on,
# Claude returns a `thinking` block (its chain-of-thought) before the answer; we surface it as
# msg.reasoning for the Agent-Activity panel, and round-trip the raw blocks (with signatures) so a
# multi-step tool loop stays valid. Extended thinking REQUIRES temperature=1.
THINKING_ON = os.getenv("RIG_THINKING", "off").lower() in ("1", "on", "true", "yes")
THINKING_BUDGET = int(os.getenv("RIG_THINKING_BUDGET", "8000"))   # was 2000 -> too thin vs Claude.ai

# --- TELEMETRY: per-thread (per-agent) token accounting. Each model call adds its usage; run_turn reads
#     the turn total and emits it into the activity chain. Thread-local isolates CONCURRENT agents (the
#     board runs in parallel threads), so each agent's tokens are counted separately. ---
import threading as _threading
_usage_tl = _threading.local()


def _add_usage(tin, tout):
    t = getattr(_usage_tl, "u", None) or {"in": 0, "out": 0, "calls": 0}
    t["in"] += int(tin or 0); t["out"] += int(tout or 0); t["calls"] += 1
    _usage_tl.u = t


def turn_usage(reset=False):
    """Accumulated token usage on THIS thread: {in, out, calls}. run_turn resets at start, reads at end."""
    t = getattr(_usage_tl, "u", None) or {"in": 0, "out": 0, "calls": 0}
    if reset:
        _usage_tl.u = {"in": 0, "out": 0, "calls": 0}
    return dict(t)

# Logical model names (unchanged — the openai path uses these directly).
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")          # the main loop (cheap, tool-calling)
SUMMARY_MODEL = os.getenv("RIG_SUMMARY_MODEL", "gpt-4o")  # Step 2 summaries
GENESIS_MODEL = os.getenv("RIG_GENESIS_MODEL", "gpt-4o")  # genesis: vision + orchestration

# genaihub: which AI Core deployment each tier maps to. Defaults fall back to AICORE_DEPLOYMENT_ID
# (single-deployment mode) so the simple case still works with just one var set.
_DEFAULT_DEPLOY = os.getenv("AICORE_DEPLOYMENT_ID", "")
DEPLOY_MAIN = os.getenv("AICORE_DEPLOY_MAIN", _DEFAULT_DEPLOY)
DEPLOY_SUMMARY = os.getenv("AICORE_DEPLOY_SUMMARY", _DEFAULT_DEPLOY)
DEPLOY_GENESIS = os.getenv("AICORE_DEPLOY_GENESIS", _DEFAULT_DEPLOY)

# anthropic provider: Claude (Sonnet 4.6) on SAP GenAI Hub via the NATIVE Anthropic Messages API
# (POST .../deployments/{id}/invoke). AI Core REJECTS the OpenAI /chat/completions shim for Anthropic
# deployments, so we send the real Anthropic body + parse the Anthropic response, translating the
# rig's OpenAI-shaped transcript (and tools, and vision) both ways. Default = the hub's running
# claude-4.6-sonnet deployment; override with AICORE_DEPLOY_CLAUDE.
ANTHROPIC_DEPLOY = os.getenv("AICORE_DEPLOY_CLAUDE", "d20b9095bde7c0ef")
ANTHROPIC_VERSION = os.getenv("AICORE_ANTHROPIC_VERSION", "bedrock-2023-05-31")
ANTHROPIC_MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "8192"))


def _deployment_for(logical_model: str) -> str:
    """Map the rig's logical model name to an AI Core deployment id (genaihub path)."""
    if logical_model == SUMMARY_MODEL and DEPLOY_SUMMARY:
        return DEPLOY_SUMMARY
    if logical_model == GENESIS_MODEL and DEPLOY_GENESIS:
        return DEPLOY_GENESIS
    return DEPLOY_MAIN or _DEFAULT_DEPLOY


# ---------------------------------------------------------------------------
# OpenAI provider (default, unchanged)
# ---------------------------------------------------------------------------
_client = None


def _oai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()                     # reads OPENAI_API_KEY from the env
    return _client


# ---------------------------------------------------------------------------
# GenAI-Hub-via-destination provider
# ---------------------------------------------------------------------------
_genai_token = {"value": None, "exp": 0.0}
_genai_clients = {}   # one OpenAI client per deployment id (each has a different base_url)


def _genai_bearer() -> str:
    """AI Core token. Creds resolved from the destination (btp_destination, hop 1)."""
    import time
    import requests
    from btp_destination import get_aicore_credentials

    now = time.time()
    if _genai_token["value"] and now < _genai_token["exp"] - 60:
        return _genai_token["value"]

    creds = get_aicore_credentials()
    if creds.get("ready_bearer") and now < creds.get("ready_bearer_exp", 0) - 60:
        _genai_token["value"] = creds["ready_bearer"]
        _genai_token["exp"] = creds.get("ready_bearer_exp", now + 3600)
        return _genai_token["value"]

    tok_url = creds["tokenurl"].rstrip("/")
    if not tok_url.endswith("/oauth/token"):
        tok_url = tok_url + "/oauth/token"
    r = requests.post(
        tok_url,
        data={"grant_type": "client_credentials",
              "client_id": creds["clientid"], "client_secret": creds["clientsecret"]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )
    r.raise_for_status()
    j = r.json()
    _genai_token["value"] = j["access_token"]
    _genai_token["exp"] = now + int(j.get("expires_in", 3600))
    return _genai_token["value"]


def _genai(deployment: str) -> OpenAI:
    """An OpenAI client pointed at a specific GenAI-Hub deployment via the destination."""
    if not deployment:
        raise RuntimeError(
            "MODEL_PROVIDER=genaihub but no deployment id is set. Set AICORE_DEPLOYMENT_ID "
            "(single) or AICORE_DEPLOY_MAIN/SUMMARY/GENESIS (per-tier) in .env. Discover ids with "
            "`uv run python -c 'import model_client as m; m.genaihub_list_deployments()'`.")
    if deployment in _genai_clients:
        return _genai_clients[deployment]
    from btp_destination import get_aicore_credentials
    creds = get_aicore_credentials()
    base = creds["ai_api_url"].rstrip("/") + f"/v2/inference/deployments/{deployment}"
    rg = os.getenv("AICORE_RESOURCE_GROUP", "default")
    api_version = os.getenv("AICORE_API_VERSION", "2024-08-01-preview")
    client = OpenAI(base_url=base, api_key=_genai_bearer(),
                    default_headers={"AI-Resource-Group": rg},
                    default_query={"api-version": api_version})   # AI Core needs api-version, else 404
    _genai_clients[deployment] = client
    return client


def genaihub_list_deployments():
    """Discover AI Core model deployments + ids (set one as a deployment var)."""
    import requests
    from btp_destination import get_aicore_credentials
    creds = get_aicore_credentials()
    rg = os.getenv("AICORE_RESOURCE_GROUP", "default")
    url = creds["ai_api_url"].rstrip("/") + "/v2/lm/deployments"
    r = requests.get(url, headers={"Authorization": f"Bearer {_genai_bearer()}",
                                   "AI-Resource-Group": rg}, timeout=20)
    r.raise_for_status()
    items = r.json().get("resources", [])
    if not items:
        print(f"No deployments in resource group '{rg}'. Try another AICORE_RESOURCE_GROUP.")
        return
    print(f"AI Core deployments (resource group '{rg}'):")
    for d in items:
        mdl = (d.get("details", {}).get("resources", {}).get("backend_details", {}).get("model", {}))
        name = mdl.get("name", d.get("configurationName", "?"))
        ver = mdl.get("version", "")
        print(f"  id={d.get('id')}  model={name} {ver}  status={d.get('status')}")


# ---------------------------------------------------------------------------
# Anthropic-via-GenAI-Hub provider (NATIVE Messages API at /invoke)
# ---------------------------------------------------------------------------
# The rig speaks the OpenAI message/tool/response shape everywhere (agent.py reads .content +
# .tool_calls[].id / .function.{name,arguments}). Claude speaks Anthropic content-blocks + tool_use /
# tool_result. These translate the rig's transcript -> Anthropic and the Anthropic reply -> the exact
# object agent.py expects -- so nothing else in the rig changes.
class _Fn:
    def __init__(self, name, arguments): self.name = name; self.arguments = arguments


class _TC:
    def __init__(self, id, name, arguments):
        self.id = id; self.type = "function"; self.function = _Fn(name, arguments)


class _Msg:
    def __init__(self, content, tool_calls, reasoning=None, thinking_blocks=None):
        self.content = content
        self.tool_calls = tool_calls or None
        self.reasoning = reasoning            # the model's chain-of-thought text (display)
        self.thinking_blocks = thinking_blocks  # raw thinking blocks (with signatures) for round-trip


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return str(content or "")


def _anthropic_content(content):
    """OpenAI user content -> Anthropic content. A plain string stays a string; a vision list
    (text + image_url data URLs) becomes Anthropic text + base64 image blocks."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    blocks = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif part.get("type") == "image_url":
            url = (part.get("image_url") or {}).get("url", "")
            if url.startswith("data:") and "," in url:
                head, b64 = url.split(",", 1)
                media = head.split(";")[0].split(":", 1)[-1] or "image/png"
                blocks.append({"type": "image",
                               "source": {"type": "base64", "media_type": media, "data": b64}})
    return blocks or ""


def _to_anthropic(messages):
    """Translate the rig's OpenAI-format transcript -> (system_str_or_None, anthropic_messages).
    system messages are hoisted to the top-level `system` param; assistant tool_calls become tool_use
    blocks; role:tool messages become tool_result blocks merged into one user turn."""
    system_parts, out = [], []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            t = _text_of(msg.get("content"))
            if t:
                system_parts.append(t)
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": msg.get("tool_call_id"),
                     "content": str(msg.get("content", ""))}
            if out and out[-1].get("_tr"):                 # merge consecutive tool results into one turn
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block], "_tr": True})
        elif role == "assistant":
            blocks = []
            # Extended thinking: the raw thinking blocks (with signatures) must lead the assistant turn
            # and be passed back unmodified, or Anthropic rejects a tool-use continuation. run_turn stores
            # them on the message as `_thinking`.
            for tb in msg.get("_thinking") or []:
                blocks.append(tb)
            t = _text_of(msg.get("content"))
            if t:
                blocks.append({"type": "text", "text": t})
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (ValueError, TypeError):
                    args = {}
                blocks.append({"type": "tool_use", "id": tc.get("id"), "name": fn.get("name"), "input": args})
            out.append({"role": "assistant", "content": blocks if blocks else " "})
        elif role == "user":
            out.append({"role": "user", "content": _anthropic_content(msg.get("content"))})
    for m in out:
        m.pop("_tr", None)
    return ("\n\n".join(system_parts) or None), out


def _anthropic_tools(tools):
    """OpenAI tool specs -> Anthropic tools (function.parameters -> input_schema)."""
    out = []
    for t in tools or []:
        fn = t.get("function", t)
        out.append({"name": fn.get("name"), "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}})
    return out


def _anthropic_complete(messages, tools, temperature):
    """One Claude call via AI Core /invoke. Returns the OpenAI-shaped _Msg agent.py expects."""
    import requests
    from btp_destination import get_aicore_credentials
    if not ANTHROPIC_DEPLOY:
        raise RuntimeError("MODEL_PROVIDER=anthropic but AICORE_DEPLOY_CLAUDE is not set.")
    creds = get_aicore_credentials()
    url = creds["ai_api_url"].rstrip("/") + f"/v2/inference/deployments/{ANTHROPIC_DEPLOY}/invoke"
    system, amsgs = _to_anthropic(messages)
    body = {"anthropic_version": ANTHROPIC_VERSION, "max_tokens": ANTHROPIC_MAX_TOKENS, "messages": amsgs}
    if system:
        body["system"] = system
    if THINKING_ON:
        # Extended thinking requires temperature=1 and max_tokens > budget; surface the chain-of-thought.
        body["thinking"] = {"type": "enabled", "budget_tokens": THINKING_BUDGET}
        body["temperature"] = 1
        if ANTHROPIC_MAX_TOKENS <= THINKING_BUDGET:
            body["max_tokens"] = THINKING_BUDGET + 2048
    elif temperature is not None:
        body["temperature"] = temperature
    if tools:
        body["tools"] = _anthropic_tools(tools)
        body["tool_choice"] = {"type": "auto"}
    resp = requests.post(url, headers={"Authorization": f"Bearer {_genai_bearer()}",
                                       "AI-Resource-Group": os.getenv("AICORE_RESOURCE_GROUP", "default"),
                                       "Content-Type": "application/json"},
                         json=body, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    text, calls, think_text, think_blocks = [], [], [], []
    for block in data.get("content", []):
        bt = block.get("type")
        if bt == "text":
            text.append(block.get("text", ""))
        elif bt == "tool_use":
            calls.append(_TC(block.get("id"), block.get("name"), json.dumps(block.get("input", {}))))
        elif bt in ("thinking", "redacted_thinking"):
            think_blocks.append(block)                       # raw, with signature, for round-trip
            if bt == "thinking":
                think_text.append(block.get("thinking", ""))
    _u = data.get("usage") or {}
    _add_usage(_u.get("input_tokens"), _u.get("output_tokens"))
    return _Msg("".join(text), calls,
                reasoning="".join(think_text) or None,
                thinking_blocks=think_blocks or None)


# ---------------------------------------------------------------------------
# The seam's public surface (unchanged signatures + return shape)
# ---------------------------------------------------------------------------
def model_complete(messages, tools=None, model=None, temperature=0.2):
    """One model call. messages: OpenAI-format list. tools: OpenAI tool specs (or None).
    Returns the assistant message object (.content, .tool_calls). Shape identical across providers."""
    logical = model or MODEL
    if MODEL_PROVIDER == "anthropic":     # Claude via GenAI Hub, native Messages API
        return _anthropic_complete(messages, tools if tools else None, temperature)
    if MODEL_PROVIDER == "genaihub":
        deployment = _deployment_for(logical)
        client = _genai(deployment)
        use_model = deployment            # for genaihub the deployment IS the model
    else:
        client = _oai()
        use_model = logical
    kwargs = {"model": use_model, "messages": messages, "temperature": temperature}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    resp = client.chat.completions.create(**kwargs)
    try:                                              # TELEMETRY: openai/genaihub usage
        _add_usage(resp.usage.prompt_tokens, resp.usage.completion_tokens)
    except Exception:
        pass
    return resp.choices[0].message


def summarize(system, text, model=None):
    """A plain (no-tools) completion -- used by the tiered-memory summariser in Step 2."""
    msg = model_complete([{"role": "system", "content": system}, {"role": "user", "content": text}],
                         model=model or SUMMARY_MODEL, temperature=0)
    return msg.content or ""