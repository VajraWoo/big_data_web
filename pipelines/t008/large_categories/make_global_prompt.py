"""Generate one global consolidation prompt over the LOCAL themes, not raw clusters."""

from __future__ import annotations
import argparse, json
from pathlib import Path


def run(args):
    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    if not catalog:
        raise RuntimeError("empty local theme catalog")
    category = catalog[0]["product_category"]

    lines=[]
    for t in catalog:
        lines.append(
            f"- {t['local_theme_id']} | name={t['local_theme_name']} | "
            f"definition={t.get('definition','')} | member_clusters={len(t['member_cluster_ids'])}"
        )

    example={
      "product_category":category,
      "global_themes":[
        {
          "canonical_theme_name":"Noise level",
          "member_local_theme_ids":["block-001:0002","block-009:0004"],
          "definition":"Operating or fan noise produced by the product."
        }
      ]
    }

    prompt=f"""You are creating the FINAL category-level taxonomy from local candidate themes.

CATEGORY
{category}

TASK
Assign EVERY local_theme_id exactly once to a global canonical theme.

RULES
1. Merge equivalent local themes created in different blocks.
2. Do not merge merely-related analytical dimensions.
3. Polarity is not a taxonomy axis.
4. Keep speed, capacity, reliability, functionality, quality, size, fit, noise, vibration, etc. separate unless the local definitions clearly express the same dimension.
5. Prefer concise noun-phrase canonical names.
6. Do not discard any local theme.
7. Return JSON only.

OUTPUT CONTRACT
{json.dumps(example,ensure_ascii=False,indent=2)}

LOCAL THEMES
"""+"\n".join(lines)

    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(prompt,encoding="utf-8")
    print(json.dumps({"status":"ready","product_category":category,"local_theme_count":len(catalog),"output":str(out)},ensure_ascii=False))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--catalog",required=True)
    p.add_argument("--output",required=True)
    run(p.parse_args())
