"""Read-only adapter of the existing typed F3 projection into Research OS.
Generic pilot/diverse receipt accounting, preserving partial and STOP states.
Only historical pilot is host-qualified here; synthetic diverse is not inference.
No canonical import, lease, promotion, publication or economic experiment.
"""
import copy,hashlib,io,json,math,statistics,sys,zipfile
from datetime import datetime
from pathlib import Path
from jsonschema import Draft202012Validator
from f3_campaign_finalize import COHORTS,SPECS,ROLES,PIN,OPTIONS,mc_expected,independent_expected,probability,require,sha
REPO="fahimahmedb/metac-bot-template"
QHEAD="4910c22e1e48ff84d5a927e5aa54e2493354b177"
PILOT={
 "projection":(45742181591,"730fdc8e85a499c8beaa9202ce1aa8f22c506a5a",15081707313,"68f1234985f4618002873c4869ca0a83ae0072d920b5e432a33eeb8b03cb2f20","typed-forecast-projection.json","c05b7a12d2bbe47cabbf4160f1f90ff26ac39315dcc59c2ee1eca7520047fdd1"),
 "final":(45739677517,"699ec1fed11dd2c141cb75833fc2a43db30ce4c7",15080054139,"620ce3a42ce57b2b5032d5cf7be91c0fd90d1529710aea6a774cdf61aca0987a","campaign-final.json","01dd541d58f0eb6b6e1b60b9aea60372a1b6be4f7a699730c690250444ad3626")}
def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def utc(s):
 t=datetime.fromisoformat(s.replace("Z","+00:00"));require(t.tzinfo is not None and t.utcoffset().total_seconds()==0,"UTC");return t
def unique(rows,key):
 out={}
 for r in rows:
  k=r[key];require(k not in out,"duplicate "+key);out[k]=r
 return out
def integer(x):return type(x) is int and x>=0
def validate_typed(r,a,cohort,source_run,source_head):
 c=r["case"];kind,qid,snapshot=SPECS[c]
 require((r["qid"],r["question_type"],r["snapshot_sha256"],r["upstream_sha"])==(qid,kind,snapshot,PIN),"typed case identity")
 require((r["source_run"],r["source_head"],r["source_job"],r["summary_sha256"])==(source_run,source_head,a["source_job"],a["summary_sha256"]),"typed/audit binding")
 require(sha(r["summary_sha256"]) and sha(r["common_prompt_sha256"]) and r["published"]==0,"typed receipt scope")
 require(r["dispatches"]==a["dispatches_lower"]==a["dispatches_upper"] and type(r["dispatches"]) is int and 3<=r["dispatches"]<=4,"typed dispatch count")
 art=r["artifact"];require(integer(art["id"]) and art["id"]>0 and art["zip_sha256_reported"].startswith("sha256:") and sha(art["zip_sha256_reported"][7:]),"typed artifact")
 start=utc("2027-02-01T00:00:00Z" if c in ("F307","F308","F309") else "2027-01-01T00:00:00Z")
 require(utc(r["event_start"])==start and utc(r["latest_dispatch_at"])<=utc(r["forecast_issued_no_later_than"])<start,"typed timing")
 require(set(r["members"])==ROLES,"member roles")
 vals=list(r["members"].values());v=r["aggregate"]
 if kind=="binary":
  require(all(probability(x) for x in vals+[v]) and abs(v-round(statistics.median(vals),3))<=1e-3,"binary arithmetic")
 elif kind=="multiple_choice":
  names=OPTIONS[c];require(all(isinstance(x,dict) and set(x)==set(names) and all(probability(y) for y in x.values()) and abs(sum(x.values())-1)<=1e-6 for x in vals+[v]),"MC shape")
  e=mc_expected(vals,names);require(max(abs(v[n]-e[n]) for n in names)<=1e-6,"MC arithmetic")
 else:
  require(isinstance(v,list) and len(v)==201 and all(probability(x) for x in v),"numeric shape")
  e=independent_expected(vals,"D04" if c=="F310" else "D03")
  require(max(abs(x-y) for x,y in zip(v,e,strict=True))<=1e-9,"numeric arithmetic")
 return {"case":c,"qid":qid,"question_type":kind,"source_job":a["source_job"],"source_artifact":art["id"],"artifact_zip_sha256_reported":art["zip_sha256_reported"],"summary_sha256":r["summary_sha256"],"snapshot_sha256":snapshot,"issued_no_later_than":r["forecast_issued_no_later_than"],"dispatches":r["dispatches"]}
def project(p,f,final_bytes_sha,projection_bytes_sha,provenance):
 cohort=f["cohort"];require(cohort in COHORTS,"cohort")
 cs=COHORTS[cohort];run=f["source_run"];head=f["source_head"]
 require(integer(run) and run>0 and isinstance(head,str) and len(head)==40 and all(c in "0123456789abcdef" for c in head),"source identity")
 require(p["schema"]=="f3-typed-projection-v1" and (p["cohort"],p["source_run"],p["source_head"],p["final_json_sha256"])==(cohort,run,head,final_bytes_sha),"projection binding")
 require(sha(final_bytes_sha) and sha(projection_bytes_sha),"receipt bytes")
 require(f["automatic_live_admission"] is False and f["direct_billing"]=="UNVERIFIED" and f["predictive_skill"]=="UNKNOWN" and f["inference_calls"]==f["published"]==0,"final authority")
 require(p["prediction_skill"]=="UNKNOWN" and p["publication_authorized"] is False and p["canonical_write_performed"] is False and p["actual_outcomes_scored"]==p["inference_calls"]==0,"projection authority")
 rows=unique(f["cases"],"case");require(set(rows)==set(cs),"final coverage")
 for c,a in rows.items():
  lo,hi=a["dispatches_lower"],a["dispatches_upper"]
  require(integer(lo) and integer(hi) and lo<=hi and a["status"] in ("PASS","BLOCK","STOP"),"budget receipt")
  if a["status"]=="STOP":require(lo>4,"STOP not evidenced")
  else:require(hi<=4,"case cap")
  if a["status"]=="PASS":
   require(a["cohort"]==cohort and a["source_run"]==run and a["source_head"]==head and a["job_conclusion"]=="success" and integer(a["source_job"]) and a["source_job"]>0 and sha(a["summary_sha256"]) and 3<=lo==hi<=4,"PASS evidence")
   err=a["aggregation_max_abs_error"];tol=1e-3 if SPECS[c][0]=="binary" else 1e-6 if SPECS[c][0]=="multiple_choice" else 1e-9
   require(type(err) in (int,float) and math.isfinite(err) and 0<=err<=tol,"audit arithmetic")
  if "source_run" in a:require(a["source_run"]==run and a["source_head"]==head,"row source")
 passed=[c for c in cs if rows[c]["status"]=="PASS"];unresolved=[c for c in cs if c not in passed]
 require(f["passed"]==passed and f["unresolved"]==unresolved,"audit coverage lists")
 require(len({rows[c]["source_job"] for c in passed})==len(passed),"duplicate PASS job")
 lo=sum(r["dispatches_lower"] for r in rows.values());hi=sum(r["dispatches_upper"] for r in rows.values())
 require(f["dispatches_lower"]==lo and f["dispatches_upper"]==hi and f["cap"]==4*len(cs),"campaign accounting")
 expected="STOP" if any(a["status"]=="STOP" for a in rows.values()) else "PASS_TECHNICAL_ONLY" if len(passed)==len(cs) else "BLOCK"
 require(f["status"]==p["technical_status"]==expected,"campaign status")
 forecasts=unique(p["forecasts"],"case");blocked=unique(p["blocked"],"case")
 require(set(forecasts)<=set(passed) and set(forecasts).isdisjoint(blocked) and set(forecasts)|set(blocked)==set(cs),"projection coverage")
 require(p["projection_status"]==("PASS" if not blocked else "PARTIAL_OR_BLOCK"),"projection status")
 require(all(isinstance(x["reason"],str) and x["reason"] for x in blocked.values()),"block evidence")
 evidence=[validate_typed(forecasts[c],rows[c],cohort,run,head) for c in cs if c in forecasts]
 require(len({x["source_artifact"] for x in evidence})==len(evidence),"duplicate source artifact")
 status="STOP" if expected=="STOP" else "PASS_TECHNICAL_ONLY" if expected=="PASS_TECHNICAL_ONLY" and not blocked else "BLOCK"
 result={"experiment_id":f"QT_NOSTREAM_F3_{cohort.upper()}_SOURCE_{run}","hypothesis_generation":"NON_ECONOMIC_SOFTWARE_RECEIPT_ONLY","dataset_provenance":provenance,"protocol_hash":"git-blob:4324eb2a899df156441b9e4651329ef567857bf6","result":{"cohort":cohort,"source_run":run,"source_head":head,"technical_status":expected,"export_status":status,"typed_cases":evidence,"unprojected_cases":[c for c in cs if c in blocked],"dispatches_lower":lo,"dispatches_upper_conditional":hi,"campaign_cap":f["cap"],"final_json_sha256":final_bytes_sha,"typed_projection_sha256":projection_bytes_sha,"quant_contract_head":QHEAD,"new_model_calls":0,"canonical_import_performed":False,"oracle_worker_lease_claimed":False,"predictive_skill":"UNKNOWN","economic_value":"UNKNOWN"},"observed_attempts":lo,"effective_trials_status":"UNKNOWN","limitations":["Historical technical receipt projection only; no resolved outcomes or prospective evidence.","Dispatch lower is recorded ledger count; unresolved upper conditional on cap adherence, not account-wide billing proof.","Source typed projection does not preserve all strict output flags; raw model responses not verified here.","No canonical import, lease or financial experiment."],"evidence_timing":"RETROSPECTIVE"}
 assessment={"hypothesis_generation":result["hypothesis_generation"],"mechanism":"EXISTING_TYPED_F3_RECEIPT_TO_RESEARCH_OS","data_integrity":status,"statistical":"UNKNOWN_NO_RESOLVED_OUTCOMES","economic":"UNKNOWN_NO_AUTHORIZED_EXPERIMENT","prospective":"NOT_AUTHORIZED","operational_readiness":"SOURCE_SIDE_EXPORT_ONLY_CANONICAL_IMPORT_BLOCKED","decision":"PARK","reason":"STOP budget review; no automatic retry." if status=="STOP" else "Incomplete technical projection; inspect only unresolved cases." if status=="BLOCK" else "Technical receipt only; scientific and canonical admission separate.","authority":"OFFLINE_READ_ONLY_NO_ACTIVATION"}
 return result,assessment
def pinned_archive(root,key):
 run,head,aid,zsha,name,h=PILOT[key]
 r=json.loads((root/(key+"-run.json")).read_bytes())
 a=json.loads((root/(key+"-artifact.json")).read_bytes());w=a["workflow_run"]
 require((r["id"],r["head_sha"],r["status"],r["conclusion"],r["run_attempt"])==(run,head,"completed","success",1),"hosted run")
 require(a["id"]==aid and a["digest"]=="sha256:"+zsha and a["expired"] is False and (w["id"],w["head_sha"])==(run,head),"hosted artifact")
 zraw=(root/(key+".zip")).read_bytes();require(digest(zraw)==zsha,"outer bytes")
 with zipfile.ZipFile(io.BytesIO(zraw)) as z:
  require(z.namelist()==[name],"archive member");raw=z.read(name)
 require(digest(raw)==h,"JSON bytes")
 return json.loads(raw),h
def tests(p,f,ph,fh,provenance,validators):
 def check(pp,ff,hh=fh):
  a,b=project(pp,ff,hh,ph,provenance)
  validators[0].validate(a);validators[1].validate(b);return a,b
 a,b=check(p,f);require(a["observed_attempts"]==9 and a["result"]["export_status"]=="PASS_TECHNICAL_ONLY" and b["decision"]=="PARK","real pilot")
 def reject(pp,ff):
  try:check(pp,ff)
  except (ValueError,KeyError,TypeError,ArithmeticError):return
  raise AssertionError("invalid projection accepted")
 reject(p|{"canonical_write_performed":True},f)
 reject(p|{"final_json_sha256":"0"*64},f)
 reject(p,f|{"dispatches_lower":18})
 reject(p|{"forecasts":p["forecasts"]+[p["forecasts"][0]]},f)
 bad=copy.deepcopy(p);bad["forecasts"][0]["aggregate"]=.99;reject(bad,f)
 bad=copy.deepcopy(p);bad["forecasts"][1]["artifact"]=bad["forecasts"][0]["artifact"];reject(bad,f)
 bad=copy.deepcopy(p);bad["forecasts"][0]["forecast_issued_no_later_than"]="2027-01-01T00:00:00Z";reject(bad,f)
 partial=p|{"forecasts":p["forecasts"][:2],"blocked":[{"case":"F303","reason":"synthetic missing projection"}],"projection_status":"PARTIAL_OR_BLOCK"}
 x,_=check(partial,f);require(x["observed_attempts"]==9 and x["result"]["export_status"]=="BLOCK" and len(x["result"]["typed_cases"])==2,"partial export count")
 # Diverse synthetic fixture: two complete types, a missing projection,
 # blocked rows, then an observed budget breach. Never output it as evidence.
 pp=copy.deepcopy(p);ff=copy.deepcopy(f);cs=COHORTS["diverse"]
 mapping={"F301":"F306","F302":"F309","F303":"F308"}
 ff.update(cohort="diverse",cap=24)
 pp.update(cohort="diverse")
 for r in ff["cases"]:r.update(case=mapping[r["case"]],cohort="diverse")
 for r in pp["forecasts"]:
  c=mapping[r["case"]];kind,qid,snapshot=SPECS[c]
  r.update(case=c,qid=qid,question_type=kind,snapshot_sha256=snapshot,event_start="2027-02-01T00:00:00Z" if c in ("F308","F309") else "2027-01-01T00:00:00Z")
 ff["cases"] += [{"case":c,"status":"BLOCK","dispatches_lower":1,"dispatches_upper":4,"reason":"synthetic incomplete"} for c in ("F304","F310","F307")]
 ff["passed"]=[c for c in cs if c in mapping.values()];ff["unresolved"]=[c for c in cs if c not in ff["passed"]]
 ff.update(status="BLOCK",dispatches_lower=12,dispatches_upper=21)
 pp.update(technical_status="BLOCK",projection_status="PARTIAL_OR_BLOCK",blocked=[{"case":c,"reason":"synthetic incomplete"} for c in ff["unresolved"]])
 x,_=check(pp,ff);require(x["observed_attempts"]==12 and x["result"]["dispatches_upper_conditional"]==21 and x["result"]["export_status"]=="BLOCK","diverse partial")
 row=next(r for r in ff["cases"] if r["case"]=="F310");row.update(status="STOP",dispatches_lower=5,dispatches_upper=5)
 ff.update(status="STOP",dispatches_lower=16,dispatches_upper=22);pp["technical_status"]="STOP"
 x,y=check(pp,ff);require(x["observed_attempts"]==16 and x["result"]["export_status"]=="STOP" and "no automatic retry" in y["reason"],"STOP propagation")
 reject(pp,ff|{"status":"BLOCK"})
 return a,b
if __name__=="__main__":
 root=Path(sys.argv[1]);schemas=Path(sys.argv[2])
 p,ph=pinned_archive(root,"projection");f,fh=pinned_archive(root,"final")
 require(p["final_run"]==PILOT["final"][0] and p["final_head"]==PILOT["final"][1] and p["final_artifact"]["id"]==PILOT["final"][2] and p["final_artifact"]["zip_sha256_reported"]=="sha256:"+PILOT["final"][3],"projection final identity")
 validators=[Draft202012Validator(json.loads((schemas/(n+".schema.json")).read_bytes())) for n in ("experiment-result","evidence-assessment")]
 prov=[f"https://github.com/{REPO}/actions/runs/{PILOT[k][0]}/artifacts/{PILOT[k][2]}" for k in ("projection","final")]
 prov += [f"https://github.com/{REPO}/actions/runs/{p['source_run']}/job/{r['source_job']}" for r in p["forecasts"]]
 a,b=tests(p,f,ph,fh,prov,validators)
 for n,d in (("experiment-result",a),("evidence-assessment",b)):Path(n+".json").write_bytes(canonical(d))
 print("F3_RESEARCH_OS_PROJECTION_PASS="+json.dumps({"actual_pilot_cases":len(a["result"]["typed_cases"]),"historical_observed_attempts":a["observed_attempts"],"synthetic_diverse_partial_and_stop":True,"schema_validations_per_successful_projection":2,"negative_checks":8,"inference_calls":0,"canonical_import_performed":False,"economic_value":"UNKNOWN"},sort_keys=True))
