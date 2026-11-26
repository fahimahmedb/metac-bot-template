"""Planning extension of the existing pinned readiness result.
No new registry, forecast, admission, actual outcome or schedule.
Common earliest possible issue day; one issue week per distinct event.
Theoretical capacity only, not verified feasible prospective dates.
"""
import json,hashlib,math,sys
from collections import Counter
from datetime import date,datetime,timedelta
from fractions import Fraction as F
from pathlib import Path
EARLY_SHA="76a0a3d7adf2c14eb458a5f5bea99831ef9bd4b8cf3128b57d295ec6cfbb9a06"
CENSUS_SHA="50efbf91ec28aa01f8bd4425e8564bf8ff710a0672896eaba4b7d832dbe775bd"
START=date(2026,11,26)
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(d):return json.dumps(d,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def weeks(deadline,start=START):
 t=datetime.fromisoformat(deadline.replace("Z","+00:00"))
 require(t.tzinfo is not None and t.utcoffset().total_seconds()==0,"UTC")
 end=(t-timedelta(microseconds=1)).date()
 require(end>=start,"already closed")
 return sorted({(d.isocalendar().year,d.isocalendar().week) for i in range((end-start).days+1) for d in [start+timedelta(days=i)]})
def maximum_distinct(deadlines,start=START):
 # All eligibility intervals are nested since they share the same start.
 # Earliest-deadline event takes earliest unused week; exchange argument
 # proves maximum matching cardinality for these prefix intervals.
 used=set();assign=[]
 for ident,d in sorted(deadlines.items(),key=lambda v:(v[1],v[0])):
  available=[w for w in weeks(d,start) if w not in used]
  if available:
   used.add(available[0]);assign.append((ident,available[0]))
 return assign
def robust_weeks(counts,missing):
 require(type(missing) is int and 0<=missing<=sum(counts) and all(type(n) is int and n>0 for n in counts),"invalid week counts")
 n=len(counts)
 for x in sorted(counts):
  if missing<x:break
  missing-=x;n-=1
 return n
def analyze(early,census):
 require(early["existing_development_definitions"]==27 and early["confirmatory_pairs"]==0 and early["development_labels_reusable_as_confirmation"] is False and early["same_deadline_counts"]=={"2027-01-01T00:00:00Z":27},"early scope")
 require(census["blocked"]==[] and census["actual_outcomes_accessed"]==census["inference_calls"]==census["confirmatory_pairs"]==0 and set(census["definitions"])=={"BFS","FTD","M3ADV"},"Census scope")
 deadlines={f"early-{i}":"2027-01-01T00:00:00Z" for i in range(27)}
 for k,r in census["definitions"].items():
  d=r["definition"]
  require(sha(canonical(d))==r["definition_sha256"] and d["program"]==k and d["authorization"]=="DEVELOPMENT_ONLY" and not any(d[x] for x in ("capture_authorized","confirmatory_eligible","inference_authorized")),"definition scope")
  deadlines[k]=d["forecast_before"]
 union=set().union(*(set(weeks(d)) for d in deadlines.values()))
 matching=maximum_distinct(deadlines)
 minimum=early["minimum_confirmatory_pairs"];min_weeks=early["minimum_issue_weeks"]
 n=next(x for x in range(minimum,minimum+100) if math.ceil(F(95,100)*x)>=minimum)
 miss=n-math.ceil(F(95,100)*n)
 layouts={"balanced_10_weeks":[11]*5+[10]*5,"balanced_15_weeks":[7]*15,"concentrated_10_weeks":[1]*6+[24,25,25,25]}
 require(all(sum(v)==n for v in layouts.values()),"planning example")
 return {"status":"BLOCK_CONFIRMATORY_DESIGN","development_definitions":len(deadlines),"registered_confirmatory_events":0,"confirmatory_pairs":0,"deadline_counts":dict(Counter(deadlines.values())),"available_week_union":len(union),"maximum_distinct_issue_weeks":len(matching),"minimum_issue_weeks":min_weeks,"minimum_paired_events":minimum,"hypothetical_count_gap":minimum-len(deadlines),"minimum_new_confirmatory_registrations_if_5pct_missing":n,"missing_budget":miss,"hypothetical_layouts":{k:{"registered_per_week":v,"worst_case_remaining_weeks":robust_weeks(v,miss)} for k,v in layouts.items()},"development_events_eligible":False,"dispatch_planning_not_authority":{"base":3*n,"cap":4*n},"actual_outcomes_accessed":0,"inference_calls":0,"promotion_authorized":False}
def tests(early,census):
 r=analyze(early,census)
 require(r["available_week_union"]==19 and r["maximum_distinct_issue_weeks"]==9,"union versus feasible distinct issue weeks")
 require(r["minimum_new_confirmatory_registrations_if_5pct_missing"]==105 and r["missing_budget"]==5,"coverage")
 require(r["hypothetical_layouts"]["balanced_10_weeks"]["worst_case_remaining_weeks"]==10 and r["hypothetical_layouts"]["balanced_15_weeks"]["worst_case_remaining_weeks"]==15 and r["hypothetical_layouts"]["concentrated_10_weeks"]["worst_case_remaining_weeks"]==5,"missing weeks")
 # Brute-force matching checks on small prefix families.
 import itertools
 for capacities in itertools.product(range(1,4),repeat=4):
  best=0
  for slots in itertools.product(range(4),repeat=4):
   assigned=[s for s in slots if s]
   if len(set(assigned))==len(assigned) and all(s<=c for s,c in zip(slots,capacities,strict=True)):best=max(best,len(assigned))
  ds={str(i):str(date(2026,11,30)+timedelta(days=7*(c-1)))+"T00:00:00Z" for i,c in enumerate(capacities)}
  require(len(maximum_distinct(ds))==best,"greedy matching proof")
 print("G3_HORIZON_TESTS_PASS small_exhaustive_cases=81")
 return r
if __name__=="__main__":
 a=Path(sys.argv[1]).read_bytes();b=Path(sys.argv[2]).read_bytes()
 require(sha(a)==EARLY_SHA and sha(b)==CENSUS_SHA,"exact source receipts")
 r=tests(json.loads(a),json.loads(b))
 Path("g3-portfolio-horizon.json").write_bytes(canonical(r))
 print("G3_PORTFOLIO_HORIZON="+json.dumps(r,sort_keys=True))
