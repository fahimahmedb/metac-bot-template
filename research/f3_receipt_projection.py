"""Preserve typed technical forecasts beyond Actions artifact expiration.

Uses existing audited case receipts; never exports raw prompts, model text,
source observation rows, credentials or future outcomes. No inference.
Projection is not an official submission, confirmation or economic signal.
"""
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
from f3_campaign_finalize import audit,COHORTS,SPECS,ROLES,GPT,require,digest,read

def utc(s):
    d=datetime.fromisoformat(s.replace("Z","+00:00"))
    require(d.tzinfo is not None and d.utcoffset().total_seconds()==0,"UTC identity")
    return d
def run_identity(d,run,head):
    require(d["id"]==run and d["head_sha"]==head and d["run_attempt"]==1,"run identity")
def artifact_identity(meta,name,run,head):
    matches=[a for a in meta["artifacts"] if a["name"]==name]
    require(len(matches)==1,"artifact identity")
    a=matches[0];w=a["workflow_run"]
    require(a["expired"] is False and w["id"]==run and w["head_sha"]==head and isinstance(a.get("digest"),str) and a["digest"].startswith("sha256:"),"artifact metadata mismatch")
    return {"id":a["id"],"zip_sha256_reported":a["digest"],"expires_at":a["expires_at"]}
def case_projection(case,cohort,source_run,head,run,jobs,artifacts,root,expected):
    name=("f3-native-" if cohort=="pilot" else "f3-diverse-")+case+"-receipt"
    folder=root/name
    actual=audit(case,cohort,source_run,head,run,jobs,folder)
    require(actual==expected and actual["status"]=="PASS","source audit not identical")
    meta=artifact_identity(artifacts,name,source_run,head)
    raw=(folder/"f3-native-summary.json").read_bytes()
    require(digest(raw)==actual["summary_sha256"],"summary hash")
    d=json.loads(raw)
    router=read(folder/"ledger.json");direct=read(folder/"direct-ledger.json")
    g=[r for r in direct if r["role"]==GPT]
    require(len(g)==1 and set(d["members"])==ROLES,"role identity")
    receipts=router+g
    job=next(j for j in jobs["jobs"] if j["id"]==actual["source_job"])
    started=utc(job["started_at"]);completed=utc(job["completed_at"])
    timestamps=[utc(r["issued_at"]) for r in receipts]
    event_start=utc("2027-02-01T00:00:00Z" if case in ("F307","F308","F309") else "2027-01-01T00:00:00Z")
    require(started<=min(timestamps)<=max(timestamps)<=completed<event_start,"forecast timing")
    return {"case":case,"qid":d["qid"],"question_type":d["question_type"],"source_run":source_run,"source_head":head,"source_job":job["id"],"artifact":meta,"summary_sha256":actual["summary_sha256"],"snapshot_sha256":d["snapshot_sha256"],"upstream_sha":d["source_sha"],"common_prompt_sha256":receipts[0]["prompt_sha256"],"latest_dispatch_at":max(timestamps).isoformat(),"forecast_issued_no_later_than":completed.isoformat(),"event_start":event_start.isoformat(),"members":d["members"],"aggregate":d["report"],"dispatches":d["attempts"],"published":0,"scope":"technical noncontest forecast projection; no resolved outcome, no predictive claim"}
def main(cohort,source_run,head,final_run,final_head,root):
    root=Path(root);source_run=int(source_run);final_run=int(final_run)
    require(cohort in COHORTS,"cohort")
    run=read(root/"source-run.json");jobs=read(root/"source-jobs.json")
    run_identity(run,source_run,head);run_identity(read(root/"final-run.json"),final_run,final_head)
    artifacts=read(root/"source-artifacts.json")
    final_artifact=artifact_identity(read(root/"final-artifacts.json"),"f3-campaign-final",final_run,final_head)
    raw=(root/"final"/"campaign-final.json").read_bytes();final=json.loads(raw)
    require(final["cohort"]==cohort and final["source_run"]==source_run and final["source_head"]==head and final["status"] in ("PASS_TECHNICAL_ONLY","BLOCK","STOP"),"final identity")
    require(final["automatic_live_admission"] is False and final["predictive_skill"]=="UNKNOWN" and final["published"]==0,"authority mismatch")
    rows={r["case"]:r for r in final["cases"]};require(set(rows)==set(COHORTS[cohort]) and len(rows)==len(final["cases"]),"case identity")
    require(set(final["passed"])=={c for c,r in rows.items() if r["status"]=="PASS"},"pass set mismatch")
    forecasts=[];blocked=[]
    for case in COHORTS[cohort]:
        if rows[case]["status"]!="PASS":
            blocked.append({"case":case,"reason":"source technical gate "+rows[case]["status"]});continue
        try:forecasts.append(case_projection(case,cohort,source_run,head,run,jobs,artifacts,root/"source",rows[case]))
        except (ValueError,KeyError,TypeError,OSError,StopIteration) as e:blocked.append({"case":case,"reason":str(e)[:200]})
    require(len(forecasts)+len(blocked)==len(rows),"coverage")
    out={"schema":"f3-typed-projection-v1","cohort":cohort,"source_run":source_run,"source_head":head,"final_run":final_run,"final_head":final_head,"final_json_sha256":hashlib.sha256(raw).hexdigest(),"final_artifact":final_artifact,"technical_status":final["status"],"projection_status":"PASS" if not blocked else "PARTIAL_OR_BLOCK","forecasts":forecasts,"blocked":blocked,"prediction_skill":"UNKNOWN","actual_outcomes_scored":0,"inference_calls":0,"publication_authorized":False,"canonical_write_performed":False}
    Path("typed-forecast-projection.json").write_text(json.dumps(out,sort_keys=True,separators=(",",":")))
    print("F3_TYPED_PROJECTION="+json.dumps(out,sort_keys=True,separators=(",",":")))
    if blocked:raise SystemExit("BLOCK: incomplete projection; preserve available records")
if __name__=="__main__":main(*sys.argv[1:])
