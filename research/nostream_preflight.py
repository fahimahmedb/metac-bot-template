"""Read-only provider preflight. No inference, search queries or submissions."""
import ast
import base64
import urllib.parse
import json
import os
import urllib.request
import urllib.error

KEYS = ("METACULUS_TOKEN", "OPENROUTER_API_KEY", "OAI_ANTH_OPENROUTER_KEY",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ASKNEWS_CLIENT_ID",
        "ASKNEWS_SECRET", "EXA_API_KEY", "GOOGLE_API_KEY", "FRED_API_KEY",
        "SEC_EDGAR_CONTACT_EMAIL")

def present(name):
    value = os.environ.get(name, "").strip()
    return bool(value and value not in {"1234567890", "your_free_key_from_fred.stlouisfed.org"})

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

OPENER = urllib.request.build_opener(NoRedirect)
def get(url, headers=None, extract=None):
    try:
        req = urllib.request.Request(url, headers=headers or {}, method="GET")
        with OPENER.open(req, timeout=20) as resp:
            status = resp.status
            if extract:
                body = json.loads(resp.read(8_000_000))
                return {"http": status, "metadata": extract(body)}
            return {"http": status}
    except urllib.error.HTTPError as e:
        return {"http": e.code}
    except Exception as e:
        return {"error_type": type(e).__name__}

def asknews_auth():
    # OAuth token issuance only, no paid news request. Never log token or response body.
    try:
        raw = os.environ["ASKNEWS_CLIENT_ID"] + ":" + os.environ["ASKNEWS_SECRET"]
        auth = base64.b64encode(raw.encode()).decode("ascii")
        req = urllib.request.Request(
            "https://auth.asknews.app/oauth2/token",
            data=urllib.parse.urlencode({"grant_type":"client_credentials","scope":"news"}).encode(),
            headers={"Authorization":"Basic "+auth,
                     "Content-Type":"application/x-www-form-urlencoded",
                     "Accept":"application/json"},
            method="POST")
        with OPENER.open(req, timeout=20) as resp:
            body = json.loads(resp.read(65536))
            return {"http":resp.status,"token_issued":bool(body.get("access_token")),
                    "scope":body.get("scope"),"expires_in":body.get("expires_in")}
    except urllib.error.HTTPError as e:
        return {"http":e.code,"token_issued":False}
    except Exception as e:
        return {"error_type":type(e).__name__,"token_issued":False}

def main():
    status = {k: present(k) for k in KEYS}
    print("PRESENCE_JSON=" + json.dumps(status, sort_keys=True))
    with open("upstream/metaculus_bot/llm_configs.py") as f:
        tree = ast.parse(f.read())
    roster = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "FORECASTER_LLMS":
            for call in node.value.elts:
                if isinstance(call, ast.Call) and isinstance(call.args[0], ast.Constant):
                    roster.append(call.args[0].value.removeprefix("openrouter/"))
    if len(roster) != 3:
        raise RuntimeError("unexpected pinned roster")
    print("ROSTER_JSON=" + json.dumps(roster))
    catalog = get("https://openrouter.ai/api/v1/models", extract=lambda d: {
        row["id"]: {"prompt": row.get("pricing", {}).get("prompt"),
                    "completion": row.get("pricing", {}).get("completion")}
        for row in d.get("data", []) if row.get("id") in roster
    })
    print("CATALOG_JSON=" + json.dumps(catalog, sort_keys=True))
    probes = {}
    for key in ("OPENROUTER_API_KEY", "OAI_ANTH_OPENROUTER_KEY"):
        if status[key]:
            probes[key] = get("https://openrouter.ai/api/v1/key",
                {"Authorization": "Bearer " + os.environ[key]},
                extract=lambda d: {k: d.get("data", {}).get(k) for k in
                    ("limit", "limit_remaining", "usage", "is_free_tier")})
    if status["METACULUS_TOKEN"]:
        probes["METACULUS_TOKEN"] = get("https://www.metaculus.com/api/posts/?limit=1",
            {"Authorization": "Token " + os.environ["METACULUS_TOKEN"]},
            extract=lambda d: {"json_object":isinstance(d,dict),"has_results":isinstance(d.get("results"),list)})
        probes["METACULUS_ANONYMOUS_CONTROL"] = get("https://www.metaculus.com/api/posts/?limit=1")
    if status["ASKNEWS_CLIENT_ID"] and status["ASKNEWS_SECRET"]:
        probes["ASKNEWS_OAUTH"] = asknews_auth()
    if status["OPENAI_API_KEY"]:
        probes["OPENAI_API_KEY"] = get("https://api.openai.com/v1/models",
            {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
    if status["ANTHROPIC_API_KEY"]:
        probes["ANTHROPIC_API_KEY"] = get("https://api.anthropic.com/v1/models?limit=1",
            {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    if status["GOOGLE_API_KEY"]:
        probes["GOOGLE_API_KEY"] = get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
            {"x-goog-api-key": os.environ["GOOGLE_API_KEY"]})
    print("PROBES_JSON=" + json.dumps(probes, sort_keys=True))
    missing = [k for k in ("METACULUS_TOKEN", "OPENROUTER_API_KEY", "ASKNEWS_CLIENT_ID",
                          "ASKNEWS_SECRET", "EXA_API_KEY", "GOOGLE_API_KEY", "FRED_API_KEY",
                          "SEC_EDGAR_CONTACT_EMAIL") if not status[k]]
    print("PARITY_JSON=" + json.dumps({"missing_reference_resources": missing,
           "authenticated_metadata_only": True, "inference_executed": False,
           "paid_calls": 0, "published": 0, "verdict": "BLOCK" if missing else "UNKNOWN"}))

if __name__ == "__main__":
    main()
