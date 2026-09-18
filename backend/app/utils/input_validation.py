"""Strict input and directive validation, adapted from the verified local oracle."""
import math

SHAPES = {
    'solar_reduction': {'hours', 'factor'},
    'minimum_battery_reserve': {'hours', 'minimum_energy_kwh'},
    'no_charge_window': {'hours'}, 'no_discharge_window': {'hours'},
    'max_grid_window': {'hours', 'max_grid_kwh'}, 'no_op': set(),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def num(x):
    return type(x) in (int, float) and math.isfinite(x) and x >= 0


def validate_input(req):
    require(isinstance(req, dict), 'request must be an object')
    require(isinstance(req.get('scenario_id'), str), 'scenario_id must be a string')
    notes = req.get('operator_notes')
    require(isinstance(notes, list) and 1 <= len(notes) <= 3, 'need 1-3 notes')
    require(all(isinstance(n, str) and n.strip() for n in notes), 'notes must be nonempty strings')
    hours = req.get('hours')
    require(isinstance(hours, list) and len(hours) == 24, 'need 24 hours')
    require(all(isinstance(h, dict) and type(h.get('hour')) is int for h in hours), 'hour must be integer')
    require(sorted(h['hour'] for h in hours) == list(range(24)), 'hours must cover 0..23 exactly once')
    for h in hours:
        for k in ('demand_kwh', 'solar_kwh', 'tariff_bdt_per_kwh'):
            require(num(h.get(k)), f'invalid {k}')
    b = req.get('battery')
    require(isinstance(b, dict), 'battery must be object')
    for k in ('capacity_kwh', 'initial_energy_kwh', 'minimum_energy_kwh',
              'max_charge_kwh_per_hour', 'max_discharge_kwh_per_hour'):
        require(num(b.get(k)), f'invalid battery {k}')
    require(b['minimum_energy_kwh'] <= b['initial_energy_kwh'] <= b['capacity_kwh'], 'initial battery outside bounds')


def validate_directives(req, directives):
    require(isinstance(directives, list) and len(directives) == len(req['operator_notes']), 'one interpretation per note required')
    for i, d in enumerate(directives):
        require(isinstance(d, dict), 'interpretation must be object')
        require(type(d.get('note_index')) is int and d['note_index'] == i, 'incorrect note_index/order')
        t = d.get('directive_type')
        require(isinstance(t, str) and t in SHAPES, 'unsupported directive')
        require(isinstance(d.get('explanation'), str), 'explanation must be string')
        require(type(d.get('applies')) is bool and d['applies'] == (t != 'no_op'), 'wrong applies semantics')
        a = d.get('structured_adjustment')
        require('structured_adjustment' in d, 'missing structured_adjustment')
        if t == 'no_op':
            require(a is None, 'no_op adjustment must be null')
            continue
        require(isinstance(a, dict) and set(a) == SHAPES[t], 'wrong adjustment shape')
        hs = a['hours']
        require(isinstance(hs, list) and all(type(h) is int and 0 <= h < 24 for h in hs), 'invalid directive hour')
        require(hs == sorted(set(hs)), 'hours must be unique and ascending')
        for k in SHAPES[t] - {'hours'}:
            require(num(a[k]), f'invalid {k}')
        if t == 'solar_reduction':
            require(a['factor'] <= 1, 'factor exceeds one')
        if t == 'minimum_battery_reserve':
            require(a['minimum_energy_kwh'] <= req['battery']['capacity_kwh'], 'reserve exceeds capacity')
