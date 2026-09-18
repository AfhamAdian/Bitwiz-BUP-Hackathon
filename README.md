# Bitwiz BUP GridWise backend

GridWise energy scheduling with provider fallback, strict operator-note validation, targeted LLM repair, and the `gridwise` optimizer.

## Call count

- Valid input and valid first model output: **one LLM call**. No independent second extraction.
- Invalid model JSON/schema, missing notes, wrong explicit hours/values, or invalid evidence: **one repair attempt**, carrying the previous output and specific errors.
- If the repair is still invalid: controlled error, no schedule. Missing/invalid directives are never silently converted to `no_op`.
- Invalid request: no model calls.
- The existing provider fallback chain is preserved. A transport/provider failure may cause additional underlying HTTP calls. The two-attempt limit counts extraction/repair attempts, not provider fallback HTTP calls.

Each extraction attempt has a 12-second timeout across its provider chain; the shared interpretation budget is 24 seconds. `/optimize-energy` has a 28-second processing timeout. Blocking solver work runs in a thread; cancellation does not forcibly kill that thread.

## Setup

Python 3.11+. From the repository root:

```powershell
python -m pip install -r backend/requirements-dev.txt
Copy-Item backend/.env.example backend/.env
```

Fill in your provider settings in `backend/.env` using the upstream Groq/Gemini/OmniRoute configuration. Keep the file private. Do not overwrite an existing configured `.env` when repeating setup.

```powershell
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --env-file backend/.env
```

Endpoints: `GET /health`, `POST /optimize-energy`, and upstream `POST /test` for note interpretation only. `/optimize-energy/` also works. Health checks process readiness, not paid provider availability.

Test the public sample:

```powershell
$samplePack = Get-Content BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json -Raw | ConvertFrom-Json
$requestBody = $samplePack.cases[0].input | ConvertTo-Json -Depth 30
Invoke-RestMethod http://localhost:8000/optimize-energy -Method Post -ContentType application/json -Body $requestBody
```

The first sample should produce solar hours `[12,13]`, factor `0.25`, note 1 as `no_op`, and optimal cost 38365 BDT. Different valid optimal schedules are accepted.

## Validation and repair

Strict JSON parsing rejects duplicate keys and nonfinite constants. Indentation is irrelevant and a surrounding JSON code fence is tolerated. Deterministic code checks one ordered entry per note, exact adjustment shapes, types, applicability, unique ascending hours, finite numbers, and capacity bounds.

The model also supplies internal evidence: one object per note with `note_index`, `time_text`, and `value_text`. Evidence must quote the original note verbatim. Known explicit time windows and single numeric quantities are checked against the original note. Evidence is not returned in successful API responses.

Returning `[12]` for noon until 2 PM produces this retry context:

```json
{
  "errors": [{"code": "HOURS_MISMATCH", "note_index": 0, "expected": [12, 13], "received": [12]}],
  "previous_output": "<the complete previous model response>",
  "instruction": "Correct these errors and return all notes and evidence in the required JSON format."
}
```

The original notes and scenario are also retained in the retry prompt. Previous model text is explicitly marked untrusted. A repair must return the whole result, not a partial patch. Raw provider failures/model outputs are not included in public errors or logs.

Validated directives reach the upstream optimizer. The integration sorts request hours and replays the returned plan against the original accepted directives. The upstream optimizer can relax constraints internally; the API wrapper refuses any returned plan that fails replay rather than publishing an invalid fallback as success.

## Tests

From the repository root:

```powershell
cd backend
python -m pytest -q tests ../tests
```

The suite contains **381 tests**, including 18 end-to-end TCP/HTTP tests that start a real API subprocess and local provider stub. Coverage includes single-call success, complete retry context, missing notes, wrong hours/factors, malformed JSON, invalid requests/model outputs, provider fallback, concurrent requests, error recovery, timeouts, 153 public/generated valid fixtures, and infeasible plans. Tests make no live provider requests; real-model accuracy and latency require configured credentials.

## Docker fallback

Image: `suprio85/gridwise:preli-v1` (Docker Hub). Built from `backend/Dockerfile`; binds `0.0.0.0:8000` inside the container and ships a built-in `/health` healthcheck. No secrets are baked in — `.dockerignore` excludes `.env`/`.env.*` and keeps only `.env.example`.

```powershell
docker pull suprio85/gridwise:preli-v1
docker run --rm --env-file backend/.env -p 8000:8000 suprio85/gridwise:preli-v1
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected: HTTP 200 with `{"status":"ok"}`.

Required environment-variable names (values stay in your private `backend/.env`, never in the image or repository): `PROVIDER_ORDER`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_BASE_URL`, `GROQ_API_KEY`, `GROQ_API_KEY1`, `GROQ_API_KEY2`, `GROQ_MODEL`, `GROQ_MODEL1`, `GROQ_MODEL2`, `GROQ_BASE_URL`, `OMNIROUTE_API_KEY`, `OMNIROUTE_MODEL`, `OMNIROUTE_BASE_URL`, `LLM_TIMEOUT_SECONDS`, `LLM_CONNECT_TIMEOUT_SECONDS`. `/health` responds without any of these set; `/optimize-energy` requires working provider credentials.

## Limits

Deterministic checks cannot prove arbitrary natural-language intent. A structurally valid but semantically wrong directive outside recognized time/quantity patterns may pass. In particular, a false `no_op` is not checked by a second model.

Time checks do not guess ambiguous or cross-midnight wording. Differing overlapping solar factors are not defined by the problem statement and are rejected by the API integration. The existing upstream `gridwise` library itself is unchanged.

Live provider accuracy/latency and deployment have not been tested in this integration. Dependencies: FastAPI/Starlette, Pydantic/settings, HTTPX, NumPy, SciPy/HiGHS, and Pytest. Structural validation was adapted from the verified local participant-docs oracle; optimization and provider routing use the pulled repository implementation.
