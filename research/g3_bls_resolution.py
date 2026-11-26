"""Offline BLS development event definitions and resolution receipt checks.

No fetching, scheduling, forecasting, confirmatory admission or outcome access.
Only caller-supplied same-day source bytes; first-success capture provenance
must be verified separately. Existing BLS candidate and baseline identities reused.
"""
import hashlib,json,sys
from datetime import datetime,timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from g3_bls_candidates import SPECS,TARGET,CUTOFF,month_num,outcomes
from g3_bls_rolling import EXPECTED

DATES={"cpi":"2027-02-16","payroll":"2027-02-08","openings":"2027-03-12"}
IDS={"cpi":"G3DEV-BLS-CPI-202701","payroll":"G3DEV-BLS-PAYROLL-202701","openings":"G3DEV-BLS-JOLTS-202701"}
ARTIFACTS={"cpi":15080845381,"payroll":15080487386,"openings":15080980024}
SOURCE_RUN=45739662391
SOURCE_HEAD="f79391ab15227f1706ac83cc8a3e22490046f6dd"
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(doc):return json.dumps(doc,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def utc(s):
    d=datetime.fromisoformat(s.replace("Z","+00:00"))
    require(d.tzinfo is not None and d.utcoffset().total_seconds()==0,"UTC required")
    return d
def source(key):return "https://api.bls.gov/publicAPI/v1/timeseries/data/"+SPECS[key]["series"]
def number(s):
    require(type(s) is str,"published decimal text required")
    d=Decimal(s)
    require(d.is_finite() and d>0,"invalid published level")
    return Fraction(d)
def classify(key,previous,current):
    a,b=number(previous),number(current)
    spec=SPECS[key];threshold=Fraction(Decimal(spec["threshold"]))
    # Exact rational comparison, including equality; no rounded headline.
    return int((100*(b-a)>=threshold*a) if spec["transform"]=="percentage_change" else b-a>=threshold)
def definition(key):
    s=SPECS[key]
    return {"id":IDS[key],"candidate":key,"series":s["series"],"family":s["family"],"partition":"development_only","type":"binary","target_month":TARGET,"previous_month":"2026-12","threshold":s["threshold"],"transform":s["transform"],"forecast_before":"2027-01-01T00:00:00Z","resolution_source":source(key),"capture_date_utc":DATES[key],"capture_rule":"first successful official same-day API response with both levels; no backfill; first-success evidence separate","snapshot_sha256":EXPECTED[key],"source_run":SOURCE_RUN,"source_head":SOURCE_HEAD,"artifact_id":ARTIFACTS[key],"confirmatory_eligible":False,"inference_authorized":False}
def prepare(key,raw):
    require(sha(raw)==EXPECTED[key],"snapshot identity")
    d=json.loads(raw)
    require(d["candidate"]==key and d["definition"]==SPECS[key] and d["target"]==TARGET and d["observation_cutoff"]==CUTOFF and d["source"]==source(key),"source definition")
    require(utc(d["retrieved_at"]).date().isoformat()=="2026-11-26","frozen retrieval window")
    rows=d["rows"]
    require(rows==sorted(rows) and len({r[0] for r in rows})==len(rows),"rows")
    require(all("2024-01"<=r[0]<=CUTOFF for r in rows),"cutoff")
    for month,value in rows:month_num(month);number(value)
    ys=[classify(key,a[1],b[1]) for a,b in zip(rows,rows[1:]) if month_num(b[0])==month_num(a[0])+1]
    require(ys==outcomes(rows,SPECS[key]),"arithmetic disagreement")
    p=(sum(ys)+1)/(len(ys)+2)
    require(len(ys)==d["baseline"]["n"] and sum(ys)==d["baseline"]["yes"] and abs(p-d["baseline"]["probability"])<1e-12,"baseline mismatch")
    e=definition(key)
    return {"definition":e,"definition_sha256":sha(canonical(e)),"baseline":{"n":len(ys),"yes":sum(ys),"probability":p},"source_sha256_reported":d["source_sha256"],"original_api_bytes_independently_verified":False,"status":"READY_DEVELOPMENT_DEFINITION_ONLY","inference_calls":0,"outcomes_accessed":0}
def evaluate_capture(key,raw,captured_at,source_url,expected_sha):
    e=definition(key)
    require(source_url==e["resolution_source"],"wrong source")
    require(utc(captured_at).date().isoformat()==e["capture_date_utc"],"outside registered capture date")
    require(sha(raw)==expected_sha,"capture bytes mismatch")
    obj=json.loads(raw)
    require(obj["status"]=="REQUEST_SUCCEEDED","BLS request not successful")
    series=obj["Results"]["series"]
    require(len(series)==1 and series[0]["seriesID"]==e["series"],"series mismatch")
    values={}
    for r in series[0]["data"]:
        if r["period"] not in ("M01","M12"):continue
        month=r["year"]+"-"+r["period"][1:]
        if month not in (e["target_month"],e["previous_month"]):continue
        require(month not in values,"duplicate target month")
        values[month]=r["value"]
    result={"id":e["id"],"definition_sha256":sha(canonical(e)),"captured_at":captured_at,"source_url":source_url,"source_sha256":expected_sha,"status":"UNRESOLVED","value":None,"first_success_independently_verified":False,"capture_provenance_independently_verified":False,"admission":False}
    if set(values)!={e["target_month"],e["previous_month"]} or any(v in (None,"-",".","") for v in values.values()):return result
    result.update(status="TYPED_CANDIDATE_NOT_ADMITTED",value=classify(key,values[e["previous_month"]],values[e["target_month"]]))
    return result
def tests():
    def reject(fn):
        try:fn()
        except (ValueError,KeyError,ArithmeticError,TypeError):return
        raise AssertionError("invalid input admitted")
    require(classify("cpi","100","100.3")==1 and classify("cpi","100","100.299999")==0,"CPI threshold")
    require(classify("payroll","1000","1100")==1 and classify("payroll","1000","1099")==0,"payroll threshold")
    require(classify("openings","100","100")==1 and classify("openings","100","99")==0,"openings threshold")
    def response(rows,series=SPECS["cpi"]["series"]):
        return canonical({"status":"REQUEST_SUCCEEDED","Results":{"series":[{"seriesID":series,"data":rows}]}})
    rows=[{"year":"2026","period":"M12","value":"100"},{"year":"2027","period":"M01","value":"100.3"}]
    raw=response(rows)
    at="2027-02-16T12:00:00Z"
    def check(b=raw,t=at,u=source("cpi"),digest=None):
        return evaluate_capture("cpi",b,t,u,sha(b) if digest is None else digest)
    r=check()
    require(r["status"]=="TYPED_CANDIDATE_NOT_ADMITTED" and r["value"]==1 and not r["admission"] and not r["first_success_independently_verified"],"claim ceiling")
    require(check(response(rows[:1]))["status"]=="UNRESOLVED","missing month")
    require(check(response([rows[0],dict(rows[1],value="-")]))["status"]=="UNRESOLVED","missing level")
    reject(lambda:check(t="2027-02-17T00:00:00Z"))
    reject(lambda:check(t="2027-02-16T00:00:00+01:00"))
    reject(lambda:check(u="https://example.invalid"))
    reject(lambda:check(digest="0"*64))
    reject(lambda:check(response(rows+[rows[0]])))
    reject(lambda:check(response(rows,"wrong")))
    reject(lambda:check(response([rows[0],dict(rows[1],value="NaN")])))
    require(not definition("cpi")["confirmatory_eligible"] and len(set(DATES.values()))==3,"definition scope")
    print("BLS_RESOLUTION_TESTS_PASS=14 synthetic_only=true")
if __name__=="__main__":
    tests()
    if sys.argv[1:]==["--test"]:sys.exit(0)
    key=sys.argv[1]
    result=prepare(key,Path(sys.argv[2]).read_bytes())
    Path("bls-definition.json").write_bytes(canonical(result))
    print("BLS_DEFINITION="+json.dumps(result,sort_keys=True))
