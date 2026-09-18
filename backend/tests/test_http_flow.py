"""Real TCP integration: Uvicorn -> provider adapter -> local HTTP provider stub.

No external model, credentials, or paid calls. These tests verify plumbing, not
the semantic accuracy of a real generative model.
"""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Thread, Lock
import time

import httpx
import pytest

from gridwise import replay_validate, resolve

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT/'BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json').read_text(encoding='utf-8'))['cases']


def model_answer(case):
    directives = deepcopy(case['expected_output']['directive_interpretation'])
    return {'directive_interpretation': directives, 'evidence': [
        {'note_index': i, 'time_text': note if d['applies'] else None,
         'value_text': note if d['applies'] and len(d['structured_adjustment']) > 1 else None}
        for i, (note, d) in enumerate(zip(case['input']['operator_notes'], directives))]}


@pytest.fixture(scope='module')
def live_stack():
    state = {'faults': deque(), 'requests': [], 'lock': Lock()}

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with state['lock']:
                state['requests'].append(payload)
                fault = state['faults'].popleft() if state['faults'] else None
            if fault == 'rate_limit':
                self.send_response(429)
                self.end_headers()
                self.wfile.write(b'{"error":"TEST_ONLY_PROVIDER_ERROR"}')
                return
            prompt = payload['messages'][-1]['content']
            original = prompt.split('RETRY VALIDATION FEEDBACK')[0]
            case = next(c for c in CASES if all(n in original for n in c['input']['operator_notes']))
            answer = model_answer(case)
            if fault == 'hours':
                answer['directive_interpretation'][0]['structured_adjustment']['hours'] = [12]
            if fault == 'missing':
                answer['directive_interpretation'].pop()
            content = '{bad JSON' if fault == 'json' else json.dumps(answer)
            body = json.dumps({'model': 'local-http-test', 'choices': [
                {'finish_reason': 'stop', 'message': {'content': content}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    env = os.environ.copy()
    env.update(PROVIDER_ORDER='groq,groq', GROQ_API_KEY='TEST_ONLY',
               GROQ_API_KEY1='TEST_ONLY', GROQ_API_KEY2='TEST_ONLY',
               GROQ_MODEL='local-test', GROQ_MODEL1='local-test', GROQ_MODEL2='local-test',
               GROQ_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',
               GEMINI_API_KEY='', OMNIROUTE_API_KEY='', LLM_TIMEOUT_SECONDS='2',
               LLM_CONNECT_TIMEOUT_SECONDS='1')
    # Separate process exercises real import/startup and HTTP transport. Hide Windows console.
    process = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend',
         '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    client = httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=30)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail('API process exited during startup')
            try:
                if client.get('/health').status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(.1)
        else:
            pytest.fail('API startup timed out')
        yield client, state
    finally:
        client.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def verify_response(case, response):
    assert response.status_code == 200, response.text
    out = response.json()
    expected = case['expected_output']
    assert out['scenario_id'] == case['input']['scenario_id']
    for actual, truth in zip(out['directive_interpretation'], expected['directive_interpretation']):
        for field in ('note_index', 'applies', 'directive_type', 'structured_adjustment'):
            assert actual[field] == truth[field]
    assert len(out['directive_interpretation']) == len(expected['directive_interpretation'])
    assert 'evidence' not in out
    report = replay_validate(case['input'], resolve(expected['directive_interpretation']), out)
    assert report.ok, report.violations
    assert abs(out['total_cost_bdt'] - expected['total_cost_bdt']) <= .01


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_public_case_over_real_http(live_stack, case):
    client, state = live_stack
    before = len(state['requests'])
    verify_response(case, client.post('/optimize-energy', json=case['input']))
    assert len(state['requests']) - before == 1


@pytest.mark.parametrize('fault,code', [('hours','HOURS_MISMATCH'), ('missing','MISSING_NOTE'), ('json','INVALID_JSON')])
def test_repair_over_real_http(live_stack, fault, code):
    client, state = live_stack
    before = len(state['requests'])
    state['faults'].append(fault)
    verify_response(CASES[0], client.post('/optimize-energy', json=CASES[0]['input']))
    assert len(state['requests']) - before == 2
    prompt = state['requests'][-1]['messages'][-1]['content']
    assert code in prompt and 'previous_output' in prompt


def test_failed_repair_and_recovery_over_http(live_stack):
    client, state = live_stack
    before = len(state['requests'])
    state['faults'].extend(['missing', 'missing'])
    response = client.post('/optimize-energy', json=CASES[0]['input'])
    assert response.status_code == 500
    assert response.json()['error']['issues'][0]['code'] == 'MISSING_NOTE'
    assert len(state['requests']) - before == 2
    assert client.get('/health').status_code == 200
    verify_response(CASES[0], client.post('/optimize-energy', json=CASES[0]['input']))


def test_provider_fallback_over_http(live_stack):
    client, state = live_stack
    before = len(state['requests'])
    state['faults'].append('rate_limit')
    verify_response(CASES[0], client.post('/optimize-energy', json=CASES[0]['input']))
    assert len(state['requests']) - before == 2


def test_bad_request_does_not_reach_provider(live_stack):
    client, state = live_stack
    before = len(state['requests'])
    for raw in ['{', 'null', '{"x":NaN}']:
        assert client.post('/optimize-energy', content=raw, headers={'Content-Type':'application/json'}).status_code == 400
    assert len(state['requests']) == before


def test_concurrent_requests_are_isolated(live_stack):
    client, state = live_stack
    cases = [CASES[i] for i in [0, 4, 9]]
    before = len(state['requests'])
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda c: client.post('/optimize-energy',json=c['input']), cases))
    for case, response in zip(cases,responses):
        verify_response(case,response)
    assert len(state['requests']) - before == 3


def test_test_endpoint_uses_same_validator(live_stack):
    client, state = live_stack
    case = CASES[0]
    payload = {k:case['input'][k] for k in ('operator_notes','battery','hours')}
    before = len(state['requests'])
    state['faults'].append('hours')
    response = client.post('/test',json=payload)
    assert response.status_code == 200
    assert response.json()['directive_interpretation'][0]['structured_adjustment']['hours'] == [12,13]
    assert len(state['requests']) - before == 2
