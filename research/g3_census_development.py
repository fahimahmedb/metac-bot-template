"""Offline development definitions; no future outcome retrieval or inference."""
import csv, hashlib, io, json, re, sys, zipfile
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

# Thresholds, series and proposed capture rules fixed before historical calculation.
SPECS={
 "M3ADV":("MDM","NO","MLN$","2027-02","2027-04-16","0.01","relative",15082395616,"f252499e280edb17236f3eb8e3d957d15c4d62a7b8a1b79ac7939c7d549f0ea7","42e22a5d0403f09047d19484e124ad2ce9e610a543c5cf7cdfad970cc00c802f","6475a10ccde89b9b727067423803bfbebfd2c7103b185329f390acf28ba87d50"),
 "BFS":("TOTAL","BA_BA","UNITS","2027-03","2027-05-15","0.01","relative",15081793061,"2e1f1c31365cdf6695e8fed6c164484487a3bdc85a3fd630e09a2a005e390785","6663325f78a10be32c2e4dc22f9951fe6de036cbc70d51faa561d8234cc596cb","4411e9e9a8fd9017453f022e9419c5ecd2e58d6fd89ef8df954b968c6e06a07b"),
 "FTD":("BOPGS","BAL","MLN$","2027-04","2027-06-18","1000","difference",15081359958,"93336b4321914419a52dac2818a02369464454520e2dd210381e4bb2bd2dfe24","12e41e795e821f137fe4076822d8966c368663153d03a14a6f72a0bdfde4b4a6","2128f4f9d7d11100bc797974102a53c13389bc5c444eef18b0cb1e739b908294")}
HEADERS={"CATEGORIES":["cat_idx","cat_code","cat_desc","cat_indent"],"DATA TYPES":["dt_idx","dt_code","dt_desc","dt_unit"],"GEO LEVELS":["geo_idx","geo_code","geo_desc"],"TIME PERIODS":["per_idx","per_name"],"DATA":["per_idx","cat_idx","dt_idx","geo_idx","is_adj","val"]}
HISTORY=[f"{y}-{m:02}" for y in (2024,2025) for m in range(1,13)]
MONTHS={m:i for i,m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(),1)}
def require(b,msg):
 if not b: raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def month(v):
 m=re.fullmatch(r"([A-Z][a-z]{2})-?(\d{4})",v)
 require(m and m[1] in MONTHS,"bad period")
 return f"{m[2]}-{MONTHS[m[1]]:02}"
def prev(m):
 y,n=map(int,m.split("-"));return f"{y-(n==1)}-{12 if n==1 else n-1:02}"
def parse(raw,key,periods):
 catcode,dtcode,unit,*_=SPECS[key]
 wanted=set(periods);require(len(wanted)==len(periods),"duplicate requested period")
 sections={};section=None
 for line in raw.decode("utf-8-sig").splitlines():
  if not line.strip():continue
  if line in {*HEADERS,"NOTES","DATA UPDATED ON","ERROR TYPES"}:
   section=line;require(section not in sections,"duplicate section");sections[section]=[];continue
  require(section is not None,"unrecognized preamble")
  # Published BFS prose has nonstandard quotation. Never use notes as data.
  if section in HEADERS:sections[section].append(next(csv.reader([line],strict=True)))
 for k,h in HEADERS.items():
  require(k in sections and sections[k] and sections[k][0]==h,"header "+k)
 def pick(k,code,unit=None):
  rows=sections[k][1:];require(all(len(r)==len(HEADERS[k]) for r in rows),"metadata row width")
  require(len({r[0] for r in rows})==len(rows) and len({r[1] for r in rows})==len(rows),"duplicate metadata identity")
  r=[v for v in rows if v[1]==code];require(len(r)==1,"missing "+k+" code")
  if unit is not None:require(r[0][3]==unit,"wrong unit")
  return r[0][0]
 cat=pick("CATEGORIES",catcode);dt=pick("DATA TYPES",dtcode,unit);geo=pick("GEO LEVELS","US")
 idx={};seen_months=set();seen_indices=set()
 for r in sections["TIME PERIODS"][1:]:
  require(len(r)==2,"period row");require(r[0] not in seen_indices,"duplicate period index");seen_indices.add(r[0])
  try:p=month(r[1])
  except ValueError:
   require(re.fullmatch(r"(?:\d{4}|\d{4}-?Q[1-4]|Q[1-4]-?\d{4})",r[1]),"unrecognized period label");continue
  require(p not in seen_months,"duplicate period month");idx[r[0]]=p;seen_months.add(p)
 values={};seen=set()
 for r in sections["DATA"][1:]:
  require(len(r)==6,"data row")
  if r[1:5]!=[cat,dt,geo,"1"] or idx.get(r[0]) not in wanted:continue
  p=idx[r[0]];require(p not in seen,"duplicate selected observation");seen.add(p)
  if r[5] in ("","NA","N","D","S","X","(S)","(D)"):continue
  v=Decimal(r[5]);require(v.is_finite(),"nonfinite value");require(key=="FTD" or v>0,"nonpositive relative series");values[p]=v
 return values
def event(key,a,b):
 a,b=Fraction(a),Fraction(b);threshold=Fraction(Decimal(SPECS[key][5]))
 if SPECS[key][6]=="relative":require(a>0,"nonpositive denominator");return (b-a)/a>=threshold
 return b-a>=threshold
def make(key,raw):
 cat,dt,unit,target,capture,threshold,mode,aid,original,safe,member=SPECS[key]
 require(sha(raw)==member,"member bytes mismatch");v=parse(raw,key,HISTORY);require(set(v)==set(HISTORY),"historical gap; no imputation")
 labels=[event(key,v[a],v[b]) for a,b in zip(HISTORY,HISTORY[1:])];n=len(labels);y=sum(labels)
 definition=dict(source="US Census Bureau",program=key,category=cat,data_type=dt,unit=unit,geography="US",seasonally_adjusted=True,mode=mode,threshold=threshold,target=target,comparison=prev(target),forecast_before=target+"-01T00:00:00Z",capture_date_utc=capture,capture_date_is_official_release=False,outcome_rule="same published vintage; exactly the two months; no backfill; missing or ambiguous unresolved",capture_provenance_verified=False,authorization="DEVELOPMENT_ONLY",inference_authorized=False,capture_authorized=False,confirmatory_eligible=False)
 return dict(definition=definition,definition_sha256=sha(canonical(definition)),reference=dict(n=n,yes=y,probability=(y+1)/(n+2),history_from=HISTORY[0],history_to=HISTORY[-1],revision_status="current historical snapshot; not point-in-time historical vintages",member_sha256=member,original_sha256=original,normalized_sha256=safe,source_run=45743246873,artifact_id=aid),real_forecasts=0,actual_outcomes_accessed=0,inference_calls=0)
def tests():
 raw=("CATEGORIES\ncat_idx,cat_code,cat_desc,cat_indent\n1,BOPGS,total,0\nDATA TYPES\ndt_idx,dt_code,dt_desc,dt_unit\n1,BAL,balance,MLN$\nGEO LEVELS\ngeo_idx,geo_code,geo_desc\n1,US,total\nTIME PERIODS\nper_idx,per_name\n1,Jan-2025\n2,Feb-2025\nNOTES\nnote\nDATA UPDATED ON\nfixture\nDATA\nper_idx,cat_idx,dt_idx,geo_idx,is_adj,val\n1,1,1,1,1,-9000\n2,1,1,1,1,-8000\n2,1,1,1,0,99999\n").encode()
 p=["2025-01","2025-02"]
 assert parse(raw,"FTD",p)=={"2025-01":Decimal(-9000),"2025-02":Decimal(-8000)}
 assert event("FTD",-9000,-8000) and not event("FTD",-9000,-8001)
 assert event("M3ADV",100,101) and not event("M3ADV",100,Decimal("100.9999"))
 assert event("BFS",100,101) and prev("2027-01")=="2026-12"
 assert parse(raw.replace(b"-8000",b"NA"),"FTD",p)=={"2025-01":Decimal(-9000)}
 assert parse(raw.replace(b"note",b'"bad "quote" text'),"FTD",p)==parse(raw,"FTD",p)
 for bad in [raw+b"2,1,1,1,1,-8001\n",raw.replace(b"MLN$",b"UNITS"),raw.replace(b"1,US,total",b"1,CA,total"),raw.replace(b"-8000",b"NaN"),raw.replace(b"Feb-2025",b"Jan-2025"),raw.replace(b"1,US,total",b"1,US,total\n1,CA,other")]:
  try:parse(bad,"FTD",p)
  except ValueError:pass
  else:raise AssertionError("accepted invalid fixture")
 print("CENSUS_DEVELOPMENT_TESTS_PASS=12")
def main(key,folder):
 tests();s=SPECS[key];root=Path(folder)
 original=(root/"census-original-source.bin").read_bytes();safe=(root/"census-public-source.zip").read_bytes()
 require(sha(original)==s[8] and sha(safe)==s[9],"archive identity")
 with zipfile.ZipFile(io.BytesIO(safe)) as z:
  require(set(z.namelist())=={key+"-mf.csv","README"} and len(z.namelist())==2,"member names")
  raw=z.read(key+"-mf.csv");require(sha(z.read("README"))=="1794c7a4c9eb919fda96bbc8d92143d3e1ce2d4e1e0ea08d346fe09f4b29bf3c","README identity")
 d=make(key,raw);Path("census-development-definition.json").write_bytes(canonical(d));print("CENSUS_DEVELOPMENT_RESULT="+json.dumps(d,sort_keys=True))
if __name__=="__main__":main(sys.argv[1],sys.argv[2])
