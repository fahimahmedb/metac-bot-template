"""D06 offline typed-ballot recovery qualification, not a native forecast replay.
Only the first failed attempt may seed this experiment; no cherry-picking the
later attempt. No credentials, network, new inference, publication or raw export.
"""
import hashlib, json, math, statistics
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import nostream_free_f2 as x
from metaculus_bot import prompts
from metaculus_bot.aggregation_strategies import aggregate_binary_median

SOURCE_RUN = 45522739596
SOURCE_ARTIFACT = 14981893671
SOURCE_ARTIFACT_DIGEST = "sha256:de7c3c988be5de554a6875459c3394df4eb625972f6c66f167114823204b3e93"
SNAPSHOT = "1d8421df4bf505688db85cbbc645ec5a60c47240bcfb81c04a62eb6424f4248c"
PROMPT = "f47aa9399ba52e9d71057e085f61ee13d24dd29b25296afdc0e1e76f813b469e"
ORIGINAL_TIME = datetime(2026,11,25,1,22,49,tzinfo=timezone.utc)
ORIGINAL_IDS = {
    x.NEM: "gen-1795569769-YiBBnEZPCTFwsvR80JlT",
    x.GPT: "chatcmpl-afd0b2e5-3583-4661-b00a-115c9eb81fa2",
}
ORIGINAL_RESPONSE_HASHES = {
    x.NEM: "6a769d5a494f78fd814d941d889efde08bf5e1ce7379b027370e0810e62add55",
    x.GPT: "eab2e86f30d7122a2453c04a93ae27e38e35b1771a168387016bd87e78999fce",
}
ORIGINAL_BALLOTS = {x.NEM:.05, x.GPT:.04}

def require(ok, why):
    if not ok: raise ValueError(why)

def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()

def read_json(path):
    return json.loads(Path(path).read_bytes())

class FrozenPromptClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return ORIGINAL_TIME.astimezone(tz) if tz is not None else ORIGINAL_TIME.replace(tzinfo=None)

def verify_original(summary, router, direct):
    require(summary["case_id"]=="D06" and summary["candidate"]=="F2" and summary["source_sha"]==x.f.PIN, "identity")
    require(summary["snapshot_sha256"]==SNAPSHOT and summary["common_prompt"] is True, "snapshot or prompt")
    require(summary["technical_pipeline_pass"] is False and summary["aggregation_verified"] is False and summary["report"] is None and summary["published"]==0, "not original failure")
    require(summary["attempts"]==5 and summary["openrouter_cost_usd"]==0 and summary["members"]==ORIGINAL_BALLOTS, "original ballots")
    require(set(summary["strict_block_valid"])==set(ORIGINAL_BALLOTS) and all(v is True for v in summary["strict_block_valid"].values()), "strict validation")
    require(len(router)==1 and len(direct)==2, "dispatch shape")
    n=router[0]
    g=next(r for r in direct if r["role"]==x.GPT)
    missing=next(r for r in direct if r["role"]==x.GEM)
    require(n["model"]==n["returned_model"]==x.NEM.removeprefix("openrouter/") and n["finish"]=="stop" and n["cost"]==0, "Nemotron receipt")
    require(g["provider"]=="cerebras" and g["requested_model"]==g["returned_model"]=="gpt-oss-120b" and g["finish"]=="stop" and g["strict_block_valid"] is True, "GPT receipt")
    require(n["structured_probability"]==.05 and g["structured_forecast"]["posterior_prob"]==.04, "parsed ballot mismatch")
    for role,r in ((x.NEM,n),(x.GPT,g)):
        require(r["id"]==ORIGINAL_IDS[role] and r["response_sha256"]==ORIGINAL_RESPONSE_HASHES[role] and r["prompt_sha256"]==PROMPT, "response provenance mismatch")
    require(missing["prompt_sha256"]==PROMPT and missing["provider"]=="google" and missing["requested_model"]=="gemma-4-26b-a4b-it" and [a["http"] for a in missing["dispatches"]]==[503,503,503], "missing member mismatch")
    return dict(ORIGINAL_BALLOTS)

def reconstruct_prompt():
    # Offline only: use the original source constructor and exact frozen evidence.
    # This deliberately does not export prompt text or relax the live date guard.
    q,evidence,sha=x.load_diverse_input()
    require(sha==SNAPSHOT and q.id_of_question==990016, "question identity")
    # Reuse the same pure provider-section assembly as the actual orchestrator.
    # The first probe incorrectly passed the raw custom source, omitting its header.
    from metaculus_bot.research.section_format import assemble_provider_sections
    from metaculus_bot.research.provider_diagnostics import ProviderResult
    research,_=assemble_provider_sections([(evidence,ProviderResult(name="custom",status="ok",chars=len(evidence),latency_ms=0))])
    with patch.object(prompts,"datetime",FrozenPromptClock):
        prompt=prompts.binary_prompt(q,research)
    require(isinstance(prompt,str) and digest(prompt)==PROMPT, "exact original prompt NOT reproduced")
    return {"prompt_sha256":digest(prompt),"prompt_bytes":len(prompt.encode()),"snapshot_sha256":sha}

def test_only_complete(original, *, missing_role, value, prompt_sha, synthetic):
    """Offline test helper; intentionally not a live admission or a real ballot."""
    require(synthetic is True, "no live admission")
    require(original==ORIGINAL_BALLOTS, "original member set")
    require(missing_role==x.GEM and missing_role not in original and prompt_sha==PROMPT, "role/prompt mismatch")
    require(type(value) in (float,int) and math.isfinite(value) and .01<=value<=.99,"invalid missing probability")
    ballots={**original,missing_role:value}
    require(set(ballots)==set(x.ROSTER), "incomplete roster")
    result=aggregate_binary_median(list(ballots.values()))
    require(result==round(statistics.median(ballots.values()),3), "aggregation mismatch")
    return result

def main():
    x.f.assert_no_platform_credentials()
    # No real key is supplied to this job. Python-level network seams are
    # fail-closed for this offline test, including the original transports.
    with patch("socket.socket.connect",side_effect=AssertionError("network forbidden")), patch("socket.create_connection",side_effect=AssertionError("network forbidden")), patch.object(x.f,"request",side_effect=AssertionError("network forbidden")), patch.object(x,"direct_request",side_effect=AssertionError("network forbidden")):
        root=Path("original")
        summary=read_json(root/"g2-summary.json")
        router=read_json(root/"ledger.json")
        direct=read_json(root/"direct-ledger.json")
        original=verify_original(summary,router,direct)
        prompt=reconstruct_prompt()
        require(test_only_complete(original,missing_role=x.GEM,value=.12,prompt_sha=PROMPT,synthetic=True)==.05,"synthetic aggregate")
        for role,value,sha,synthetic in ((x.NEM,.12,PROMPT,True),(x.GEM,True,PROMPT,True),(x.GEM,float("nan"),PROMPT,True),(x.GEM,.12,"bad",True),(x.GEM,.12,PROMPT,False)):
            try:test_only_complete(original,missing_role=role,value=value,prompt_sha=sha,synthetic=synthetic)
            except ValueError:pass
            else:raise AssertionError("bad recovery admitted")
        bad=json.loads(json.dumps(summary));bad["members"][x.GPT]=.13
        try:verify_original(bad,router,direct)
        except ValueError:pass
        else:raise AssertionError("tampered original admitted")
        print("D06_RECOVERY_OFFLINE="+json.dumps({**prompt,"original_run":SOURCE_RUN,"original_artifact":SOURCE_ARTIFACT,"original_artifact_digest":SOURCE_ARTIFACT_DIGEST,"verified_original_roles":sorted(original),"missing_role":x.GEM,"synthetic_tests_passed":7,"inference_calls":0,"actual_recovered_report":False,"native_pipeline_pass":False,"published":0},sort_keys=True))

if __name__=="__main__":main()
