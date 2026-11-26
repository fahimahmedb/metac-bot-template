"""Three official public Census bulk files, metadata qualification only.
No Data API key, no API call, no model, no future outcomes or admission.
Source: U.S. Census Bureau, Business and Industry Time Series/Trend Charts,
https://www.census.gov/econ_datasets/ . Preserve original public ZIP bytes
for later exact series selection; never execute or extract arbitrary paths.
"""
import hashlib,io,json,re,sys,zipfile
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
from unittest.mock import patch
import g2_diverse_evidence as transport
SPECS={
 "M3ADV":"Advance Monthly Manufacturers' Shipments, Inventories, and Orders",
 "BFS":"Business Formation Statistics",
 "FTD":"U.S. International Trade in Goods and Services"}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def inspect(raw,allow_official_root=False,normalized_zip=None):
    require(len(raw)<=2_000_000 and zipfile.is_zipfile(io.BytesIO(raw)),"archive size/type")
    report=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        members=z.infolist()
        require(0<len(members)<=40 and sum(x.file_size for x in members)<=30_000_000,"archive members/size")
        # ZIPs sometimes use Windows separators. Normalize for validation
        # only, then read by ZipInfo; no extraction or filesystem writes.
        names=set()
        for i in members:
            normalized=i.filename.replace("\\","/")
            # Official Census bulk generator uses root-level names such as
            # /README. Interpret that archive namespace only for this source.
            # Never allow rooted directories, drives, traversal or UNC names.
            if allow_official_root and re.fullmatch(r"/[A-Za-z0-9_.-]+",normalized):
                normalized=normalized[1:]
            p=PurePosixPath(normalized)
            require(not p.is_absolute() and ".." not in p.parts and not re.match(r"^[A-Za-z]:",normalized) and "\x00" not in normalized and not i.flag_bits&1 and (i.external_attr>>16)&0o170000!=0o120000,"unsafe member "+repr(i.filename)[:120])
            name=str(p)
            require(name not in names,"duplicate normalized member")
            names.add(name)
            if i.is_dir():continue
            b=z.read(i)
            item={"name":i.filename,"normalized_name":name,"bytes":len(b),"sha256":sha(b)}
            if normalized_zip is not None:
                safe=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));safe.compress_type=zipfile.ZIP_DEFLATED
                normalized_zip.writestr(safe,b)
            # Only metadata/header previews, never observation values in logs.
            if p.suffix.lower() in (".txt",".csv",".tsv",".dat",".mf",""):
                text=b.decode("utf-8-sig",errors="replace")
                first=text.splitlines()[:3]
                item["first_line_format"]=[{"length":len(l),"tabs":l.count("\t"),"commas":l.count(","),"pipes":l.count("|")} for l in first]
                # Metadata dictionaries can be inspected separately using raw
                # archive; no row values exposed in this summary.
            report.append(item)
    return report
def tests():
    def make(name="sample.txt"):
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z:z.writestr(name,"header\n2024,1\n")
        return b.getvalue()
    require(inspect(make())[0]["name"]=="sample.txt","valid archive")
    require(inspect(make("relative\\sample.txt"))[0]["normalized_name"]=="relative/sample.txt","relative Windows path")
    for x in (b"bad",make("../escape.txt"),make("/absolute.txt"),make("..\\escape.txt"),make("C:\\absolute.txt"),make("\\\\server\\share.txt")):
        try:inspect(x)
        except ValueError:pass
        else:raise AssertionError("unsafe archive admitted")
    require(inspect(make("/README"),allow_official_root=True)[0]["normalized_name"]=="README","official root file")
    for x in (make("/etc/passwd"),make("//server/share.txt"),make("/..")):
        try:inspect(x,allow_official_root=True)
        except ValueError:pass
        else:raise AssertionError("unsafe official namespace")
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w") as z:z.writestr("/README","first");z.writestr("README","second")
    try:inspect(b.getvalue(),allow_official_root=True)
    except ValueError:pass
    else:raise AssertionError("normalized collision")
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:inspect(make("/README"),allow_official_root=True,normalized_zip=z)
    require(inspect(buf.getvalue())[0]["name"]=="README","safe rebuilt archive")
    print("CENSUS_BULK_TESTS_PASS=14")
def main(key):
    tests();require(key in SPECS,"program")
    now=datetime.now(timezone.utc)
    require(now.date().isoformat()=="2026-11-26","date window")
    url="https://www.census.gov/econ_getzippedfile/?programCode="+key
    with patch.object(transport,"ALLOWED",{"www.census.gov"}):raw=transport.fetch_public(url)
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as safe:meta=inspect(raw,allow_official_root=True,normalized_zip=safe)
    normalized=buf.getvalue()
    require({x["normalized_name"]:x["sha256"] for x in meta}=={x["name"]:x["sha256"] for x in inspect(normalized)},"rebuilt member identity")
    Path("census-original-source.bin").write_bytes(raw)
    Path("census-public-source.zip").write_bytes(normalized)
    d={"program":key,"title":SPECS[key],"source_url":url,"attribution":"U.S. Census Bureau, "+SPECS[key]+", accessed "+str(now.date()),"retrieved_at":now.isoformat(),"archive_sha256":sha(raw),"archive_bytes":len(raw),"normalized_archive_sha256":sha(normalized),"members":meta,"scope":"public official bulk source metadata only; no selected series, event definitions, forecasts or outcomes","status":"PUBLIC_BULK_TRANSPORT_PASS","inference_calls":0,"actual_outcomes_accessed":0,"confirmatory_eligible":False}
    Path("census-source-receipt.json").write_text(json.dumps(d,sort_keys=True))
    print("CENSUS_BULK_RESULT="+json.dumps(d,sort_keys=True))
if __name__=="__main__":main(sys.argv[1])
