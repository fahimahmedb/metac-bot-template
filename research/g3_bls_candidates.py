"""Primary BLS public-domain candidates, fixed exploratory thresholds.

No FRED, outcomes, inference, or actual confirmatory cohort admission.
January 2027 values are future; snapshots only through October 2026.
Source: US Bureau of Labor Statistics, https://www.bls.gov/opub/copyright-information.htm
"""
import hashlib,json,math,sys,urllib.request
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from g2_diverse_evidence import fetch_public

SPECS={
 "cpi":{"series":"CUSR0000SA0","family":"consumer_price_all_items","label":"US CPI-U all items seasonally adjusted index","transform":"percentage_change","threshold":"0.3","resolution_window":"2027-02-28"},
 "payroll":{"series":"CES0000000001","family":"total_nonfarm_payrolls","label":"Total nonfarm employees seasonally adjusted, thousands","transform":"difference","threshold":"100","resolution_window":"2027-02-28"},
 "openings":{"series":"JTS000000000000000JOL","family":"total_nonfarm_job_openings","label":"Total nonfarm job openings seasonally adjusted, thousands","transform":"difference","threshold":"0","resolution_window":"2027-03-31"},
}
TARGET="2027-01"
CUTOFF="2026-10"
def require(ok,msg):
    if not ok:raise ValueError(msg)
def month_num(s):
    y,m=map(int,s.split("-"));require(1<=m<=12,"month");return y*12+m
def parse(raw,series):
    obj=json.loads(raw)
    require(obj["status"]=="REQUEST_SUCCEEDED","BLS status")
    rows=obj["Results"]["series"]
    require(len(rows)==1 and rows[0]["seriesID"]==series,"series mismatch")
    result=[]
    for r in rows[0]["data"]:
        if r["period"]=="M13":continue
        require(r["period"].startswith("M"),"not monthly")
        m=r["year"]+"-"+r["period"][1:];month_num(m)
        if not "2024-01"<=m<=CUTOFF or r["value"] in (None,"-",".",""):continue
        v=Decimal(r["value"]);require(v.is_finite() and v>0,"invalid observation")
        result.append([m,str(v)])
    result.sort()
    require(len(result)>=24 and len({r[0] for r in result})==len(result),"missing/duplicate data")
    return result
def outcomes(rows,spec):
    out=[]
    for a,b in zip(rows,rows[1:]):
        if month_num(b[0])!=month_num(a[0])+1:continue
        av,bv=Decimal(a[1]),Decimal(b[1])
        change=(bv/av-1)*100 if spec["transform"]=="percentage_change" else bv-av
        out.append(int(change>=Decimal(spec["threshold"])))
    return out
def main(key):
    spec=SPECS[key]
    now=datetime.now(timezone.utc)
    require(now.date().isoformat()=="2026-11-26","source window")
    url="https://api.bls.gov/publicAPI/v1/timeseries/data/"+spec["series"]
    raw=fetch_public(url)
    rows=parse(raw,spec["series"]);ys=outcomes(rows,spec)
    require(len(ys)>=20,"insufficient contiguous comparisons")
    p=(sum(ys)+1)/(len(ys)+2)
    d={"candidate":key,"definition":spec,"target":TARGET,"observation_cutoff":CUTOFF,"retrieved_at":now.isoformat(),"source":url,"source_sha256":hashlib.sha256(raw).hexdigest(),"rows":rows,"baseline":{"method":"Laplace smoothed threshold frequency, adjacent months only","n":len(ys),"yes":sum(ys),"probability":p},"resolution_rule":"Use January and December 2026 levels from the same official BLS API snapshot captured on the registered resolution date; if not available or missed, unresolved. January refers to 2027. Use unrounded Decimal arithmetic on published levels, not headline rounded percent or first release. Final resolution date and retrieval procedure must be frozen before forecasts.","admission":"source and baseline probe only; future vintage availability and cohort independence not proved","inference_calls":0}
    # Explicitly separate the two months in the definition.
    d["resolution_rule"]=d["resolution_rule"].replace("January and December 2026 levels","January 2027 and December 2026 levels")
    data=json.dumps(d,sort_keys=True).encode()
    Path("bls-candidate.json").write_bytes(data)
    print("BLS_CANDIDATE="+json.dumps({k:v for k,v in d.items() if k!="rows"}|{"observations":len(rows),"first":rows[0][0],"last":rows[-1][0],"snapshot_sha256":hashlib.sha256(data).hexdigest()},sort_keys=True))
if __name__=="__main__":main(sys.argv[1])
