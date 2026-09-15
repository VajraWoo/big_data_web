"""Offline environment acceptance, using only synthetic English sentences."""
import hashlib
import json
from pathlib import Path
import platform
import resource
import time

import numpy as np
import torch
import transformers
import sentence_transformers
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path("/models")
LOCK = json.loads(Path("/app/model-lock.json").read_text())


def save_report(name, values):
    values.update({
        "status": "PASS", "scope": "environment-only; not a trained business model",
        "python": platform.python_version(), "torch": torch.__version__,
        "transformers": transformers.__version__,
        "sentence_transformers": sentence_transformers.__version__,
        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    })
    Path(f"/reports/{name}.json").write_text(json.dumps(values, indent=2), encoding="utf-8")
    print("NLP_ENVIRONMENT_RESULT=" + json.dumps(values), flush=True)


def test_downloaded_models_have_matching_checksums_and_pinned_revisions():
    manifest = json.loads((ROOT / "download-manifest.json").read_text())
    assert set(manifest) == set(LOCK)
    for name, spec in LOCK.items():
        assert manifest[name]["revision"] == spec["revision"]
        assert set(manifest[name]["files"]) == set(spec["files"])
        for filename, info in manifest[name]["files"].items():
            path = ROOT / name / filename
            assert path.stat().st_size == info["bytes"]
            with path.open("rb") as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == info["sha256"]


def test_distilbert_cpu_forward_backward_and_backbone_update():
    start = time.perf_counter()
    torch.manual_seed(42)
    torch.set_num_threads(8)
    assert torch.version.cuda is None
    assert not torch.cuda.is_available()
    tokenizer = AutoTokenizer.from_pretrained(ROOT / "distilbert", local_files_only=True, trust_remote_code=False)
    model = AutoModelForSequenceClassification.from_pretrained(
        ROOT / "distilbert", num_labels=2, local_files_only=True,
        trust_remote_code=False, use_safetensors=True,
    ).to("cpu")
    batch = tokenizer(["The sample device is easy to clean.", "The sample device leaks water."],
                      return_tensors="pt", padding=True, truncation=True, max_length=64)
    labels = torch.tensor([0, 1])  # Arbitrary smoke labels, not a real annotated dataset.
    parameter = model.distilbert.transformer.layer[0].attention.q_lin.weight
    before = parameter.detach().clone()
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5)
    model.train()
    optimizer.zero_grad()
    output = model(**batch, labels=labels)
    assert torch.isfinite(output.loss)
    assert output.logits.shape == (2, 2)
    output.loss.backward()
    assert parameter.grad is not None
    assert torch.isfinite(parameter.grad).all()
    assert parameter.grad.abs().sum().item() > 0
    optimizer.step()
    assert torch.isfinite(parameter).all()
    assert not torch.equal(before, parameter.detach())
    model.eval()
    with torch.no_grad():
        assert torch.isfinite(model(**batch).logits).all()
    save_report("distilbert", {
        "model_revision": LOCK["distilbert"]["revision"], "device": "cpu", "seed": 42,
        "training_steps": 1, "batch_size": 2, "loss": output.loss.item(),
        "backbone_updated": True, "seconds": round(time.perf_counter() - start, 3),
    })


def test_minilm_cpu_embeddings():
    start = time.perf_counter()
    torch.set_num_threads(8)
    model = SentenceTransformer(str(ROOT / "minilm"), device="cpu",
                                local_files_only=True, trust_remote_code=False)
    vectors = model.encode([
        "A compact ice maker for a small kitchen.",
        "A small appliance that makes ice.",
        "An example sentence used only to test the environment.",
    ], normalize_embeddings=True, show_progress_bar=False)
    assert vectors.shape == (3, 384)
    assert np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    save_report("minilm", {"model_revision": LOCK["minilm"]["revision"], "device": "cpu",
                           "embedding_shape": list(vectors.shape),
                           "seconds": round(time.perf_counter() - start, 3)})
