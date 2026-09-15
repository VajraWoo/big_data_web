from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path

EXPECTED = {
    "beverage-refrigerators": ("Beverage Refrigerators", 143),
    "chest-freezers": ("Chest Freezers", 78),
    "cooktops": ("Cooktops", 21),
    "countertop-dishwashers": ("Countertop Dishwashers", 256),
    "dryers": ("Dryers", 56),
    "ice-makers": ("Ice Makers", 2342),
    "kegerators": ("Kegerators", 9),
    "portable-dryers": ("Portable Dryers", 102),
    "portable-washers": ("Portable Washers", 1260),
    "range-hoods": ("Range Hoods", 495),
    "refrigerators": ("Refrigerators", 55),
    "upright-freezers": ("Upright Freezers", 143),
    "washers": ("Washers", 32),
}
LARGE = {"ice-makers", "portable-washers", "range-hoods"}

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def read_ndjson(path: Path):
    rows=[]
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def taxonomy_id(category: str, name: str) -> str:
    return hashlib.sha256(f"{category}|{name.lower()}".encode()).hexdigest()[:24]

def main(args):
    packets = Path(args.packets)
    small = Path(args.small_decisions)
    large_final = Path(args.large_final)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    all_taxonomy=[]
    all_mapping=[]
    summary=[]
    errors=[]

    for slug, (category, expected_count) in EXPECTED.items():
        packet_path = packets / f"{slug}.json"
        if not packet_path.exists():
            errors.append(f"{category}: missing packet {packet_path}")
            continue
        packet = read_json(packet_path)
        packet_ids = [str(x["cluster_id"]) for x in packet.get("clusters", [])]
        packet_set = set(packet_ids)
        if len(packet_ids) != len(packet_set):
            errors.append(f"{category}: duplicate cluster_id in packet")
        if len(packet_set) != expected_count:
            errors.append(f"{category}: packet cluster count {len(packet_set)} != expected {expected_count}")

        if slug in LARGE:
            tpath = large_final / slug / "taxonomy.ndjson"
            mpath = large_final / slug / "cluster-to-taxonomy.ndjson"
            vpath = large_final / slug / "validation.json"
            if not tpath.exists() or not mpath.exists():
                errors.append(f"{category}: missing finalized large-category files under {large_final / slug}")
                continue
            if vpath.exists():
                v=read_json(vpath)
                if v.get("status") != "ready" or v.get("errors"):
                    errors.append(f"{category}: final validation is not ready: {v}")
            tax = read_ndjson(tpath)
            mapping = read_ndjson(mpath)
        else:
            dpath = small / f"{slug}.json"
            if not dpath.exists():
                errors.append(f"{category}: missing small/medium decision {dpath}")
                continue
            dec = read_json(dpath)
            if dec.get("product_category") != category:
                errors.append(f"{category}: decision category mismatch")
            themes = dec.get("themes") or []
            tax=[]
            mapping=[]
            seen=[]
            names=[]
            for i,t in enumerate(themes):
                name=str(t.get("canonical_theme_name") or "").strip()
                ids=t.get("member_cluster_ids") or []
                if not name:
                    errors.append(f"{category}: theme[{i}] empty canonical_theme_name")
                    continue
                if not ids:
                    errors.append(f"{category}: theme {name!r} has no member_cluster_ids")
                    continue
                names.append(name.lower())
                tid=taxonomy_id(category,name)
                tax.append({
                    "taxonomy_id":tid,
                    "product_category":category,
                    "canonical_theme_name":name,
                    "local_theme_count":None,
                    "first_level_cluster_count":len(ids),
                    "definition":t.get("rationale"),
                    "status":"human_review_required",
                })
                for cid in ids:
                    cid=str(cid)
                    seen.append(cid)
                    mapping.append({
                        "taxonomy_id":tid,
                        "product_category":category,
                        "canonical_theme_name":name,
                        "first_level_cluster_id":cid,
                    })
            if len(names) != len(set(names)):
                errors.append(f"{category}: duplicate canonical theme names (case-insensitive)")
            if len(seen) != len(set(seen)):
                errors.append(f"{category}: a first-level cluster is assigned more than once")
            if set(seen) != packet_set:
                errors.append(f"{category}: small/medium coverage mismatch expected={len(packet_set)} seen={len(set(seen))}")

        # Per-category final validation
        names=[str(x.get("canonical_theme_name","")).strip().lower() for x in tax]
        if len(names) != len(set(names)):
            errors.append(f"{category}: duplicate final canonical theme names (case-insensitive)")
        mapped=[str(x["first_level_cluster_id"]) for x in mapping]
        if len(mapped) != len(set(mapped)):
            errors.append(f"{category}: duplicate cluster assignments in final mapping")
        if set(mapped) != packet_set:
            errors.append(f"{category}: final coverage mismatch expected={len(packet_set)} seen={len(set(mapped))}")

        all_taxonomy.extend(tax)
        all_mapping.extend(mapping)
        summary.append({
            "product_category":category,
            "first_level_cluster_count":len(packet_set),
            "final_theme_count":len(tax),
            "mapping_count":len(mapping),
            "coverage_exact_once": set(mapped)==packet_set and len(mapped)==len(set(mapped)),
        })

    # Global checks
    if len(summary) != 13:
        errors.append(f"category count mismatch: completed={len(summary)} expected=13")
    total_expected=sum(v[1] for v in EXPECTED.values())
    total_mapped=len(all_mapping)
    mapped_keys=[(x["product_category"], x["first_level_cluster_id"]) for x in all_mapping]
    if total_mapped != total_expected:
        errors.append(f"total mapping count {total_mapped} != expected {total_expected}")
    if len(mapped_keys) != len(set(mapped_keys)):
        errors.append("duplicate (category, first_level_cluster_id) in merged mapping")

    validation={
        "status":"failed" if errors else "ready",
        "category_count":len(summary),
        "expected_category_count":13,
        "taxonomy_theme_count":len(all_taxonomy),
        "expected_first_level_cluster_count":total_expected,
        "mapped_first_level_cluster_count":total_mapped,
        "errors":errors,
    }

    (out/"validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding="utf-8")
    with (out/"taxonomy.ndjson").open("w",encoding="utf-8") as f:
        for r in all_taxonomy:
            f.write(json.dumps(r,ensure_ascii=False)+"\n")
    with (out/"cluster-to-taxonomy.ndjson").open("w",encoding="utf-8") as f:
        for r in all_mapping:
            f.write(json.dumps(r,ensure_ascii=False)+"\n")
    with (out/"category-summary.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["product_category","first_level_cluster_count","final_theme_count","mapping_count","coverage_exact_once"])
        w.writeheader()
        w.writerows(summary)

    print(json.dumps(validation,ensure_ascii=False))
    if errors:
        raise RuntimeError("T008 final consolidation failed")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--packets",required=True)
    p.add_argument("--small-decisions",required=True)
    p.add_argument("--large-final",required=True)
    p.add_argument("--output",required=True)
    main(p.parse_args())
