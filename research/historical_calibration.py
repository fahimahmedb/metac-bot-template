"""Offline, temporal calibration experiment on archived ForecastBench forecasts.

This module is deliberately NOT imported by the live Metaculus bot. It uses
predictions made by other models at their historical forecast dates, not their
retrospective reconstructions, and does not train LLM weights.

Source: Forecasting Research Institute, ForecastBench datasets, CC BY-SA 4.0.
https://www.forecastbench.org/datasets/
https://github.com/forecastingresearch/forecastbench-datasets
Karger et al., ICLR 2025, https://arxiv.org/abs/2409.19839

The archive is mutable: record its exact SHA-256. Resolution dates are a proxy
for when labels became known; use a 30-day embargo, not a claim of proof of
the original publication timestamp. Do not transfer fitted coefficients to
a different model or to live FutureEval without prospective qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import tarfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

TRAIN_END = date(2025, 10, 1)
VALIDATION_END = date(2026, 2, 1)
TEST_END = date(2026, 7, 1)
LABEL_FREEZE = date(2026, 10, 1)
EMBARGO = timedelta(days=30)
MARKET_SOURCES = {"metaculus", "manifold", "polymarket"}
MIN_TRAIN, MIN_VAL, MIN_TEST = 100, 40, 40
MAX_MODELS = 8
MIN_VAL_GAIN = 0.002


@dataclass(frozen=True)
class Row:
    event: str
    issued: date
    resolved: date
    p: float
    y: int


def clip(p: float) -> float:
    return min(0.999, max(0.001, p))


def transform(p: float, a: float, b: float) -> float:
    z = a + b * math.log(clip(p) / (1.0 - clip(p)))
    return 1.0 / (1.0 + math.exp(-z))


def score(rows: list[Row], probabilities: list[float]) -> dict:
    if len(rows) != len(probabilities) or not rows:
        raise ValueError("Scores require aligned, nonempty observations")
    n = len(rows)
    return {
        "n": n,
        "brier": sum((p-r.y)**2 for p, r in zip(probabilities, rows)) / n,
        "log_loss": -sum(r.y * math.log(clip(p)) +
                         (1-r.y)*math.log(1-clip(p))
                         for p, r in zip(probabilities, rows))/n,
        "accuracy_at_half": sum((p >= .5) == bool(r.y)
                                for p, r in zip(probabilities, rows))/n,
    }


def split(rows: list[Row]) -> tuple[list[Row], list[Row], list[Row]]:
    # One earliest archived forecast per (source, event ID) for each model.
    # Avoid placing the same event in both training and test.
    unique = {}
    for r in sorted(rows, key=lambda r: (r.issued, r.event, r.resolved, r.p)):
        unique.setdefault(r.event, r)
    train, val, test = [], [], []
    for r in unique.values():
        if r.issued >= r.resolved:
            continue
        if r.issued < TRAIN_END and r.resolved < TRAIN_END - EMBARGO:
            train.append(r)
        elif TRAIN_END <= r.issued < VALIDATION_END and r.resolved < VALIDATION_END - EMBARGO:
            val.append(r)
        elif VALIDATION_END <= r.issued < TEST_END and r.resolved < LABEL_FREEZE:
            test.append(r)
    assert not ({r.event for r in train} & {r.event for r in val+test})
    assert not ({r.event for r in val} & {r.event for r in test})
    assert all(r.resolved < TRAIN_END-EMBARGO for r in train)
    assert all(r.resolved < VALIDATION_END-EMBARGO for r in val)
    return train, val, test


def fit_and_select(train: list[Row], val: list[Row]) -> dict:
    """Only train/validation labels enter parameter fitting and model choice."""
    if not train or not val:
        raise ValueError("Missing training or validation data")
    # A bounded Platt-scaling grid avoids depending on an external optimizer.
    # Fit two candidates to training, with a small penalty toward identity.
    options = []
    for family, offsets in (("temperature", [0.0]),
                            ("affine_logit", [i/10 for i in range(-8, 9)])):
        best = None
        for a in offsets:
            for i in range(5, 19):
                b = i/10
                fitted = [transform(r.p, a, b) for r in train]
                loss = score(train, fitted)["brier"] + .001*(a*a+(b-1)**2)
                candidate = (loss, abs(a)+abs(b-1), a, b)
                if best is None or candidate < best:
                    best = candidate
        _, _, a, b = best
        val_brier = score(val, [transform(r.p,a,b) for r in val])["brier"]
        options.append({"method": family, "a": a, "b": b, "validation_brier": val_brier})
    raw = score(val, [r.p for r in val])["brier"]
    best = min(options, key=lambda x: (x["validation_brier"],x["method"]))
    if best["validation_brier"] > raw - MIN_VAL_GAIN:
        best = {"method":"identity","a":0.0,"b":1.0,"validation_brier":raw}
    return {"chosen": best, "raw_validation_brier": raw, "candidates": options}


def predict(p_values: list[float], params: dict) -> list[float]:
    """Inference has no access to outcomes, dates, or event IDs."""
    if params["method"] == "identity":
        return p_values[:]
    return [transform(p, params["a"], params["b"]) for p in p_values]


def paired_bootstrap(rows: list[Row], forecast: list[float]) -> dict:
    # Resample whole forecast rounds, not independent rows from the same round.
    grouped = defaultdict(list)
    for r,q in zip(rows,forecast):
        grouped[r.issued].append((r.p-r.y)**2-(q-r.y)**2)
    groups = list(grouped.values())
    if len(groups) < 5:
        return {"rounds":len(groups),"ci95":None}
    rng = random.Random(20261124)
    estimates = []
    for _ in range(1000):
        sampled = [x for _ in groups for x in rng.choice(groups)]
        estimates.append(sum(sampled)/len(sampled))
    estimates.sort()
    return {"rounds":len(groups),"ci95":[estimates[24],estimates[974]]}


def sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            digest.update(part)
    return digest.hexdigest()


def read_archive(path: Path) -> tuple[dict,dict]:
    models = defaultdict(list)
    counters=defaultdict(int)
    with tarfile.open(path, "r|gz") as archive:
        for member in archive:
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            counters["json_files"]+=1
            # Only historical submission files. No filesystem extraction.
            filename=Path(member.name).name
            try:
                issued=date.fromisoformat(filename[:10])
            except ValueError:
                continue
            if not date(2024,7,1)<=issued<TEST_END or member.size>30_000_000:
                continue
            payload=archive.extractfile(member)
            if payload is None:
                continue
            obj=json.load(payload)
            if not isinstance(obj,dict):
                continue
            org=obj.get("organization")
            model_org=obj.get("model_organization")
            model=obj.get("model")
            qs=obj.get("question_set")
            # Exclude crowd, human and dummy benchmark forecasters. Only
            # ForecastBench's archived LLM submissions; no live market feed.
            if org!="ForecastBench" or not model_org or model_org=="ForecastBench" or not model:
                continue
            if qs!=f"{issued.isoformat()}-llm.json":
                continue
            for item in obj.get("forecasts",[]):
                counters["rows_seen"]+=1
                source=item.get("source")
                ident=item.get("id")
                if source not in MARKET_SOURCES or not isinstance(ident,str):
                    continue
                if item.get("imputed") is not False or item.get("resolved") is not True:
                    continue
                try:
                    p=float(item["forecast"])
                    y=float(item["resolved_to"])
                    resolved=date.fromisoformat(str(item["resolution_date"])[:10])
                except (KeyError,ValueError,TypeError):
                    counters["invalid_rows"]+=1
                    continue
                if not (0<=p<=1 and y in (0,1) and issued<resolved<LABEL_FREEZE):
                    continue
                variant=str(item.get("forecast_variant_key") or "unspecified")
                key=f"{model_org}/{model}/{variant}"
                models[key].append(Row(f"{source}:{ident}",issued,resolved,p,int(y)))
                counters["eligible_rows"]+=1
    return models,dict(counters)


def evaluate(path: Path) -> dict:
    models,counts=read_archive(path)
    cohorts={k:split(v) for k,v in models.items()}
    # Cohort selection is based only on train/validation coverage, never
    # on test scores or test performance. Report ALL selected cohorts.
    selected=sorted((k for k,(t,v,s) in cohorts.items()
                     if len(t)>=MIN_TRAIN and len(v)>=MIN_VAL),
                    key=lambda k:(-len(cohorts[k][0]),k))[:MAX_MODELS]
    report={"archive_sha256":sha256(path),"archive_bytes":path.stat().st_size,
            "counts":counts,"cohorts_seen":len(cohorts),
            "split_policy":{"train_forecasts_before":str(TRAIN_END),
                            "validation_forecasts_before":str(VALIDATION_END),
                            "test_forecasts_before":str(TEST_END),
                            "label_freeze":str(LABEL_FREEZE),"embargo_days":30,
                            "train_min":MIN_TRAIN,"val_min":MIN_VAL,"test_min":MIN_TEST},
            "results":[]}
    for k in selected:
        train,val,test=cohorts[k]
        fitted=fit_and_select(train,val)
        # Freeze chosen coefficients and produce predictions BEFORE scoring.
        params=fitted["chosen"]
        masked_input=[r.p for r in test]
        prediction=predict(masked_input,params)
        out={"model":k,"train_n":len(train),"validation_n":len(val),
             "test_n":len(test),"fitted":fitted}
        if len(test)>=MIN_TEST:
            raw=score(test,masked_input)
            calibrated=score(test,prediction)
            out.update({"status":"SCORED","raw":raw,"calibrated":calibrated,
                        "brier_gain":raw["brier"]-calibrated["brier"],
                        "paired_round_bootstrap":paired_bootstrap(test,prediction)})
        else:
            out["status"]="INSUFFICIENT_TEST_COVERAGE"
        report["results"].append(out)
    report["status"]="SCORED" if any(x["status"]=="SCORED" for x in report["results"]) else "BLOCK_INSUFFICIENT_DATA"
    return report


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("archive",type=Path)
    ap.add_argument("--output",type=Path,default=Path("historical_calibration_report.json"))
    args=ap.parse_args()
    report=evaluate(args.archive)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    if report["status"]!="SCORED":
        raise SystemExit("No qualifying archived LLM cohort: do not claim an evaluation")
