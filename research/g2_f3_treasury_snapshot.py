"""Primary-source replacement for F305; no FRED/ALFRED data or inference."""
import hashlib,json,math,urllib.request,urllib.parse
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET
SOURCE="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month="
CUTOFF="2026-11-24"
CASE={"id":"F310","qid":990040,"type":"numeric","domain":"interest rates","question":"What will be the final published US Treasury 10-year par yield curve rate dated in January 2027?","criteria":"Use the final nonmissing January 2027 10-year nominal par yield curve observation published directly by the US Treasury, in percent, as of 2027-02-15 UTC.","source":"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve","resolve":"2027-02-15T23:59:59Z","unit":"percent","lower":-2,"upper":15,"open_lower":True,"open_upper":True}
def parse(raw):
    root=ET.fromstring(raw)
    rows=[]
    for el in root.iter():
        if el.tag.split("}")[-1]!="properties":continue
        fields={c.tag.split("}")[-1]:c.text for c in el}
        d=(fields.get("NEW_DATE") or "")[:10]
        if d and "2026-09-01"<=d<=CUTOFF and fields.get("BC_10YEAR") not in (None,"","N/A"):
            v=float(fields["BC_10YEAR"])
            if not math.isfinite(v):raise ValueError("nonfinite")
            rows.append([d,v])
    return rows
def main():
    now=datetime.now(timezone.utc)
    if now.date().isoformat()!="2026-11-26":raise ValueError("snapshot window")
    rows=[];hashes={}
    for month in ("202609","202610","202611"):
        url=SOURCE+month
        with urllib.request.urlopen(url,timeout=30) as r:
            if urllib.parse.urlparse(r.geturl()).hostname!="home.treasury.gov":raise ValueError("unexpected host")
            raw=r.read(3_000_001)
        if len(raw)>3_000_000:raise ValueError("response too large")
        batch=parse(raw)
        if not batch or any(d.replace("-","")[:6]!=month for d,v in batch):raise ValueError("month mismatch")
        rows.extend(batch);hashes[month]=hashlib.sha256(raw).hexdigest()
    rows.sort()
    if len(rows)<40 or len({d for d,v in rows})!=len(rows):raise ValueError("missing or duplicate dates")
    doc={"case":CASE,"retrieved_at":now.isoformat(),"observation_cutoff":CUTOFF,"source_sha256_by_month":hashes,"observations":rows}
    raw=json.dumps(doc,sort_keys=True,ensure_ascii=True).encode()
    p=Path("treasury-input");p.mkdir(exist_ok=True);(p/"snapshot.json").write_bytes(raw)
    print("TREASURY_SNAPSHOT="+json.dumps({"case":CASE["id"],"rows":len(rows),"first":rows[0][0],"last":rows[-1][0],"sha256":hashlib.sha256(raw).hexdigest(),"source_sha256_by_month":hashes,"inference_calls":0}))
if __name__=="__main__":main()
