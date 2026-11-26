"""Reuse Eurostat development definitions on six already-collected country artifacts.
No source request, model calls, future outcomes or confirmatory admission.
Historical dependence is descriptive only (24 months, revised values).
"""
import copy,hashlib,itertools,json,math,statistics,sys
from pathlib import Path
from unittest.mock import patch
import g3_eurostat_source_probe as eu
import g3_eurostat_development as dev

SOURCE_RUN=45741970010
PINS=json.loads('''{"SE":{"artifact":15081731775,"digest":"sha256:23f9e32bfbdffe7174f98b9428aa97f362b65389a551efc6bf627aefc89f94dc","hashes":{"hicp":"6a78030238d4b712d49e397c89060f126b887657b440fd698d4d4ce2b2aade27","retail":"514f20fc3761f5a58a6cd78452c7cc9293fff3760986ef6090e53fffae57ee8a","unemployment":"7b8999235eba43cd5f3bcb3e538e605fdb4aa9ab965d0dc3ac6c582f1a2fae58"}},"IT":{"artifact":15081192623,"digest":"sha256:2424ef4842333fc23834fb4f50a5eb5fa37fc47e81c0a719421db443e7057dfa","hashes":{"hicp":"de7f64dbebbe2fee5a465b83ff94e2134f6cbb43d0022db62f0ab8161257fdb7","retail":"e5ff193befb7d5798a99b0a4221def835e6fe7a0b32343b616b714f3d3942b09","unemployment":"ebff1e495a778a3986844f30422372658cb413dec72cddfdf41b961dd1f63cd7"}},"ES":{"artifact":15081866561,"digest":"sha256:4c926f502d1f2bc8dee615b832b56e19d171f14576070e617947a03158aa590e","hashes":{"hicp":"42f5b3c91500ec71e51a96b7c2c3380eb1ae2e28952497d3adbf5ab885eef9d2","retail":"9166e194b67fa5500c8dc0604f92d36a967b3e4424d9ec8a31622fe220bcc018","unemployment":"ddc0d722a5aeea8543a75bd8465616a9d0d440f71c526651341084f472e8b373"}},"NL":{"artifact":15081477280,"digest":"sha256:49d271ba1bf438acd277ea30fdd2689df5fffcb51a706e7e6db1cb033537695b","hashes":{"hicp":"457dba5e7e89e3db5bd12c17757de7e97fe22b6a1011feead8fc0afdfc4a81c6","retail":"ffb40297bbf107df3bcbf37254afb18f7c564a8715bd5c14be233c8d927ed260","unemployment":"556307ebadee95a438fff708a88098345539bfa980d6d803e2cbc2482e706216"}},"DE":{"artifact":15081203290,"digest":"sha256:87cba3140fefa476719453e56bb948ca1b889b921294018e9711cc7fcaee5654","hashes":{"hicp":"3c84581f77b320505b6d53ac9fd710820ada51076ed0bf8732f144f5feb3114a","retail":"2bbdf88466ecd0f9541e8ea2142c61db0e63f0ea7834976d15ffd0abab4db99c","unemployment":"16b407b9a1f7e56c62cb99387d390e11e2d0e43f3383c5e2acd57e5302ae3d82"}},"PL":{"artifact":15082120605,"digest":"sha256:8f0250bde5c26730157e8685131a76c84f169e0ba920b0ed0c1d02860a2b4d0b","hashes":{"hicp":"866298443727935b3dc4c76b08f2f4b02cbc1673c0c33da7c4f9e6e91e5ca7f1","retail":"443062a0d8f312736a835adb34831d6389d557b34d357c904cbeb4954476a7a2","unemployment":"42ed5e44e07968ba1d8a91f4935a729e0323889b0bcd7484486fc86a72af4818"}}}''')
KEYS=("hicp","retail","unemployment")

def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def specs(country):
    s=copy.deepcopy(eu.SPECS)
    for key in KEYS:
        s[key]["filters"]["geo"]=country
        s[key]["family"]=country+s[key]["family"][2:]
    return s
def indexed_labels(key,rows):
    if key=="hicp":return dict(zip((r["month"] for r in rows),eu.labels(key,rows),strict=True))
    return {b["month"]:eu.labels(key,[a,b])[0] for a,b in zip(rows,rows[1:]) if eu.month(b["month"])==eu.month(a["month"])+1}
def prepare(country,folder):
    pin=PINS[country];s=specs(country)
    doc=json.loads((folder/"country-result.json").read_bytes())
    require(doc["country"]==country and not doc["blocked"] and set(doc["reports"])==set(KEYS) and doc["inference_calls"]==doc["confirmatory_pairs"]==0,"country receipt")
    results={}
    for key in KEYS:
        raw=(folder/f"{country}-{key}-source.json").read_bytes()
        report=doc["reports"][key]
        require(sha(raw)==pin["hashes"][key]==report["source_sha256"],"raw source mismatch")
        require(report["family"]==s[key]["family"] and report["spec"]==s[key] and report["outcomes_accessed"]==report["inference_calls"]==0,"report identity")
        report_bytes=json.dumps(report,sort_keys=True).encode()
        p={key:(SOURCE_RUN,pin["artifact"],sha(raw),sha(report_bytes))}
        with patch.object(eu,"SPECS",s),patch.object(dev,"SPECS",s),patch.object(dev,"PINS",p):
            result=dev.prepare(key,raw,report_bytes)
            labs=indexed_labels(key,report["rows"])
            require(len(labs)==result["baseline"]["n"] and sum(labs.values())==result["baseline"]["yes"],"label mismatch")
            # The already-tested resolver is reused. Country-specific negative test:
            # the source for a different geography must be rejected.
            wrong=copy.deepcopy(json.loads(raw));axis=wrong["dimension"]["geo"]["category"]
            axis["index"]={"FR":0}
            try:eu.parse(key,json.dumps(wrong).encode())
            except ValueError:pass
            else:raise AssertionError("wrong country admitted")
        results[key]=result|{"historical_labels":labs,"source_artifact_digest":pin["digest"],"dependency_groups":["EU_MACRO",country,key]}
    return {"country":country,"results":results,"inference_calls":0,"outcomes_accessed":0}
def corr(a,b):
    ts=sorted(set(a)&set(b));x=[a[t] for t in ts];y=[b[t] for t in ts]
    if len(ts)<12 or len(set(x))<2 or len(set(y))<2:return None
    mx,my=statistics.mean(x),statistics.mean(y)
    dx=[v-mx for v in x];dy=[v-my for v in y]
    return {"n":len(ts),"r":sum(i*j for i,j in zip(dx,dy,strict=True))/math.sqrt(sum(i*i for i in dx)*sum(j*j for j in dy))}
def consolidate(root):
    definitions={};blocked=[]
    for country in sorted(PINS):
        try:
            d=json.loads((root/("country-definition-"+country)/"country-definition.json").read_bytes())
            require(d["country"]==country and d["inference_calls"]==d["outcomes_accessed"]==0 and set(d["results"])==set(KEYS),"definition receipt")
            for key,r in d["results"].items():
                e=r["definition"];family=e["family"]
                require(family==specs(country)[key]["family"] and e["source_sha256"]==PINS[country]["hashes"][key] and r["definition_sha256"]==sha(dev.canonical(e)) and not e["confirmatory_eligible"] and not e["inference_authorized"] and not e["capture_authorized"],"definition identity")
                require(family not in definitions,"duplicate family")
                definitions[family]=r
        except (OSError,ValueError,KeyError,TypeError) as ex:blocked.append({"country":country,"reason":str(ex)[:200]})
    pairs=[]
    for a,b in itertools.combinations(sorted(definitions),2):
        x,y=definitions[a],definitions[b]
        r=corr(x["historical_labels"],y["historical_labels"])
        if r is not None:pairs.append({"a":a,"b":b,"same_indicator":x["definition"]["candidate"]==y["definition"]["candidate"],**r})
    groups={}
    for key in ("all","same_indicator","different_indicator"):
        ps=[p for p in pairs if key=="all" or p["same_indicator"]==(key=="same_indicator")]
        groups[key]={"pairs":len(ps),"mean_abs_r":statistics.mean(abs(p["r"]) for p in ps) if ps else None,"abs_r_ge_half":sum(abs(p["r"])>=.5 for p in ps)}
    out={"definitions":definitions,"blocked":blocked,"pairwise_correlations":pairs,"summary":groups,"highest_absolute":sorted(pairs,key=lambda p:abs(p["r"]),reverse=True)[:5],"scope":"descriptive historical label dependence, not independent prospective events or correlation of forecast errors","confirmatory_pairs":0,"inference_calls":0,"outcomes_accessed":0}
    return out
if __name__=="__main__":
    if sys.argv[1]=="consolidate":
        result=consolidate(Path(sys.argv[2]))
        Path("country-definitions-final.json").write_text(json.dumps(result,sort_keys=True))
        print("COUNTRY_DEFINITIONS_FINAL="+json.dumps({k:v for k,v in result.items() if k not in ("definitions","pairwise_correlations")}|{"count":len(result["definitions"])},sort_keys=True))
        if result["blocked"]:raise SystemExit(1)
    else:
        c=sys.argv[1];result=prepare(c,Path(sys.argv[2]))
        Path("country-definition.json").write_text(json.dumps(result,sort_keys=True))
        print("COUNTRY_DEFINITION_PASS="+json.dumps({"country":c,"definitions":[r["definition_sha256"] for r in result["results"].values()],"count":3,"inference_calls":0},sort_keys=True))
