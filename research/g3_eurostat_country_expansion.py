"""Expand an already qualified Eurostat adapter to a fixed set of countries.
18 distinct series, not 18 independent events. Historical data only.
One request per series, no retries, no live forecasts, no paid calls.
"""
import copy,json,sys
from pathlib import Path
from unittest.mock import patch
import g3_eurostat_source_probe as eu
COUNTRIES=("DE","ES","IT","NL","PL","SE")
KEYS=("unemployment","retail","hicp")

def main(country):
    if country not in COUNTRIES:raise ValueError("unregistered country")
    specs=copy.deepcopy(eu.SPECS)
    for key in KEYS:
        spec=specs[key]
        spec["filters"]["geo"]=country
        spec["family"]=country+spec["family"][2:]
    reports={};blocked={}
    with patch.object(eu,"SPECS",specs):
        for key in KEYS:
            # Do not let stale files from a previous series masquerade as evidence.
            for name in ("eurostat-source.json","eurostat-report.json"):
                Path(name).unlink(missing_ok=True)
            try:
                eu.main(key)
                report=json.loads(Path("eurostat-report.json").read_bytes())
                assert report["spec"]==specs[key] and report["inference_calls"]==0
                reports[key]=report
                Path("eurostat-source.json").rename(country+"-"+key+"-source.json")
            except Exception as exc:
                blocked[key]={"class":type(exc).__name__,"reason":str(exc)[:200]}
    result={"country":country,"reports":reports,"blocked":blocked,"inference_calls":0,"confirmatory_pairs":0,"scope":"distinct country-series candidate identities; macroeconomic and cross-country dependence not established"}
    Path("country-result.json").write_text(json.dumps(result,sort_keys=True))
    print("EUROSTAT_COUNTRY_RESULT="+json.dumps({"country":country,"qualified":{k:{"family":v["family"],"n":v["baseline"]["n"],"p":v["baseline"]["probability"],"source_sha256":v["source_sha256"]} for k,v in reports.items()},"blocked":blocked,"inference_calls":0},sort_keys=True))
if __name__=="__main__":main(sys.argv[1])
