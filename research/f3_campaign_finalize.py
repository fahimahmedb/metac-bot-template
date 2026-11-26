"""Finite, read-only F3 campaign finalizer; no inference or retry authority.

Inputs are GitHub run/job metadata and artifacts downloaded by the workflow.
Missing/inconsistent evidence is BLOCK/UNKNOWN, never silently a success.
The aggregate is a technical gate, not a predictive or billing qualification.
"""
import hashlib,json,math,statistics,sys
from pathlib import Path
from g2_numeric_receipt_audit import independent_expected

PIN="79c1d7a1192a00724646ab05c67f3b776d2d7b65"
NEM="openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
GPT="openrouter/openai/gpt-oss-120b"
ERNIE="openrouter/baidu/ernie-5.5-flash-preview:free"
UTIL="openrouter/google/gemma-4-26b-a4b-it"
ROLES={NEM,GPT,ERNIE}
PROVIDERS={NEM.removeprefix("openrouter/"):"nvidia",ERNIE.removeprefix("openrouter/"):"baidu"}
SPECS={
 "F301":("binary",990031,"25abefef6ef13f8346a5669cc52e52981867f5e9a58215606daa167e67a74815"),
 "F302":("multiple_choice",990032,"320b3e7a322aa5b4831778f959b4b260ae45ca0ff1fbfe0b0a0cbdf5d8061721"),
 "F303":("numeric",990033,"c69d9bba0dd7f22761d0788188926368935ab79f0b993202ed7020cbe1f16804"),
 "F304":("multiple_choice",990034,"26bbb1fd280179316d7a358e9eb401a29498d8b7cfc860d4ccaac1f1aa86abc4"),
 "F310":("numeric",990040,"b8ebef5f84312adfc372716bac39a39fa1bbc8a543bd13ed78d48b202154db6a"),
 "F306":("binary",990036,"1d8421df4bf505688db85cbbc645ec5a60c47240bcfb81c04a62eb6424f4248c"),
 "F307":("binary",990037,"25abefef6ef13f8346a5669cc52e52981867f5e9a58215606daa167e67a74815"),
 "F308":("numeric",990038,"c69d9bba0dd7f22761d0788188926368935ab79f0b993202ed7020cbe1f16804"),
 "F309":("multiple_choice",990039,"320b3e7a322aa5b4831778f959b4b260ae45ca0ff1fbfe0b0a0cbdf5d8061721"),
}
COHORTS={"pilot":["F301","F302","F303"],"diverse":["F304","F310","F306","F307","F308","F309"]}
OPTIONS={k:("Below 80","80 to below 140","140 or higher") for k in ("F302","F309")}
OPTIONS["F304"]=("Negative","Zero to below 0.5%","0.5% or higher")
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(s):
    return isinstance(s,str) and len(s)==64 and all(c in "0123456789abcdef" for c in s)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(path.read_text())
def probability(x):return type(x) in (int,float) and math.isfinite(x) and 0<=x<=1

def mc_expected(members,names):
    raw=[max(.01,min(.99,statistics.median(v[n] for v in members))) for n in names]
    p=[v/sum(raw) for v in raw]
    fixed=set()
    for _ in names:
        bad=[i for i,v in enumerate(p) if i not in fixed and not .01<=v<=.99]
        if not bad:break
        for i in bad:
            p[i]=.01 if p[i]<.01 else .99
            fixed.add(i)
        free=[i for i in range(len(p)) if i not in fixed]
        if not free:break
        total=sum(p[i] for i in free)
        require(total>0,"MC normalization")
        factor=(1-sum(p[i] for i in fixed))/total
        for i in free:p[i]*=factor
    return dict(zip(names,p,strict=True))

def check_summary(case,d,router,direct):
    kind,qid,snapshot=SPECS[case]
    require(d["case"]==case and d["qid"]==qid and d["question_type"]==kind and d["source_sha"]==PIN and d["snapshot_sha256"]==snapshot and d["candidate"]=="F3","identity")
    require(d["technical_pipeline_pass"] is True and d["common_prompt"] is True and d["aggregation_verified"] is True and d["degradation"]==0 and d["engine_error"] is None and d["published"]==0,"pipeline flags")
    require(d["openrouter_cost_usd"]==0 and d["openrouter_after"]["usage"]==0 and d["openrouter_after"]["is_free_tier"] is True,"cost")
    require(type(d["attempts"]) is int and 3<=d["attempts"]<=4,"attempt count")
    require(len(router)==2 and {r["model"] for r in router}==set(PROVIDERS),"router roles")
    for r in router:
        require(r["cost"]==0 and r["finish"]=="stop" and r["returned_model"]==r["model"] and r["provider"].casefold()==PROVIDERS[r["model"]],"router result")
    g=[r for r in direct if r["role"]==GPT]
    require(len(g)==1 and g[0]["provider"]=="cerebras" and g[0]["returned_model"]=="gpt-oss-120b" and g[0]["finish"]=="stop","direct role")
    require(len(direct)<=2 and all(r["role"] in (GPT,UTIL) and len(r["dispatches"])==1 for r in direct),"direct budget")
    require(len(router)+sum(len(r["dispatches"]) for r in direct)==d["attempts"],"ledger count")
    require(all(sha(r.get("prompt_sha256")) and sha(r.get("response_sha256")) and isinstance(r.get("id"),str) and r["id"] for r in router+g),"response identity")
    require(len({r["prompt_sha256"] for r in router+g})==1,"prompt mismatch")
    members=d["members"];actual=d["report"]
    require(set(members)==ROLES,"member roles")
    vals=list(members.values())
    if kind=="binary":
        require(all(probability(v) for v in vals+[actual]),"binary ballot")
        err=abs(actual-round(statistics.median(vals),3))
        require(err<=1e-3,"binary median")
    elif kind=="multiple_choice":
        names=OPTIONS[case]
        require(all(set(v)==set(names) and all(probability(x) and .01-1e-9<=x<=.99+1e-9 for x in v.values()) and abs(sum(v.values())-1)<=1e-6 for v in vals+[actual]),"MC ballot")
        expected=mc_expected(vals,names)
        err=max(abs(expected[n]-actual[n]) for n in names)
        require(err<=1e-6,"MC median")
    else:
        expected=independent_expected(vals,"D04" if case=="F310" else "D03")
        require(len(actual)==201 and all(probability(p) for p in actual),"numeric shape")
        err=max(abs(a-b) for a,b in zip(expected,actual,strict=True))
        require(err<=1e-9,"numeric reconstruction mismatch")
    return err

def audit(case,cohort,run_id,head,run,jobs,folder):
    require(case in COHORTS[cohort],"case outside cohort")
    require(run["id"]==run_id and run["head_sha"]==head and run["run_attempt"]==1,"run identity")
    matches=[j for j in jobs["jobs"] if j["name"].startswith("real ("+case+",")]
    require(len(matches)==1,"missing/duplicate job identity")
    job=matches[0]
    require(job["head_sha"]==head and job["status"]=="completed","job not terminal")
    result={"case":case,"cohort":cohort,"source_run":run_id,"source_head":head,"source_job":job["id"],"job_conclusion":job["conclusion"],"status":"BLOCK","dispatches_lower":0,"dispatches_upper":4,"reason":"terminal failure or missing receipt","inference_calls":0}
    try:
        router=read(folder/"ledger.json");direct=read(folder/"direct-ledger.json")
        require(isinstance(router,list) and isinstance(direct,list) and all(isinstance(r.get("dispatches"),list) for r in direct),"ledger shape")
        count=len(router)+sum(len(r["dispatches"]) for r in direct)
        # Preserve observed ledger count even if the summary is missing or cap breached.
        result["dispatches_lower"]=count
        result["dispatches_upper"]=max(4,count)
        require(count<=4,"observed dispatch budget exceeded")
        raw=(folder/"f3-native-summary.json").read_bytes()
        d=json.loads(raw)
        result["summary_sha256"]=digest(raw)
        require(job["conclusion"]=="success","source job not successful")
        result["aggregation_max_abs_error"]=check_summary(case,d,router,direct)
        result.update(status="PASS",reason="terminal source job and receipt reconciled; fixture-specific arithmetic",dispatches_upper=count)
    except (ValueError,KeyError,TypeError,OSError,AttributeError) as e:
        result["reason"]=str(e)[:250]
        if "exceeded" in result["reason"]:result["status"]="STOP"
    return result

def consolidate(cohort,run_id,head,folder):
    results=[]
    for case in COHORTS[cohort]:
        try:
            r=read(folder/case/"audit.json")
            require(r["case"]==case and r["cohort"]==cohort and r["source_run"]==run_id and r["source_head"]==head,"audit identity")
            require(r["status"] in ("PASS","BLOCK","STOP") and type(r["dispatches_lower"]) is int and type(r["dispatches_upper"]) is int and 0<=r["dispatches_lower"]<=r["dispatches_upper"],"audit budget")
            if r["status"]=="STOP":
                require(r["dispatches_lower"]>4,"unsubstantiated excess")
            else:
                require(r["dispatches_upper"]<=4,"audit budget")
            if r["status"]=="PASS":
                require(3<=r["dispatches_lower"]==r["dispatches_upper"]<=4,"PASS count")
                require(type(r.get("source_job")) is int and r["source_job"]>0 and r.get("job_conclusion")=="success" and sha(r.get("summary_sha256")) and r.get("inference_calls")==0,"PASS receipt identity")
                err=r.get("aggregation_max_abs_error")
                require(type(err) in (int,float) and math.isfinite(err) and 0<=err<=(1e-3 if SPECS[case][0]=="binary" else 1e-6 if SPECS[case][0]=="multiple_choice" else 1e-9),"PASS aggregation proof")
        except (ValueError,KeyError,TypeError,OSError):
            r={"case":case,"status":"BLOCK","dispatches_lower":0,"dispatches_upper":4,"reason":"audit missing or invalid"}
        results.append(r)
    valid=[r["case"] for r in results if r["status"]=="PASS"]
    stop=any(r["status"]=="STOP" for r in results)
    ok=len(valid)==len(results)
    return {"cohort":cohort,"source_run":run_id,"source_head":head,"status":"STOP" if stop else "PASS_TECHNICAL_ONLY" if ok else "BLOCK","passed":valid,"unresolved":[r["case"] for r in results if r["status"]!="PASS"],"dispatches_lower":sum(r["dispatches_lower"] for r in results),"dispatches_upper":sum(r["dispatches_upper"] for r in results),"cap":4*len(results),"cases":results,"dispatch_bounds_scope":"observed ledger lower; unresolved upper conditional on cap adherence, not account-wide guarantee","next_action":"STOP_REVIEW_BUDGET_NO_AUTO_RETRY" if stop else "REVIEW_G3_ADMISSION" if ok and cohort=="diverse" else "DIVERSE_FRESH_WINDOW" if ok else "INSPECT_UNRESOLVED_ONLY_NO_AUTO_RETRY","automatic_live_admission":False,"predictive_skill":"UNKNOWN","direct_billing":"UNVERIFIED","published":0,"inference_calls":0}

def tests():
    import tempfile
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        r=consolidate("pilot",1,"head",root)
        require(r["status"]=="BLOCK" and r["dispatches_upper"]==12,"missing receipts admitted")
        for i,c in enumerate(COHORTS["pilot"]):
            p=root/c;p.mkdir()
            (p/"audit.json").write_text(json.dumps({"case":c,"cohort":"pilot","source_run":1,"source_head":"head","status":"PASS","dispatches_lower":3,"dispatches_upper":3,"source_job":i+1,"job_conclusion":"success","summary_sha256":"a"*64,"aggregation_max_abs_error":0,"inference_calls":0}))
        require(consolidate("pilot",1,"head",root)["status"]=="PASS_TECHNICAL_ONLY","complete cohort")
        (root/"F302"/"audit.json").unlink()
        r=consolidate("pilot",1,"head",root)
        require(r["passed"]==["F301","F303"] and r["unresolved"]==["F302"] and r["dispatches_upper"]==10,"local block erased successes")
        require(consolidate("pilot",2,"head",root)["status"]=="BLOCK","wrong run admitted")
        run={"id":1,"head_sha":"head","run_attempt":1}
        jobs={"jobs":[{"name":"real (F301, binary)","head_sha":"head","status":"completed","conclusion":"failure","id":2}]}
        a=audit("F301","pilot",1,"head",run,jobs,root)
        require(a["status"]=="BLOCK" and a["dispatches_upper"]==4,"failed job admitted")
        # New adversarial cases: a false PASS without receipt, zero dispatches,
        # and an over-cap ledger with no summary must not pass or lose counts.
        f=root/"F302"/"audit.json"
        base=read(root/"F301"/"audit.json")|{"case":"F302","source_job":2}
        f.write_text(json.dumps({k:v for k,v in base.items() if k!="summary_sha256"}))
        require(consolidate("pilot",1,"head",root)["status"]=="BLOCK","missing receipt identity admitted")
        f.write_text(json.dumps(base|{"dispatches_lower":0,"dispatches_upper":0}))
        require(consolidate("pilot",1,"head",root)["status"]=="BLOCK","zero-call PASS admitted")
        (root/"ledger.json").write_text(json.dumps([{}]*5))
        (root/"direct-ledger.json").write_text("[]")
        a=audit("F301","pilot",1,"head",run,jobs,root)
        require(a["status"]=="STOP" and a["dispatches_lower"]==a["dispatches_upper"]==5,"excess count lost")
        (root/"F301"/"audit.json").write_text(json.dumps(a))
        f.write_text(json.dumps(base))
        result=consolidate("pilot",1,"head",root)
        require(result["status"]=="STOP" and result["dispatches_lower"]==result["dispatches_upper"]==11 and result["next_action"]=="STOP_REVIEW_BUDGET_NO_AUTO_RETRY","STOP erased by consolidation")
        (root/"ledger.json").write_text(json.dumps([{}]*3))
        a=audit("F301","pilot",1,"head",run,jobs,root)
        require(a["status"]=="BLOCK" and a["dispatches_lower"]==3 and a["dispatches_upper"]==4,"missing summary erased ledger")
    print("FINALIZER_SYNTHETIC_PASS=10")

if __name__=="__main__":
    if sys.argv[1:]==["--test"]:tests()
    elif sys.argv[1]=="audit":
        _,_,case,cohort,run,head,meta,jobs,folder=sys.argv
        r=audit(case,cohort,int(run),head,read(Path(meta)),read(Path(jobs)),Path(folder))
        Path("audit.json").write_text(json.dumps(r,sort_keys=True))
        print("CASE_AUDIT="+json.dumps(r,sort_keys=True))
    elif sys.argv[1]=="consolidate":
        _,_,cohort,run,head,folder=sys.argv
        r=consolidate(cohort,int(run),head,Path(folder))
        Path("campaign-final.json").write_text(json.dumps(r,sort_keys=True))
        print("CAMPAIGN_FINAL="+json.dumps(r,sort_keys=True))
        if r["status"]!="PASS_TECHNICAL_ONLY":raise SystemExit(1)
    else:raise SystemExit("invalid command")
