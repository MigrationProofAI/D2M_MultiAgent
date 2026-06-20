"""BTP destination consumer — hop 1 of the GenAI-Hub lift.

The rig can't see the raw AI Core service key (deliberately withheld). It CAN see the
*destination service* key (`proj-vector-destination-service` → `energymind-destination-key`).
So we do the standard two-hop:

    (this file, hop 1)  destination-service xsuaa token  ->  GET destination 'aicore'
                        ->  returns the AI Core OAuth creds + AI_API_URL
    (model_client, hop 2)  AI Core xsuaa token  ->  call the GenAI-Hub model deployment

Nothing here is rig-specific; it's the generic "fetch a BTP destination from outside CF" dance.
All creds come from the env (the destination-service key JSON values) — never hard-coded.

Env it reads (paste from the energymind-destination-key JSON):
    BTP_DEST_CLIENTID        <- clientid
    BTP_DEST_CLIENTSECRET    <- clientsecret
    BTP_DEST_AUTH_URL        <- url        (the xsuaa token endpoint, .../oauth/token is appended if missing)
    BTP_DEST_URI             <- uri        (the destination service base, e.g. https://destination-configuration...)
    BTP_DEST_NAME            <- the destination to fetch (default: aicore)
"""
import os
import time
import requests

_DEST_TOKEN = {"value": None, "exp": 0.0}      # cached destination-service token
_AICORE = {"data": None, "exp": 0.0}           # cached resolved aicore creds (re-fetched hourly)


def _need(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise RuntimeError(f"btp_destination: missing env {key} (paste it from the destination-service key JSON)")
    return v


def _dest_token() -> str:
    """xsuaa client-credentials token for the DESTINATION SERVICE itself."""
    now = time.time()
    if _DEST_TOKEN["value"] and now < _DEST_TOKEN["exp"] - 60:
        return _DEST_TOKEN["value"]
    auth = _need("BTP_DEST_AUTH_URL").rstrip("/")
    if not auth.endswith("/oauth/token"):
        auth = auth + "/oauth/token"
    r = requests.post(
        auth,
        data={"grant_type": "client_credentials",
              "client_id": _need("BTP_DEST_CLIENTID"),
              "client_secret": _need("BTP_DEST_CLIENTSECRET")},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )
    r.raise_for_status()
    j = r.json()
    _DEST_TOKEN["value"] = j["access_token"]
    _DEST_TOKEN["exp"] = now + int(j.get("expires_in", 3600))
    return _DEST_TOKEN["value"]


def get_aicore_credentials() -> dict:
    """Hop 1: fetch the `aicore` destination and return its AI Core OAuth creds + API url.

    Returns a dict like:
        {"clientid": ..., "clientsecret": ..., "tokenurl": ..., "ai_api_url": ...}
    Cached for ~1h (destinations are slow-moving).
    """
    now = time.time()
    if _AICORE["data"] and now < _AICORE["exp"]:
        return _AICORE["data"]

    name = os.getenv("BTP_DEST_NAME", "aicore")
    base = _need("BTP_DEST_URI").rstrip("/")
    # Destination service API: GET /destination-configuration/v1/destinations/<name>
    url = f"{base}/destination-configuration/v1/destinations/{name}"
    r = requests.get(url, headers={"Authorization": f"Bearer {_dest_token()}"}, timeout=20)
    r.raise_for_status()
    payload = r.json()

    # The destination's own auth fields live under destinationConfiguration.
    dc = payload.get("destinationConfiguration", payload)
    # For OAuth2ClientCredentials destinations, the consumable token + creds are exposed here:
    creds = {
        "clientid": dc.get("clientId") or dc.get("clientid"),
        "clientsecret": dc.get("clientSecret") or dc.get("clientsecret"),
        "tokenurl": dc.get("tokenServiceURL") or dc.get("tokenServiceUrl"),
        "ai_api_url": dc.get("URL") or dc.get("url"),
    }
    # Some destination-service responses also return a ready 'authTokens' bearer — keep it if present.
    auth_tokens = payload.get("authTokens") or []
    if auth_tokens and isinstance(auth_tokens, list):
        tok = auth_tokens[0]
        creds["ready_bearer"] = tok.get("value")
        creds["ready_bearer_type"] = tok.get("type", "Bearer")
        creds["ready_bearer_exp"] = now + int(tok.get("expires_in", 0) or 0)

    missing = [k for k in ("clientid", "clientsecret", "tokenurl", "ai_api_url")
               if not creds.get(k) and "ready_bearer" not in creds]
    if missing and "ready_bearer" not in creds:
        raise RuntimeError(
            f"btp_destination: aicore destination returned but missing {missing}. "
            f"Got keys: {list(dc.keys())}. Inspect the raw response (set BTP_DEST_DEBUG=1).")

    if os.getenv("BTP_DEST_DEBUG"):
        safe = {k: ("<set>" if "secret" in k or "bearer" in k else v) for k, v in creds.items()}
        print(f"[btp_destination] resolved aicore: {safe}")

    _AICORE["data"] = creds
    _AICORE["exp"] = now + 3600
    return creds


if __name__ == "__main__":
    # Smoke test: prove the two env hops work before wiring the model client.
    # Run:  uv run python btp_destination.py
    print("[btp_destination] fetching destination-service token...")
    _dest_token()
    print("[btp_destination] token OK. Fetching aicore destination...")
    c = get_aicore_credentials()
    safe = {k: ("<set>" if "secret" in k or "bearer" in k else v) for k, v in c.items()}
    print("[btp_destination] aicore resolved:", safe)
    print("\nNext: discover the model deployment id (see model_client.py genaihub_list_deployments()).")
