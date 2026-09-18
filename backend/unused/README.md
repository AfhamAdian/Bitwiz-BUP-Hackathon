# Unused

Files kept for reference but not read by the app or any test.

- `tests/invalid_responses.json` — response-validation fixtures (candidate_output /
  detected_reason pairs) for a judge-style response replay checker. No test in
  `backend/tests/` currently consumes this file; `edge_cases.json`,
  `infeasible_cases.json`, `invalid_llm_outputs.json`, and `invalid_requests.json`
  cover the same ground and are wired into `test_interpretation.py`.
