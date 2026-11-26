"""Source-side, read-only Research OS export of the exact historical F3 pilot.
Reuse native F3 audit; no inference, economic experiment, canonical write or lease.
This is an immutable pilot projection; future diverse campaign needs its own
verified metadata, receipt and distinct admission, never a re-use of this pin.
"""
import hashlib,json,math,sys
from pathlib import Path
from jsonschema import Draft202012Validator
from f3_campaign_finalize import audit,require,COHORTS
SOURCE_RUN=45733982405
SOURCE_HEAD="3459896cbd0d89f4274e527b5a5ced1fcff55993"
FINAL_RUN=45739677517
FINAL_HEAD="699ec1fed11dd2c141cb75833fc2a43db30ce4c7"
FINAL_BLOB="4324eb2a899df156441b9e4651329ef567857bf6"
FINAL_ARTIFACT=15080054139
FINAL_ZIP="620ce3a42ce57b2b5032d5cf7be91c0fd90d1529710aea6a774cdf61aca0987a"
FINAL_JSON="01dd541d58f0eb6b6e1b60b9aea60372a1b6be4f7a699730c690250444ad3626"
QHEAD="aaebcb760be631585cc84cd67b2cff9cea0ae492"
REPO="fahimahmedb/metac-bot-template"
PINS={
 "F301":(139622859082,15077234210,"d6a7d9cc1e1556f4b3d6e0409263048a361b5a2fde2c943bc0e1fbd08e437f7d","3e9533d5c2e1563563617cc2e7cdb8b5fe0bad7569a1ec902fa2944c620c6341","3045b664356242f2135d332b9af949656ace6fb8d8bc6e8d7ddb556ae023df63","712abab0660a9c3bd4f4aa7ba6c96d85fdedadca59124800225ef57ece4df6a1"),
 "F302":(139622859047,15077309641,"954b608e15f87b4404fedf26deb6203035a08d0db31aff6fa0f73913461c78d6","6fdd6d53f552534ebc2305becbc80fb62b064c83ad6e3d443990f313338a5aeb","7903943dd81f2ce947fc32a06e4397e934d1edc9a6620f09df268768d3a77fb5","d5cce6d5989c426f807ec5b212ff3cd033bbe1548fd95ded7e9d4fe4a4c7af97"),
 "F303":(139622859172,15077803671,"76181e8f95f1a7f32a56cb4b0118e6a561486df634113cca4902378ba7bff13d","1823f8af70ee5e30c940b6a5e0acd866476db96770f52f14fd4e8367feffadf9","c1003434985aa214227c8c9c590883b54a7ba1f2acb2c72b43985184d78e191d","6bc376331abd8f79d5e47679b55eb30589f41828d2f8e7c7453f8fa8585f02b1"),
}
def digest(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def checked(p,expected):
    b=p.read_bytes();require(digest(b)==expected,"file digest "+p.name);return json.loads(b)
def verify_run(d,run,head):
    require((d["id"],d["head_sha"],d["status"],d["conclusion"],d["run_attempt"])==(run,head,"completed","success",1),"run binding")
def verify_artifact(d,aid,sha,run,head):
    w=d["workflow_run"]
    require(d["id"]==aid and d["digest"]=="sha256:"+sha and d["expired"] is False and (w["id"],w["head_sha"])==(run,head),"artifact binding")
def bind_final(final,rows):
    require((final["cohort"],final["source_run"],final["source_head"],final["status"],final["cap"])==("pilot",SOURCE_RUN,SOURCE_HEAD,"PASS_TECHNICAL_ONLY",12),"final scope")
    require(final["automatic_live_admission"] is False and final["predictive_skill"]=="UNKNOWN" and final["direct_billing"]=="UNVERIFIED" and final["published"]==final["inference_calls"]==0,"authority")
    require(final["cases"]==rows and final["passed"]==COHORTS["pilot"] and final["unresolved"]==[],"audit/final binding")
    require(final["dispatches_lower"]==final["dispatches_upper"]==sum(r["dispatches_lower"] for r in rows)==9,"double count")
def main(root,schemas):
    source=read(root/"source-run.json");jobs=read(root/"source-jobs.json")
    verify_run(source,SOURCE_RUN,SOURCE_HEAD)
    verify_run(read(root/"final-run.json"),FINAL_RUN,FINAL_HEAD)
    verify_artifact(read(root/f"artifact-{FINAL_ARTIFACT}.json"),FINAL_ARTIFACT,FINAL_ZIP,FINAL_RUN,FINAL_HEAD)
    final=checked(root/"final"/"campaign-final.json",FINAL_JSON)
    rows=[];strict={};case_evidence=[]
    for case in COHORTS["pilot"]:
        job,aid,zsha,summary,router,direct=PINS[case]
        verify_artifact(read(root/f"artifact-{aid}.json"),aid,zsha,SOURCE_RUN,SOURCE_HEAD)
        folder=root/case
        checked(folder/"f3-native-summary.json",summary)
        checked(folder/"ledger.json",router)
        dl=checked(folder/"direct-ledger.json",direct)
        r=audit(case,"pilot",SOURCE_RUN,SOURCE_HEAD,source,jobs,folder)
        require(r["status"]=="PASS" and r["source_job"]==job and r["summary_sha256"]==summary,"source audit")
        rows.append(r)
        strict[case]=all(x.get("strict_block_valid") is True for x in dl)
        case_evidence.append(r|{"artifact_id":aid,"artifact_zip_sha256_reported":zsha,"strict_direct_block_valid":strict[case]})
    bind_final(final,rows)
    # Reproduce material failure modes without modifying original artifacts.
    import copy
    def reject(fn):
        try:fn()
        except (ValueError,KeyError,TypeError):return
        raise AssertionError("invalid accepted")
    reject(lambda:bind_final(final|{"automatic_live_admission":True},rows))
    reject(lambda:bind_final(final|{"dispatches_lower":18,"dispatches_upper":18},rows))
    reject(lambda:bind_final(final|{"unresolved":["F302"]},rows))
    altered=copy.deepcopy(rows);altered[0]["summary_sha256"]=altered[1]["summary_sha256"]
    reject(lambda:bind_final(final,altered))
    reject(lambda:verify_run(source|{"head_sha":"0"*40},SOURCE_RUN,SOURCE_HEAD))
    a=read(root/f"artifact-{FINAL_ARTIFACT}.json")
    reject(lambda:verify_artifact(a|{"digest":"sha256:"+"0"*64},FINAL_ARTIFACT,FINAL_ZIP,FINAL_RUN,FINAL_HEAD))
    require(strict=={"F301":True,"F302":False,"F303":True},"strict block scope changed")
    result={"experiment_id":"QT_NOSTREAM_F3_PILOT_TECHNICAL_RECEIPTS_20261126","hypothesis_generation":"NON_ECONOMIC_SOFTWARE_RECEIPT_ONLY","dataset_provenance":[f"https://github.com/{REPO}/actions/runs/{SOURCE_RUN}/job/{r['source_job']}" for r in rows]+[f"https://github.com/{REPO}/actions/runs/{FINAL_RUN}/artifacts/{FINAL_ARTIFACT}"],"protocol_hash":"git-blob:"+FINAL_BLOB,"result":{"projection":"SOURCE_HOSTED_RESEARCH_OS_EXPORT_ONLY","cases":case_evidence,"source_final_run":FINAL_RUN,"source_final_artifact":FINAL_ARTIFACT,"source_final_json_sha256":FINAL_JSON,"quant_contract_head":QHEAD,"strict_direct_block_scope":"NOT_ALL_THREE_VERIFIED","new_model_calls":0,"authority":"OFFLINE_READ_ONLY_NO_ACTIVATION","canonical_import_performed":False,"oracle_worker_lease_claimed":False},"observed_attempts":9,"effective_trials_status":"UNKNOWN","limitations":["Historical technical pilot, not full diverse cohort.","F302 direct strict-block flag false; typed aggregate audit passed, raw response not retained.","Artifact ZIP digests verified against remote metadata; extracted summary and ledger bytes independently pinned.","No real outcome, direct billing verification, economic experiment or canonical import."],"evidence_timing":"RETROSPECTIVE"}
    assessment={"hypothesis_generation":"NON_ECONOMIC_SOFTWARE_RECEIPT_ONLY","mechanism":"EXISTING_F3_AUDIT_PROJECTED_TO_EXACT_RESEARCH_OS_CONTRACTS","data_integrity":"PASS_PINNED_SOURCE_SUMMARY_AND_LEDGERS","statistical":"UNKNOWN_NO_RESOLVED_OUTCOMES","economic":"UNKNOWN_NO_AUTHORIZED_EXPERIMENT","prospective":"NOT_AUTHORIZED","operational_readiness":"SOURCE_HOSTED_SCHEMA_EXPORT_ONLY_CANONICAL_IMPORT_BLOCKED","decision":"PARK","reason":"F3 pilot only; diverse gate and separate Quant-Trade admission required.","authority":"OFFLINE_READ_ONLY_NO_ACTIVATION"}
    for n,d in (("experiment-result",result),("evidence-assessment",assessment)):
        Draft202012Validator(read(schemas/(n+".schema.json"))).validate(d)
        Path(n+".json").write_text(json.dumps(d,sort_keys=True))
    print("F3_QUANT_HANDOFF_PASS="+json.dumps({"cases":len(rows),"observed_attempts":9,"synthetic_adversarial_checks":6,"schema_validations":2,"strict_direct_block_valid":strict,"canonical_import_performed":False,"oracle_worker_lease_claimed":False,"inference_calls":0,"predictive_skill":"UNKNOWN","economic_value":"UNKNOWN"},sort_keys=True))
if __name__=="__main__":main(Path(sys.argv[1]),Path(sys.argv[2]))
