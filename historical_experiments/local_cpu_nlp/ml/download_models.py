from huggingface_hub import snapshot_download


MODELS = (
    ("MoritzLaurer/deberta-v3-base-zeroshot-v2.0", "8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8"),
    ("sentence-transformers/all-MiniLM-L6-v2", "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"),
)


for model_id, revision in MODELS:
    path = snapshot_download(repo_id=model_id, revision=revision)
    print(f"MODEL_READY={model_id}|{revision}|{path}", flush=True)
