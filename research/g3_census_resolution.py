"""Offline resolution adapter for the three frozen Census development events.
Reuse archive path validation, exact parser and threshold arithmetic.
Caller-supplied bytes/times never establish official provenance or admission.
No future data download, forecasting, orders or scheduling.
"""
import io,json,sys,zipfile
from datetime import datetime
from pathlib import Path
from g3_census_bulk_probe import inspect
from g3_census_development import SPECS,HISTORY,canonical,sha,parse,event,make,require,prev

DEFINITIONS={
 "M3ADV":"b7e8a0d8116c8cdd74cce15db593ea2a32523a3e52b0327d4e05a8942093f883",
 "BFS":"9a0e869ade79b7ed16437e077029f83b6a5711e52c37bdace15710e084cbbfce",
 "FTD":"0413cb6b4446631bc3a0c4766b8da737ffca0e0fa1710b2875eecd8258c93aa2"}
def utc(s):
 t=datetime.fromisoformat(s.replace("Z","+00:00"));require(t.tzinfo is not None and t.utcoffset().total_seconds()==0,"UTC required");return t
def source(key):return "https://www.census.gov/econ_getzippedfile/?programCode="+key
def member(key,raw):
 # Validate paths before using only the in-memory rebuilt ZIP.
 buf=io.BytesIO()
 with zipfile.ZipFile(buf,"w") as z:meta=inspect(raw,allow_official_root=True,normalized_zip=z)
 require(len(meta)==2 and {r["normalized_name"] for r in meta}=={key+"-mf.csv","README"},"wrong program or member set")
 with zipfile.ZipFile(buf) as z:
  data=z.read(key+"-mf.csv")
  require(sha(data)==next(r["sha256"] for r in meta if r["normalized_name"]==key+"-mf.csv"),"member identity")
 return data
def check_definition(key,receipt):
 d=receipt["definition"];h=sha(canonical(d))
 require(h==receipt["definition_sha256"]==DEFINITIONS[key],"frozen definition identity")
 require(d["program"]==key and d["authorization"]=="DEVELOPMENT_ONLY" and not any(d[x] for x in ("inference_authorized","capture_authorized","confirmatory_eligible","capture_provenance_verified")),"authority")
 return d
def candidate(key,receipt,raw,url,captured_at,expected_sha,now):
 d=check_definition(key,receipt);stamp=utc(captured_at)
 require(url==source(key) and sha(raw)==expected_sha,"source identity")
 require(stamp.date().isoformat()==d["capture_date_utc"] and stamp<=utc(now),"wrong capture date or future timestamp")
 require(utc(d["forecast_before"])<stamp,"forecast timing")
 data=member(key,raw);periods=[d["comparison"],d["target"]]
 values=parse(data,key,periods)
 result={"program":key,"definition_sha256":DEFINITIONS[key],"source_url":url,"captured_at":captured_at,"archive_sha256":expected_sha,"member_sha256":sha(data),"status":"UNRESOLVED","value":None,"capture_provenance_verified":False,"first_success_verified":False,"outcome_admitted":False}
 if set(values)!=set(periods):return result
 return result|{"status":"CANDIDATE_NOT_ADMITTED","value":int(event(key,values[periods[0]],values[periods[1]]))}
def fixture(key,previous,current):
 c,t,u,target,*_=SPECS[key];months="Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
 def display(v):y,m=v.split("-");return months[int(m)-1]+"-"+y
 data=f"CATEGORIES\ncat_idx,cat_code,cat_desc,cat_indent\n1,{c},total,0\nDATA TYPES\ndt_idx,dt_code,dt_desc,dt_unit\n1,{t},value,{u}\nGEO LEVELS\ngeo_idx,geo_code,geo_desc\n1,US,total\nTIME PERIODS\nper_idx,per_name\n1,{display(prev(target))}\n2,{display(target)}\nDATA\nper_idx,cat_idx,dt_idx,geo_idx,is_adj,val\n1,1,1,1,1,{previous}\n2,1,1,1,1,{current}\n".encode()
 return data
def archive(key,data,name=None,extra=None):
 b=io.BytesIO()
 with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z:
  z.writestr(name or key+"-mf.csv",data);z.writestr("/README","synthetic fixture")
  if extra:z.writestr(*extra)
 return b.getvalue()
def qualify(key,receipt,raw):
 d=check_definition(key,receipt)
 data=member(key,raw)
 require(sha(raw)==SPECS[key][8] and sha(data)==SPECS[key][10],"historical archive identity")
 # Historical smoke over the SAME pinned archive, never future capture.
 old=make(key,data);require(old==receipt,"exact frozen receipt")
 v=parse(data,key,HISTORY);require(set(v)==set(HISTORY),"historical completeness")
 labels=[event(key,v[a],v[b]) for a,b in zip(HISTORY,HISTORY[1:])]
 require(sum(labels)==receipt["reference"]["yes"] and len(labels)==23,"historical arithmetic")
 def check(a,at=None,url=None,h=None,now=None,r=None):
  stamp=at or d["capture_date_utc"]+"T12:00:00Z"
  return candidate(key,r or receipt,a,url or source(key),stamp,h or sha(a),now or stamp)
 def reject(fn):
  try:fn()
  except (ValueError,KeyError,TypeError,ArithmeticError,zipfile.BadZipFile):return
  raise AssertionError("invalid capture accepted")
 a,b,c=("-9000","-8000","-8001") if key=="FTD" else ("100","101","100.9999")
 good=archive(key,fixture(key,a,b))
 z=check(good);require(z["value"]==1 and z["status"]=="CANDIDATE_NOT_ADMITTED" and not z["outcome_admitted"] and not z["first_success_verified"] and not z["capture_provenance_verified"],"equality/claim")
 require(check(archive(key,fixture(key,a,c)))["value"]==0,"below threshold")
 require(check(archive(key,fixture(key,a,"NA")))["status"]=="UNRESOLVED","missing target")
 reject(lambda:check(good,at="2027-01-01T12:00:00Z"))
 reject(lambda:check(good,at=d["capture_date_utc"]+"T12:00:00+01:00"))
 reject(lambda:check(good,now="2026-11-26T00:00:00Z"))
 reject(lambda:check(good,url="https://example.invalid"))
 reject(lambda:check(good,h="0"*64))
 reject(lambda:check(good,r=receipt|{"definition_sha256":"0"*64}))
 reject(lambda:check(archive(key,fixture(key,a,b),name="other-mf.csv")))
 reject(lambda:check(archive(key,fixture(key,a,b),extra=("README","duplicate"))))
 reject(lambda:check(archive(key,fixture(key,a,b),extra=("../escape","invalid"))))
 reject(lambda:check(archive(key,fixture(key,a,b)+b"2,1,1,1,1,99\n")))
 require(check(archive(key,fixture(key,a,b).replace(b",1,"+b.encode()+b"\n",b",0,"+b.encode()+b"\n")))["status"]=="UNRESOLVED","wrong adjustment")
 # A historical snapshot cannot resolve a future event even with a claimed capture date.
 require(check(raw)["status"]=="UNRESOLVED","historical archive masquerading as future capture")
 return {"program":key,"definition_sha256":DEFINITIONS[key],"historical_source_sha256":sha(raw),"historical_reference_n":23,"historical_reference_yes":sum(labels),"synthetic_checks":15,"status":"OFFLINE_RESOLVER_QUALIFIED","actual_outcomes_accessed":0,"inference_calls":0,"capture_authorized":False,"capture_provenance_verified":False,"confirmatory_pairs":0}
if __name__=="__main__":
 key=sys.argv[1];receipt=json.loads(Path(sys.argv[2]).read_bytes());raw=Path(sys.argv[3]).read_bytes()
 result=qualify(key,receipt,raw)
 Path("census-resolution-qualification.json").write_bytes(canonical(result))
 print("CENSUS_RESOLUTION_QUALIFICATION="+json.dumps(result,sort_keys=True))
