# Backend development skeleton

This is a FastAPI mock backend for the first frontend skeleton. It intentionally does **not** read T007 candidate output or claim Gold status.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
pytest -q
```

## Implemented endpoints

- `GET /healthz`
- `GET /api/v1/health`
- `GET /api/v1/catalog/categories`
- `GET /api/v1/products`
- `GET /api/v1/products/{parent_asin}/overview`
- `GET /api/v1/products/{parent_asin}/themes?sentiment=positive|negative`
- `GET /api/v1/products/{parent_asin}/improvements`
- `GET /api/v1/themes/{theme_id}`
- `GET /api/v1/themes/{theme_id}/reviews`
- `GET /api/v1/analysis/batch`

All responses are marked `data_source=mock` and `is_gold=false`. Ratio values stay `definition_pending` until downstream T008–T010 semantics are frozen.
