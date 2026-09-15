"""Validate local block decisions and combine them into one local-theme catalog."""

from __future__ import annotations
import argparse, json
from pathlib import Path


def read_json(path): return json.loads(Path(path).read_text(encoding="utf-8"))


def run(args):
    block_dir = Path(args.block_dir)
    decision_dir = Path(args.decision_dir)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    catalog = []
    errors = []
    all_expected = set()
    all_seen = set()

    for bp in sorted(block_dir.glob("block-*.json")):
        block = read_json(bp)
        expected = {r["cluster_id"] for r in block["clusters"]}
        all_expected |= expected

        dp = decision_dir / f"{block['block_id']}.json"
        if not dp.exists():
            errors.append(f"missing decision file: {dp.name}")
            continue
        d = read_json(dp)
        if d.get("product_category") != block["product_category"]:
            errors.append(f"{block['block_id']}: category mismatch")
        if d.get("block_id") != block["block_id"]:
            errors.append(f"{block['block_id']}: block_id mismatch")

        seen = set()
        for i,t in enumerate(d.get("local_themes") or []):
            name = str(t.get("local_theme_name") or "").strip()
            ids = t.get("member_cluster_ids")
            definition = str(t.get("definition") or "").strip()
            if not name:
                errors.append(f"{block['block_id']} theme[{i}]: empty name")
            if not isinstance(ids,list) or not ids:
                errors.append(f"{block['block_id']} theme[{i}]: empty member list")
                continue
            for cid in ids:
                if cid not in expected:
                    errors.append(f"{block['block_id']}: invented cluster_id {cid}")
                if cid in seen:
                    errors.append(f"{block['block_id']}: duplicate cluster_id {cid}")
                seen.add(cid)
                all_seen.add(cid)
            catalog.append({
                "product_category": block["product_category"],
                "block_id": block["block_id"],
                "local_theme_id": f"{block['block_id']}:{i:04d}",
                "local_theme_name": name,
                "definition": definition,
                "member_cluster_ids": ids,
            })
        missing = expected - seen
        if missing:
            errors.append(f"{block['block_id']}: missing {len(missing)} cluster_ids")

    if all_expected != all_seen:
        errors.append(f"global local-stage coverage mismatch expected={len(all_expected)} seen={len(all_seen)}")

    validation = {
        "status":"failed" if errors else "ready",
        "expected_cluster_count":len(all_expected),
        "seen_cluster_count":len(all_seen),
        "local_theme_count":len(catalog),
        "errors":errors,
    }
    (out/"validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"local-theme-catalog.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(validation,ensure_ascii=False))
    if errors:
        raise RuntimeError("local decision validation failed")


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--block-dir",required=True)
    p.add_argument("--decision-dir",required=True)
    p.add_argument("--output",required=True)
    run(p.parse_args())
