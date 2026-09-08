"""Validate global decisions and materialize final first-level-cluster -> taxonomy mapping."""

from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path


def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))


def run(args):
    catalog=read(args.catalog)
    decision=read(args.decision)
    out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    if not catalog: raise RuntimeError("empty catalog")
    category=catalog[0]["product_category"]
    if decision.get("product_category") != category:
        raise RuntimeError("category mismatch")

    local={x["local_theme_id"]:x for x in catalog}
    expected=set(local)
    seen=set(); errors=[]

    global_themes=decision.get("global_themes") or []
    for i,g in enumerate(global_themes):
        name=str(g.get("canonical_theme_name") or "").strip()
        ids=g.get("member_local_theme_ids")
        if not name: errors.append(f"global_theme[{i}] empty name")
        if not isinstance(ids,list) or not ids:
            errors.append(f"global_theme[{i}] empty member list"); continue
        for lid in ids:
            if lid not in expected: errors.append(f"invented local_theme_id {lid}")
            if lid in seen: errors.append(f"duplicate local_theme_id {lid}")
            seen.add(lid)
    missing=expected-seen
    if missing: errors.append(f"missing local_theme_ids: {len(missing)}")

    cluster_seen=set()
    taxonomy_rows=[]
    mapping_rows=[]
    for g in global_themes:
        name=str(g["canonical_theme_name"]).strip()
        lid_list=g["member_local_theme_ids"]
        cluster_ids=[]
        for lid in lid_list:
            cluster_ids.extend(local[lid]["member_cluster_ids"])
        if len(cluster_ids) != len(set(cluster_ids)):
            errors.append(f"global theme {name!r} contains duplicate first-level cluster ids")
        for cid in cluster_ids:
            if cid in cluster_seen:
                errors.append(f"first-level cluster assigned to multiple global themes: {cid}")
            cluster_seen.add(cid)
        tid=hashlib.sha256(f"{category}|{name.lower()}".encode()).hexdigest()[:24]
        taxonomy_rows.append({
            "taxonomy_id":tid,
            "product_category":category,
            "canonical_theme_name":name,
            "local_theme_count":len(lid_list),
            "first_level_cluster_count":len(cluster_ids),
            "definition":g.get("definition"),
            "status":"human_review_required",
        })
        mapping_rows += [{
            "taxonomy_id":tid,
            "product_category":category,
            "canonical_theme_name":name,
            "first_level_cluster_id":cid,
        } for cid in cluster_ids]

    expected_clusters={cid for x in catalog for cid in x["member_cluster_ids"]}
    if cluster_seen != expected_clusters:
        errors.append(f"final cluster coverage mismatch expected={len(expected_clusters)} seen={len(cluster_seen)}")

    validation={
        "status":"failed" if errors else "ready",
        "product_category":category,
        "local_theme_count":len(expected),
        "global_theme_count":len(global_themes),
        "expected_first_level_cluster_count":len(expected_clusters),
        "mapped_first_level_cluster_count":len(cluster_seen),
        "errors":errors,
    }
    (out/"validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding="utf-8")
    if errors:
        print(json.dumps(validation,ensure_ascii=False)); raise RuntimeError("final validation failed")

    with (out/"taxonomy.ndjson").open("w",encoding="utf-8") as f:
        for r in taxonomy_rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")
    with (out/"cluster-to-taxonomy.ndjson").open("w",encoding="utf-8") as f:
        for r in mapping_rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")
    print(json.dumps(validation,ensure_ascii=False))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--catalog",required=True)
    p.add_argument("--decision",required=True)
    p.add_argument("--output",required=True)
    run(p.parse_args())
