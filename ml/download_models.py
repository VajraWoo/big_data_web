"""Fetch only explicitly allowlisted files from pinned model commits."""
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download


if __name__ == "__main__":
    specs = json.loads(Path("/app/model-lock.json").read_text())
    manifest = {}
    for name, spec in specs.items():
        destination = Path("/models") / name
        snapshot_download(repo_id=spec["repo_id"], revision=spec["revision"],
                          allow_patterns=spec["files"], local_dir=destination, max_workers=2)
        files = {}
        for filename in spec["files"]:
            path = destination / filename
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            files[filename] = {"sha256": digest, "bytes": path.stat().st_size}
        manifest[name] = {"repo_id": spec["repo_id"], "revision": spec["revision"],
                          "license": spec["license"], "files": files}
        print(f"Downloaded and hashed {name}: {sum(f['bytes'] for f in files.values())} bytes", flush=True)
    Path("/models/download-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
