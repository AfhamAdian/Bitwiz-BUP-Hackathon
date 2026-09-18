# BUP CSE Fest 2026 — Submission and README Checklist

Based on the supplied **Participant Guide & Evaluation Rubric** and **Preliminary Problem Statement**. The Problem Statement governs API behavior and optimization; the Guide governs submission, deployment, scoring, and repository policy. This document is a checklist, not a claim that the team has completed every item.

## 1. Required submission package

| Deliverable | What to provide | Acceptance checks |
|---|---|---|
| Public API | Base URL for one deployed service | Judge can call `GET /health` and `POST /optimize-energy` without login, manual approval, VPN, or private-network access. |
| GitHub repository | Repository URL with complete source and dependency/configuration files | Repository created after question reveal, kept private during the event, and made public after the submission deadline. |
| README and configuration | Self-contained `README.md` and configuration instructions | Organizers can run and test from a clean environment without team assistance. Document variable names, never secret values. |
| Docker fallback image | Pullable registry reference with an exact tag or digest | Image starts with the documented command, binds to `0.0.0.0`, exposes the documented port, reaches `/health`, and contains no baked-in secrets. |
| Solution video | Organizer-accessible link or MP4 upload | Maximum 3 minutes. Explain the problem, architecture, implementation choices, and run/testing process. |

The fallback image is required by the Guide; do not treat a Dockerfile alone as the submitted image. Keep the API, image, repository, and video accessible throughout evaluation.

### Submission fields to prepare

```text
Public API base URL:
GitHub repository URL:
README location:
Docker image reference with exact tag/digest:
Container/service port:
Required environment-variable names:
Verified docker run command:
Video link or uploaded MP4:
```

Do not put API keys or other secret values into these fields. Follow the organizers' actual submission form for the final field names and upload mechanism; the supplied PDFs do not specify every form detail.

## 2. Files to include in the repository

Include everything needed to build, run, and reproduce the service. For the current BUP codebase, this normally means:

| File or directory | Purpose |
|---|---|
| `README.md` | Complete setup, architecture, API, test, and deployment documentation. |
| `backend/app/` | API routes, schemas, provider adapters, validation, services, configuration, and middleware. |
| `gridwise/` | Optimization and schedule-validation implementation imported by the backend. |
| `backend/requirements.txt` | Runtime dependencies. |
| `backend/requirements-dev.txt` | Test/development dependencies, if referenced by the instructions. |
| `backend/.env.example` | Configuration names and non-secret defaults/placeholders. |
| `.gitignore` and relevant nested ignore files | Keep secrets and local artifacts out of version control. |
| Tests and required fixtures | Reproduce documented validation and end-to-end checks. Include public sample data if the tests load it from the repository. |
| Test configuration | For example, `backend/pytest.ini`, if required to discover tests or resolve imports. |
| `tools/` scripts referenced by tests or README | Keep required support modules and runnable verification scripts. |
| Docker build files | Dockerfile, `.dockerignore`, and any required startup/build configuration. |

The Guide does not mandate this exact directory layout. The requirement is completeness and reproducibility. Do not delete a file merely because it looks like a test artifact: first check whether tests, imports, the Docker build, or README commands depend on it.

## 3. What the README must contain

### A. Purpose and architecture

- Explain the 24-hour campus energy-scheduling problem and the grid-cost objective.
- Describe the actual flow: request validation → LLM note interpretation → deterministic guardrails and bounded repair → optimizer → final schedule replay → response.
- Identify where the LLM is used. It must produce the structured directives that affect optimization.
- Name the optimizer/solver and explain how applicable directives become constraints.
- Describe provider fallback and failure behavior as actually implemented.

### B. Clean local quickstart

- Supported Python/runtime version and any other prerequisites.
- Clone command and correct working directory for subsequent commands.
- Exact dependency-install command.
- How to create local configuration from `.env.example` and supply secrets privately.
- Exact service-start command, host binding, and port.
- A health request and its expected successful result: HTTP 200 with `{"status":"ok"}`.
- At least one public sample request against `/optimize-energy` and the expected interpretation/cost or validation result.

The quickstart must work without undocumented paths, globally installed packages, or files that exist only on a team member's computer.

### C. Environment and model configuration

Include a table with each relevant variable's **name**, **purpose**, **required/optional status**, and **non-secret default**, if any.

For this codebase, document the selected configuration from `backend/.env.example`, such as:

- `PROVIDER_ORDER`.
- Groq key slots and model settings, if used.
- Gemini key/model settings, if used.
- OmniRoute key/model/base URL settings, if used.
- Provider timeout settings and any application-level timeout that overrides them.

State the actual provider/model or local model identifier used for judging. Distinguish the configured preferred model from fallback models. A variable name or placeholder is acceptable; a working secret value is not.

### D. API contract and examples

- Exact routes: `GET /health` and `POST /optimize-energy`.
- Request shape, including 24 hours, battery fields, and 1–3 operator notes.
- Successful response fields and a representative example.
- HTTP status behavior for malformed requests, interpretation failures, and internal failures.
- Explain that equivalent valid optimal schedules may have different hourly actions.
- Explain that reported totals are recomputed from the returned plan.

Provide copy-paste request examples. If a command uses a fixture, state the exact file path and send only the case's `input` object.

### E. Guardrails and limitations

- One ordered interpretation per note; supported types; exact adjustment shapes; valid hours and numeric bounds.
- Start-inclusive/end-exclusive windows and the meaning of remaining solar fraction.
- Validation before optimization and final replay afterward.
- Bounded retries with the previous output and specific validation errors.
- No silent conversion of malformed or missing relevant directives into `no_op`.
- Known semantic limitations: deterministic checks cannot prove arbitrary natural-language intent.
- Any unresolved specification assumptions or unsupported ambiguous inputs.

Document the current single-extraction design accurately: one model call on a normal successful path, with repair when validation fails. Provider fallback can add HTTP calls. Do not claim independent second-model verification if it has been removed.

### F. Testing and expected results

- Exact public-sample test procedure and expected result.
- Full regression-test command and required dependencies.
- End-to-end HTTP-test command.
- Explain which tests use authored/mock model responses and which actually call an external model.
- For live testing, explain how to start the configured service and send the public samples.

Current local commands, from the repository root:

```powershell
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m pytest -q tests ../tests
python -m pytest -q tests/test_http_flow.py
```

The last recorded local results were **381 tests passed**, including **18 end-to-end HTTP tests with a local provider stub**. These results do not establish real-model accuracy, live-provider latency, or public deployment readiness. Update the counts after subsequent code changes.

### G. Docker fallback

- Exact pullable registry image reference, including tag or digest.
- `docker pull` command.
- Verified `docker run` command with the correct port mapping and configuration mechanism.
- Container listening port and `0.0.0.0` binding.
- Health-check command and expected response.
- Required runtime environment-variable names, without their secret values.

Example format only—replace the placeholders and verify it:

```text
docker pull <registry>/<team>/<image>:<exact-tag>
docker run --rm --env-file <private-local-env-file> -p <host-port>:<container-port> <registry>/<team>/<image>:<exact-tag>
```

The private environment file stays outside the repository and image. A successful image build alone is not proof that the image can be pulled and run by organizers.

### H. Dependencies, credits, and known limitations

- List external libraries, frameworks, solvers, and tools, and credit external assistance/dependencies as required by the Guide.
- Explain model/API availability and quota requirements.
- State known limitations and which deployment or live tests have actually been performed.
- Include secret-handling guidance.

## 4. Security exclusions and repository hygiene

### Prohibited by the supplied rules

- API keys, access tokens, passwords, or other secrets committed to the repository.
- Real secret values in README examples, submission fields, logs, API responses, or exposed stack traces.
- Secrets baked into the submitted Docker image.
- Live campus, utility, billing, or personal data. Use synthetic challenge data.

Do not copy `.env` into the repository or Docker image. Provide `.env.example` with empty values/placeholders instead. Do not record keys on screen in the video.

### Recommended exclusions for a clean submission

These are repository-hygiene recommendations, not additional competition prohibitions:

- Virtual environments such as `.venv/`.
- `__pycache__/`, `*.pyc`, and `.pytest_cache/`.
- Local debug logs, crash dumps, temporary files, and editor-specific local state.
- Intermediate assistant progress notes or superseded verification reports.
- Unused generated code and duplicate outputs that no test/build/run procedure requires.
- Machine-specific absolute paths in instructions or runtime configuration.

Retain useful test fixtures and end-to-end tests. A local Git stash/checkpoint is not part of a normal branch push and need not be included in the submission.

If a real secret was ever committed, removing it from the latest file is insufficient: revoke/rotate it and address repository-history exposure before publication.

## 5. API and optimization constraints

| Constraint | Required behavior |
|---|---|
| Health readiness | `/health` returns the ready response within 60 seconds of startup. |
| Request duration | `/optimize-energy` completes within 30 seconds. |
| Latency scoring | p95 ≤5 seconds earns full latency points; slower bands reduce credit. |
| Interpretation | A real language-capable generative model interprets the notes into directives used by optimization. |
| Note coverage | Exactly one entry per note, in index order; no missing or duplicate mappings. |
| No-op semantics | `applies=false`, `directive_type="no_op"`, and null adjustment. Other directives use `applies=true`. |
| Hours | 24 unique scenario/plan hours 0–23; directive hours sorted, unique, and in range. |
| Energy balance | Grid + used solar + discharge = demand + charge every hour. |
| Solar | Never use more than effective solar after directives. Curtailment allowed; grid export is not part of the challenge. |
| Battery | Respect state transitions, capacity, reserves, charge/discharge rates, and action restrictions. |
| Neutrality | Final battery energy equals initial energy. |
| Grid caps | Obey every applicable per-hour import limit. |
| Totals | Grid total, cost, and peak must agree with replayed plan values. |
| Numeric tolerance | Absolute 0.01 kWh/BDT unless the official judge specifies a stricter tolerance. |
| Validity before cost | A cheap plan violating a true directive or physical rule earns no optimization credit for that case. |
| Robustness | Controlled malformed-input/model/provider failure handling; do not crash or expose secrets. |

No hard-coded phrase matcher as the sole interpreter, no LLM used only for cosmetic summaries, and no requirement for long training/fine-tuning during evaluation.

## 6. Video checklist

- [ ] Duration is at most 3 minutes.
- [ ] Explains the problem and objective.
- [ ] Shows the architecture and LLM → guardrails → optimizer → replay flow.
- [ ] Explains key implementation choices and how to run/test the solution.
- [ ] Link or upload is accessible to organizers.
- [ ] No credentials or sensitive configuration appear in the recording.

The video is required but contributes no base points to the 100-point score. It is used when tied total scores need to be resolved.

## 7. Final pre-submission checklist

- [ ] Public API URL is reachable from outside the development environment.
- [ ] Health and optimization endpoints use the exact required paths and JSON contract.
- [ ] Real provider credentials, quota, models, and fallback availability have been tested.
- [ ] Public samples have been exercised against the actual deployed service.
- [ ] Local regression and end-to-end tests pass.
- [ ] README instructions work from a clean environment without team help.
- [ ] Repository visibility and creation timing comply with the official rules.
- [ ] No secrets, private data, or unnecessary local artifacts are included.
- [ ] Docker image is published with an exact tag/digest and is pullable.
- [ ] Documented Docker command starts the service and reaches `/health`.
- [ ] Video meets the time/access requirements.
- [ ] All submitted URLs and artifacts remain available throughout evaluation.

## 8. Source references

- **Participant Guide & Evaluation Rubric:** required deliverables and package (pp. 2–3), deployment/security/repository rules (pp. 4–5), reproducibility and scoring (pp. 6–8), penalties and hidden evaluation (pp. 9–10), final checklist (p. 11).
- **Preliminary Problem Statement:** directives and objective (pp. 3–4), API and request schema (pp. 4–5), guardrails and energy rules (pp. 5–6), output and validation (pp. 7–9).

Page references are physical PDF pages in the supplied document pack. Use the official rulebook and organizer announcements for participation details not stated in these files.
