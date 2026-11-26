"""Hosted historical source custody qualification, not first-publication proof.
Consumes only existing GitHub artifact, run, job and log bytes.
No HTTP to producers, model calls, future outcomes or admission.
"""
import copy,io,json,re,sys,zipfile
from pathlib import Path
from g3_census_resolution import member,source,utc
from g3_census_development import SPECS,sha,canonical,require
RUN=45743246873
HEAD="7c743ee2931bf70bf653ac67a2554112550e3ca1"
REPO_ID=1467486554
PINS={
 "M3ADV":(139653086668,15082395616,"fb4e9cccf948969e9470995065d6cc0ee606b62985c0a10d67ad0dccc6fcc746"),
 "BFS":(139653086675,15081793061,"cab9db3e1984b232a7729a62aab610d9b214ff0c0be62deb7ba7dd6b24fa0739"),
 "FTD":(139653086604,15081359958,"9faf6b950598016d1a4391b428a5c8c943bb1d751d1787f93434cb9e5057c6c9")}
def unpack(raw):
 require(len(raw)<=6_000_000 and zipfile.is_zipfile(io.BytesIO(raw)),"outer archive format")
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  infos=z.infolist();names={x.filename for x in infos}
  require(len(infos)==3 and names=={"census-original-source.bin","census-public-source.zip","census-source-receipt.json"},"outer archive members")
  require(sum(x.file_size for x in infos)<=6_000_000 and all(not x.flag_bits&1 and (x.external_attr>>16)&0o170000!=0o120000 for x in infos),"outer archive bounds")
  return {k:z.read(k) for k in names}
def log_marker(log):
 lines=[]
 for line in log.splitlines():
  m=re.match(r"^(\S+) CENSUS_BULK_RESULT=(\{.*\})$",line)
  if m:lines.append((utc(m[1]),json.loads(m[2])))
 require(len(lines)==1,"unique actual producer log marker")
 return lines[0]
def verify(key,run,jobs,artifact,raw,log):
 job_id,aid,zip_hash=PINS[key]
 require((run["id"],run["head_sha"],run["run_attempt"],run["status"],run["conclusion"],run["path"])==(RUN,HEAD,1,"completed","success",".github/workflows/g3_census_bulk_probe.yaml"),"run identity")
 require(run["repository"]["id"]==REPO_ID and run["head_repository"]["id"]==REPO_ID,"repository identity")
 selected=[j for j in jobs["jobs"] if j["id"]==job_id]
 require(len(selected)==1,"job identity")
 j=selected[0]
 require((j["run_id"],j["head_sha"],j["name"],j["status"],j["conclusion"])==(RUN,HEAD,"probe ("+key+")","completed","success"),"job identity")
 w=artifact["workflow_run"]
 require((artifact["id"],artifact["name"],artifact["digest"],artifact["expired"])==(aid,"census-bulk-"+key,"sha256:"+zip_hash,False),"artifact identity")
 require((w["id"],w["head_sha"],w["repository_id"],w["head_repository_id"])==(RUN,HEAD,REPO_ID,REPO_ID),"artifact run identity")
 require(sha(raw)==zip_hash,"outer ZIP digest")
 p=unpack(raw);d=json.loads(p["census-source-receipt.json"])
 when,logged=log_marker(log);retrieved=utc(d["retrieved_at"]);created=utc(artifact["created_at"])
 # GitHub metadata timestamps are second precision. Compare integer seconds
 # for ordering against artifact creation/completion, preserve fine log time.
 require(utc(j["started_at"])<=retrieved<=when and int(when.timestamp())<=int(created.timestamp())<=int(utc(j["completed_at"]).timestamp()),"custody chronology")
 require(logged==d,"receipt/log mismatch")
 require(d["program"]==key and d["source_url"]==source(key) and d["status"]=="PUBLIC_BULK_TRANSPORT_PASS" and d["confirmatory_eligible"] is False and d["inference_calls"]==d["actual_outcomes_accessed"]==0,"scope")
 original=p["census-original-source.bin"];safe=p["census-public-source.zip"]
 require(sha(original)==d["archive_sha256"]==SPECS[key][8] and sha(safe)==d["normalized_archive_sha256"]==SPECS[key][9] and len(original)==d["archive_bytes"],"inner archive identity")
 data=member(key,original)
 with zipfile.ZipFile(io.BytesIO(safe)) as z:
  require(set(z.namelist())=={key+"-mf.csv","README"} and len(z.namelist())==2,"normalized members")
  require(z.read(key+"-mf.csv")==data and sha(data)==SPECS[key][10],"CSV byte identity")
  require(sha(z.read("README"))=="1794c7a4c9eb919fda96bbc8d92143d3e1ce2d4e1e0ea08d346fe09f4b29bf3c","README identity")
 require({r["normalized_name"]:r["sha256"] for r in d["members"]}=={key+"-mf.csv":sha(data),"README":"1794c7a4c9eb919fda96bbc8d92143d3e1ce2d4e1e0ea08d346fe09f4b29bf3c"},"member log linkage")
 return {"program":key,"run":RUN,"job":job_id,"head":HEAD,"artifact":aid,"artifact_sha256":zip_hash,"original_sha256":sha(original),"member_sha256":sha(data),"reported_retrieved_at":d["retrieved_at"],"actual_log_timestamp":when.isoformat(),"artifact_created_at":artifact["created_at"],"hosted_artifact_custody_verified":True,"producer_response_independently_authenticated":False,"first_success_verified":False,"point_in_time_vintage_verified":False,"capture_authorized":False,"status":"HISTORICAL_HOSTED_CUSTODY_PASS","inference_calls":0,"actual_outcomes_accessed":0}
def qualify(key,run,jobs,artifact,raw,log):
 out=verify(key,run,jobs,artifact,raw,log)
 def reject(*args):
  try:verify(key,*args)
  except (ValueError,KeyError,TypeError,ArithmeticError,zipfile.BadZipFile):return
  raise AssertionError("invalid custody accepted")
 reject(run|{"head_sha":"0"*40},jobs,artifact,raw,log)
 reject(run|{"run_attempt":2},jobs,artifact,raw,log)
 bad=copy.deepcopy(jobs);next(j for j in bad["jobs"] if j["id"]==PINS[key][0])["started_at"]="2027-01-01T00:00:00Z"
 reject(run,bad,artifact,raw,log)
 reject(run,jobs,artifact|{"created_at":"2026-11-25T00:00:00Z"},raw,log)
 reject(run,jobs,artifact|{"digest":"sha256:"+"0"*64},raw,log)
 reject(run,jobs,artifact,raw+b"x",log)
 reject(run,jobs,artifact,raw,log.replace("PUBLIC_BULK_TRANSPORT_PASS","ALTERED_STATUS"))
 reject(run,jobs,artifact,raw,log+"\n"+log)
 require(out["hosted_artifact_custody_verified"] and not any(out[k] for k in ("producer_response_independently_authenticated","first_success_verified","point_in_time_vintage_verified","capture_authorized")),"claim ceiling")
 return out|{"adversarial_checks":8}
if __name__=="__main__":
 key=sys.argv[1];p=Path(sys.argv[2])
 r=qualify(key,*[json.loads((p/n).read_bytes()) for n in ("run.json","jobs.json","artifact.json")],(p/"artifact.zip").read_bytes(),(p/"job.log").read_text())
 Path("census-custody.json").write_bytes(canonical(r))
 print("CENSUS_CUSTODY="+json.dumps(r,sort_keys=True))
