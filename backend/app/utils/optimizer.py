"""Use the upstream optimizer, but fail closed if its fallback violates directives."""
from pathlib import Path
import sys

ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from energy_optimizer import build_response, replay_validate, resolve


def optimize(request, directives):
    request = dict(request, hours=sorted(request['hours'], key=lambda h: h['hour']))
    # The statement does not specify how differing overlapping solar factors combine.
    factors = {}
    for d in directives:
        if d['directive_type'] == 'solar_reduction':
            adjustment = d['structured_adjustment']
            for hour in adjustment['hours']:
                if hour in factors and factors[hour] != adjustment['factor']:
                    raise ValueError('Ambiguous overlapping solar reductions.')
                factors[hour] = adjustment['factor']
    response = build_response(request, directives)
    report = replay_validate(request, resolve(directives), response)
    if not report.ok:
        raise ValueError('Optimizer could not satisfy all validated directives.')
    return response
