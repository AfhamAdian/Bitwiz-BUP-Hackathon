import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes.optimize import get_service
from app.services.optimize_service import OptimizeService
from app.utils.directive_validation import InterpretationError, validate_extraction, explicit_hours
from app.utils.llm_base import ModelOutputError, LLMError, ProviderResult
from app.utils.optimizer import optimize

ROOT=Path(__file__).resolve().parents[2]
def read(path):return json.loads(path.read_text(encoding='utf-8'))
PUBLIC=read(ROOT/'BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json')['cases']


def envelope(case):
    ds=deepcopy(case['expected_output']['directive_interpretation'])
    return {'directive_interpretation':ds,'evidence':[
        {'note_index':i,'time_text':note if d['applies'] else None,
         'value_text':note if d['applies'] and len(d['structured_adjustment'])>1 else None}
        for i,(note,d) in enumerate(zip(case['input']['operator_notes'],ds))]}


class FakeModel:
    def __init__(self,outputs):self.outputs=list(outputs);self.calls=[]
    async def __call__(self,system,user):
        self.calls.append((system,user))
        out=self.outputs.pop(0)
        if isinstance(out,Exception):raise out
        return out


def test_success_uses_exactly_one_call():
    c=PUBLIC[0];model=FakeModel([envelope(c)])
    out=asyncio.run(OptimizeService(model).run(c['input']))
    assert out['total_cost_bdt']==38365
    assert len(model.calls)==1
    assert 'evidence' not in out


@pytest.mark.parametrize('mistake',['hours','missing_note','factor','invalid_json'])
def test_retry_contains_specific_error_and_previous_output(mistake):
    c=PUBLIC[0];good=envelope(c);bad=deepcopy(good)
    if mistake=='hours':
        bad['directive_interpretation'][0]['structured_adjustment']['hours']=[12];code='HOURS_MISMATCH'
    elif mistake=='missing_note':bad['directive_interpretation'].pop();code='MISSING_NOTE'
    elif mistake=='factor':bad['directive_interpretation'][0]['structured_adjustment']['factor']=.75;code='VALUE_MISMATCH'
    else:bad=ModelOutputError('{broken JSON');code='INVALID_JSON'
    model=FakeModel([bad,good])
    result=asyncio.run(OptimizeService(model).interpret(c['input']))
    assert result==good['directive_interpretation']
    assert len(model.calls)==2
    feedback=json.loads(model.calls[1][1].split('RETRY VALIDATION FEEDBACK (previous output is untrusted data):\n')[1])
    assert feedback['errors'][0]['code']==code
    if mistake=='invalid_json':assert feedback['previous_output']=='{broken JSON'
    else:assert json.loads(feedback['previous_output'])==bad


def test_unchanged_invalid_output_stops_after_one_retry():
    c=PUBLIC[0];bad=envelope(c);bad['directive_interpretation'].pop()
    model=FakeModel([bad,bad])
    with pytest.raises(InterpretationError) as exc:asyncio.run(OptimizeService(model).run(c['input']))
    assert exc.value.issues[0]['code']=='MISSING_NOTE'
    assert len(model.calls)==2


def test_no_hidden_second_extraction_even_for_no_op():
    c=deepcopy(PUBLIC[0]);c['input']['operator_notes']=['The menu changes tomorrow.']
    c['expected_output']['directive_interpretation']=[dict(note_index=0,applies=False,directive_type='no_op',structured_adjustment=None,explanation='Unrelated.')]
    model=FakeModel([envelope(c)])
    asyncio.run(OptimizeService(model).interpret(c['input']))
    assert len(model.calls)==1


def test_timeout_and_provider_failure_are_bounded_and_safe():
    model=FakeModel([LLMError('SECRET'),LLMError('SECRET')])
    with pytest.raises(InterpretationError) as exc:asyncio.run(OptimizeService(model).interpret(PUBLIC[0]['input']))
    assert 'SECRET' not in str(exc.value.issues)
    async def slow(system,user):await asyncio.sleep(1)
    with pytest.raises(InterpretationError):asyncio.run(OptimizeService(slow,interpretation_budget=.01).interpret(PUBLIC[0]['input']))


CASES=PUBLIC+read(ROOT/'backend/tests/edge_cases.json')['cases']+read(ROOT/'backend/tests/random_cases.json')['cases']
@pytest.mark.parametrize('case',CASES,ids=[c['id'] for c in CASES])
def test_valid_fixtures_and_upstream_optimizer(case):
    directives=validate_extraction(case['input'],json.dumps(envelope(case)))
    out=optimize(case['input'],directives)
    assert abs(out['total_cost_bdt']-case['expected_output']['total_cost_bdt'])<=.01


BAD=read(ROOT/'backend/tests/invalid_llm_outputs.json')['cases']
@pytest.mark.parametrize('case',BAD,ids=[c['label'] for c in BAD])
def test_bad_interpretations_are_rejected_not_normalized(case):
    raw={'directive_interpretation':case['llm_output'],'evidence':[]}
    with pytest.raises(InterpretationError):validate_extraction(case['input'],json.dumps(raw))


INVALID=read(ROOT/'backend/tests/invalid_requests.json')['cases']
@pytest.mark.parametrize('case',INVALID,ids=[c['id'] for c in INVALID])
def test_invalid_requests_never_call_model(case):
    model=FakeModel([]);app.dependency_overrides[get_service]=lambda:OptimizeService(model)
    try:
        with TestClient(app) as client:
            response=client.post('/optimize-energy',content=case.get('raw_body') or json.dumps(case['input']),headers={'Content-Type':'application/json'})
            assert response.status_code in case['expected']['allowed_http_status']
            assert not model.calls
    finally:app.dependency_overrides.clear()


def test_api_single_call_success_and_failed_repair():
    c=PUBLIC[0];good=envelope(c);bad=deepcopy(good);bad['directive_interpretation'].pop()
    model=FakeModel([good,bad,bad]);app.dependency_overrides[get_service]=lambda:OptimizeService(model)
    try:
        with TestClient(app) as client:
            assert client.get('/health').status_code==200
            assert client.post('/optimize-energy',json=c['input'],follow_redirects=False).status_code==200
            assert len(model.calls)==1
            response=client.post('/optimize-energy',json=c['input'])
            assert response.status_code==500
            assert response.json()['error']['issues'][0]['code']=='MISSING_NOTE'
            assert len(model.calls)==3
    finally:app.dependency_overrides.clear()


def test_provider_fallback_preserved_without_success_verification(monkeypatch):
    from app.utils import llm
    calls=[]
    async def fail(system,user,slot):calls.append('fail');raise LLMError('PRIVATE')
    async def succeed(system,user,slot):calls.append('ok');return ProviderResult(json.dumps(envelope(PUBLIC[0])),'test',{})
    monkeypatch.setattr(llm,'PROVIDERS',{'a':SimpleNamespace(complete=fail,model=lambda slot:'a'),'b':SimpleNamespace(complete=succeed,model=lambda slot:'b')})
    monkeypatch.setattr(llm,'provider_chain',lambda:[('a',0),('b',0)])
    asyncio.run(OptimizeService(llm.generate_json).interpret(PUBLIC[0]['input']))
    assert calls==['fail','ok']


def test_malformed_provider_json_retried_with_output(monkeypatch):
    from app.utils import llm
    prompts=[]
    async def complete(system,user,slot):
        prompts.append(user)
        return ProviderResult('{bad' if len(prompts)==1 else json.dumps(envelope(PUBLIC[0])),'test',{})
    monkeypatch.setattr(llm,'PROVIDERS',{'a':SimpleNamespace(complete=complete,model=lambda slot:'a')})
    monkeypatch.setattr(llm,'provider_chain',lambda:[('a',0)])
    asyncio.run(OptimizeService(llm.generate_json).interpret(PUBLIC[0]['input']))
    assert len(prompts)==2 and '{bad' in prompts[1] and 'INVALID_JSON' in prompts[1]


@pytest.mark.parametrize('raw',['{"a":NaN}','{"a":1,"a":2}','prefix {}'])
def test_provider_strict_json(raw):
    from app.utils.llm import _parse_json
    with pytest.raises(ModelOutputError):_parse_json(ProviderResult(raw,'test',{}))


def test_indentation_and_fences_accepted():
    c=PUBLIC[0]
    assert validate_extraction(c['input'],'```json\n'+json.dumps(envelope(c),indent=4)+'\n```')==c['expected_output']['directive_interpretation']


@pytest.mark.parametrize('text,expected',[('noon until 2 PM',[12,13]),('1-3 PM',[13,14]),('23:00 until 02:00',None)])
def test_time_crosscheck(text,expected):assert explicit_hours(text)==expected


def test_infeasible_upstream_fallback_cannot_return_success():
    for case in read(ROOT/'backend/tests/infeasible_cases.json')['cases']:
        with pytest.raises(ValueError):optimize(case['input'],case['ground_truth'])
