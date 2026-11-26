"""Read-only test of existing Oracle V2 admission and evidence lane boundaries.
Use actual Quant-Trade checkout and actual source export, but a local-only
snapshot and no claim, lease, commit, scheduler, model or canonical import.
"""
import hashlib,json,sys
from pathlib import Path
from unittest.mock import patch
from jsonschema import Draft202012Validator
from research.research_os.expansion.v2_stage_executor import V2StageExecutor,ACTIVE_EPOCH_PATH
from research.research_os.github_state import PREFIX
from research.research_os.worker_stages import CanonicalStageExecutor,StageBlocked,stage_plan,AUTHORITY,artifact_path
from research.research_os.worker_preflight import canonical_hash

class Snapshot:
 def __init__(self,base,values):
  self.base=base;self.values=values
  self.blobs={k:hashlib.sha1(("blob "+str(len(self.raw(v)))+"\0").encode()+self.raw(v)).hexdigest() for k,v in values.items()}
  self.head="4910c22e1e48ff84d5a927e5aa54e2493354b177"
 @staticmethod
 def raw(v):return json.dumps(v,sort_keys=True,separators=(",",":")).encode()
 def read(self,path):return self.values[path]
def require(ok,msg):
 if not ok:raise ValueError(msg)
def blocked(fn,reason):
 try:fn()
 except StageBlocked as e:
  require(str(e)==reason,"unexpected blocker: "+str(e));return str(e)
 raise AssertionError("expected block: "+reason)
def main(qt,export):
 base=qt/"research/research_os"
 def read(p):return json.loads(p.read_bytes())
 epoch=read(qt/ACTIVE_EPOCH_PATH)
 exp=read(export/"experiment-result.json");ass=read(export/"evidence-assessment.json")
 for n,d in (("experiment-result",exp),("evidence-assessment",ass)):
  Draft202012Validator(read(base/"contracts"/(n+".schema.json"))).validate(d)
 require(exp["result"]["canonical_import_performed"] is False and exp["result"]["oracle_worker_lease_claimed"] is False and ass["decision"]=="PARK","export scope")
 task={"task_id":"OFFLINE-PROBE-NEVER-QUEUED","task_type":"DATA_PROVENANCE","required_capability":"data_provenance","inputs":{},"allowed_actions":["qualify provenance source"],"forbidden_actions":["economic outcomes","prospective observation","capital action"],"authority":dict(AUTHORITY,scope="OFFLINE_PROBE_ONLY")}
 evidence={"experiment_result":exp,"evidence_assessment":ass}
 source=PREFIX+"sources/offline-probe-never-published.json"
 # Construct only in-memory input paths; never write a fake canonical receipt.
 snap=Snapshot(base,{ACTIVE_EPOCH_PATH:epoch,source:evidence})
 v2=V2StageExecutor(None);v1=CanonicalStageExecutor(None)
 require(stage_plan(task,"evidence_data")==["recover_or_qualify","provenance_check"],"native evidence stages")
 now="2026-11-26T18:27:00Z"
 with patch("socket.socket.connect",side_effect=AssertionError("network forbidden")),patch("socket.create_connection",side_effect=AssertionError("network forbidden")):
  expired=blocked(lambda:v2.execute(snap,task|{"inputs":{"source_path":source}},"evidence_data","recover_or_qualify",now,"offline"),"V2_RESEARCH_WINDOW_CLOSED")
  outside=blocked(lambda:v1.execute(snap,task|{"inputs":{"source_path":"https://github.com/fahimahmedb/metac-bot-template/actions/runs/45875846791"}},"evidence_data","recover_or_qualify",now,"offline"),"PROVENANCE_SOURCE_OUTSIDE_ADMISSIBLE_CAPTURE_STORE")
  absent=blocked(lambda:v1.execute(snap,task,"evidence_data","recover_or_qualify",now,"offline"),"EXPLICIT_PROVENANCE_SOURCE_REQUIRED")
  localtask=task|{"inputs":{"source_path":source}}
  first,writes,status=v1.execute(snap,localtask,"evidence_data","recover_or_qualify",now,"offline")
  require(first["source"]=={"path":source,"blob":snap.blobs[source],"hash":canonical_hash(evidence)} and first["outcome_accessed"] is False and first["economic_result"]=="NOT_OBSERVED" and first["authority"]==AUTHORITY,"actual base provenance binding")
  require(not writes,"unexpected durable writes")
  # Reuse exact previous-stage artifact binding, only in the in-memory snapshot.
  ap=artifact_path(localtask,"recover_or_qualify");snap.values[ap]=first
  localtask=localtask|{"execution":{"completed_stages":{"recover_or_qualify":{"artifact":ap,"artifact_hash":canonical_hash(first)}}}}
  second,writes,status2=v1.execute(snap,localtask,"evidence_data","provenance_check",now,"offline")
  require(second["source"]==first["source"] and not writes and second["outcome_accessed"] is False,"provenance stage")
  bad=localtask|{"execution":{"completed_stages":{"recover_or_qualify":{"artifact":ap,"artifact_hash":"0"*64}}}}
  stale=blocked(lambda:v1.execute(snap,bad,"evidence_data","provenance_check",now,"offline"),"DURABLE_STAGE_BINDING_MISMATCH:recover_or_qualify")
 d={"status":"BLOCK_V2_EPOCH_WINDOW_CLOSED","canonical_epoch_id":epoch["research_epoch_id"],"canonical_epoch_state":epoch["state"],"canonical_epoch_window_end":epoch["research_window"]["end"],"probe_as_of":now,"actual_v2_blocker":expired,"actual_v1_external_url_blocker":outside,"actual_v1_missing_source_blocker":absent,"actual_v1_memory_only_source_binding":True,"actual_v1_stale_stage_blocker":stale,"base_stage_statuses":[status,status2],"source_side_export_id":exp["experiment_id"],"canonical_source_admitted":False,"canonical_import_performed":False,"worker_receipt_created":False,"worker_lease_claimed":False,"new_epoch_created":False,"inference_calls":0,"economic_experiment_performed":False,"prospective_observation_performed":False,"real_capital_used":False,"live_trading_performed":False}
 Path("oracle-boundary.json").write_text(json.dumps(d,sort_keys=True))
 print("F3_ORACLE_BOUNDARY="+json.dumps(d,sort_keys=True))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
