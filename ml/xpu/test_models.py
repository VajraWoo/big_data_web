"""Synthetic FP32 CPU/XPU comparison; no real review training or checkpoints."""
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

import numpy as np
import psutil
import pytest
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer

REPO = Path(__file__).resolve().parents[2]
MODELS = REPO / "tmp/xpu/models"
REPORTS = REPO / "tmp/xpu/reports"
DEVICE = os.environ.get("NLP_DEVICE", "xpu")
WARMUP, REPEATS = 2, 5


@pytest.fixture(scope="module", autouse=True)
def require_device_and_local_files():
    assert DEVICE in {"cpu", "xpu"}
    if DEVICE == "xpu":
        assert torch.xpu.is_available(), "XPU required: no CPU fallback"
    assert os.environ.get("HF_HUB_OFFLINE") == "1"
    torch.set_num_threads(8)
    lock = json.loads((REPO / "ml/model-lock.json").read_text())
    manifest = json.loads((MODELS / "download-manifest.json").read_text())
    for name, spec in lock.items():
        assert manifest[name]["revision"] == spec["revision"]
        assert set(manifest[name]["files"]) == set(spec["files"])
        for filename, info in manifest[name]["files"].items():
            path = MODELS / name / filename
            assert path.stat().st_size == info["bytes"]
            with path.open("rb") as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == info["sha256"]


def synchronize():
    if DEVICE == "xpu":
        torch.xpu.synchronize()


def write_report(name, values):
    values.update({
        "status": "PASS", "scope": "synthetic environment benchmark only",
        "device": DEVICE, "torch": torch.__version__, "precision": "fp32",
        "device_name": torch.xpu.get_device_name(0) if DEVICE == "xpu" else "CPU (8 threads)",
        "warmup": WARMUP, "repeats": REPEATS,
        "process_peak_working_set_bytes": psutil.Process().memory_info().peak_wset,
        "xpu_peak_allocated_bytes": torch.xpu.max_memory_allocated() if DEVICE == "xpu" else None,
        "xpu_peak_reserved_bytes": torch.xpu.max_memory_reserved() if DEVICE == "xpu" else None,
    })
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{DEVICE}-{name}.json").write_text(json.dumps(values, indent=2), encoding="utf-8")
    summary = {key: value for key, value in values.items() if key != "first_three_embeddings"}
    print("XPU_COMPARISON_RESULT=" + json.dumps(summary), flush=True)


def test_distilbert_forward_backward_and_timing():
    torch.manual_seed(42)
    tokenizer = AutoTokenizer.from_pretrained(MODELS / "distilbert", local_files_only=True,
                                               trust_remote_code=False)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODELS / "distilbert", num_labels=2, local_files_only=True,
        trust_remote_code=False, use_safetensors=True, attn_implementation="eager",
    ).to(DEVICE)
    if DEVICE == "xpu":
        torch.xpu.reset_peak_memory_stats()
    texts = ["The sample device is easy to clean.", "The sample device leaks water."] * 4
    batch = tokenizer(texts, return_tensors="pt", padding="max_length", truncation=True,
                      max_length=128).to(DEVICE)
    labels = torch.tensor([0, 1] * 4, device=DEVICE)
    parameter = model.distilbert.transformer.layer[0].attention.q_lin.weight
    before = parameter.detach().cpu().clone()
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5, foreach=False)
    model.train()
    training = []
    losses = []
    for step in range(WARMUP + REPEATS):
        synchronize()
        start = time.perf_counter()
        optimizer.zero_grad(set_to_none=True)
        output = model(**batch, labels=labels)
        output.loss.backward()
        optimizer.step()
        synchronize()
        elapsed = time.perf_counter() - start
        assert torch.isfinite(output.loss).item()
        assert parameter.grad is not None and torch.isfinite(parameter.grad).all().item()
        losses.append(output.loss.item())
        if step >= WARMUP:
            training.append(elapsed)
    assert parameter.device.type == DEVICE
    assert torch.isfinite(parameter).all().item()
    assert not torch.equal(before, parameter.detach().cpu())
    model.eval()
    inference = []
    with torch.no_grad():
        for step in range(WARMUP + REPEATS):
            synchronize()
            start = time.perf_counter()
            logits = model(**batch).logits
            synchronize()
            elapsed = time.perf_counter() - start
            assert logits.shape == (8, 2) and torch.isfinite(logits).all().item()
            if step >= WARMUP:
                inference.append(elapsed)
    write_report("distilbert", {
        "batch_size": 8, "sequence_length": 128, "seed": 42,
        "training_seconds": training, "inference_seconds": inference,
        "training_median_seconds": statistics.median(training),
        "inference_median_seconds": statistics.median(inference),
        "losses": losses, "backbone_updated": True,
        "timing_scope": "preloaded model and device tensors; synchronized compute; excludes assertions",
    })


def test_minilm_embeddings_and_timing():
    model = SentenceTransformer(str(MODELS / "minilm"), device=DEVICE,
                                local_files_only=True, trust_remote_code=False,
                                model_kwargs={"attn_implementation": "eager"})
    if DEVICE == "xpu":
        torch.xpu.reset_peak_memory_stats()
    texts = ["A compact ice maker for a small kitchen.",
             "A small appliance that makes ice.",
             "An example sentence used only to test the environment."] * 8
    timings = []
    for step in range(WARMUP + REPEATS):
        synchronize()
        start = time.perf_counter()
        vectors = model.encode(texts, batch_size=8, normalize_embeddings=True, show_progress_bar=False)
        synchronize()
        elapsed = time.perf_counter() - start
        assert vectors.shape == (24, 384)
        assert np.isfinite(vectors).all()
        assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
        if step >= WARMUP:
            timings.append(elapsed)
    assert next(model.parameters()).device.type == DEVICE
    write_report("minilm", {
        "batch_size": 8, "sentences": 24, "embedding_shape": list(vectors.shape),
        "seconds": timings, "median_seconds": statistics.median(timings),
        "timing_scope": "encode including tokenization and return to CPU; excludes model load",
        "first_three_embeddings": vectors[:3].tolist(),
    })
