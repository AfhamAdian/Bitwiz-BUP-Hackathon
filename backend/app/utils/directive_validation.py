"""Deterministic checks supplement extraction; unknown semantics are not proven."""
import json
import re
from .input_validation import validate_directives


class InterpretationError(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__('Operator-note interpretation failed validation.')


def issue(code, note_index=None, **details):
    return {'code': code, 'note_index': note_index, **details}


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result

    def constant(value):
        raise ValueError('Non-finite JSON constant')

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def parse_model_output(raw):
    if not isinstance(raw, str):
        raise InterpretationError([issue('INVALID_JSON')])
    text = raw.strip()
    # Unwrap only a single whole-response fence, never extract arbitrary embedded JSON.
    fence = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.S | re.I)
    if fence:
        text = fence.group(1)
    try:
        data = strict_json(text)
    except (ValueError, RecursionError):
        raise InterpretationError([issue('INVALID_JSON')]) from None
    if not isinstance(data, dict) or set(data) != {'directive_interpretation', 'evidence'}:
        raise InterpretationError([issue('INVALID_ENVELOPE')])
    return data


_TIME = r'(?:noon|midnight|\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)'
_WINDOW = re.compile(r'(?<![\w:])(' + _TIME + r')\s*(?:until|to|through|and|[-–—])\s*(' + _TIME + r')(?![\w:])', re.I)


def _clock(token, endpoint=False):
    token = token.lower().replace('.', '').strip()
    if token == 'noon':
        return 12, True
    if token == 'midnight':
        return (24 if endpoint else 0), True
    match = re.fullmatch(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', token)
    if not match:
        return None, False
    h, minute, meridiem = match.groups()
    h = int(h)
    if minute not in (None, '00'):
        return None, False
    if meridiem:
        if not 1 <= h <= 12:
            return None, False
        return h % 12 + (12 if meridiem == 'pm' else 0), True
    if not 0 <= h <= 24:
        return None, False
    return h, minute is not None or h > 12 or h == 0


def explicit_hours(note):
    """One unambiguous same-day window, or None; never guess missing context."""
    matches = list(_WINDOW.finditer(note))
    if len(matches) != 1:
        return None
    left, right = matches[0].groups()
    start, start_explicit = _clock(left)
    end, end_explicit = _clock(right, endpoint=True)
    if start is None or end is None:
        return None
    suffix = re.search(r'(am|pm)$', right.lower().replace('.', '').strip())
    if not start_explicit and suffix and 1 <= start <= 12:
        start = start % 12 + (12 if suffix.group(1) == 'pm' else 0)
        start_explicit = True
    if not start_explicit or not end_explicit or not 0 <= start < end <= 24:
        return None
    return list(range(start, end))


def numeric_expectation(note, kind, capacity):
    """Cross-check one explicitly stated percent or kWh quantity."""
    percentages = list(re.finditer(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(?:%|percent\b)', note, re.I))
    if len(percentages) == 1:
        match = percentages[0]
        fraction = float(match.group(1)) / 100
        if kind == 'solar_reduction':
            tail = note[match.end():].lower()
            before = note[:match.start()].lower()
            if re.match(r'\s*(?:reduction|decrease|drop|less)\b', tail) or re.search(r'(?:reduced|decreased|drop|reduction)\s+by\s*$', before):
                return 'factor', 1-fraction
            if re.match(r'\s*(?:of\s+(?:the\s+)?(?:forecast|normal|expected|original)|remaining|usable)\b', tail) or re.search(r'(?:to|at)\s+(?:about\s+|roughly\s+)?$', before):
                return 'factor', fraction
        if kind == 'minimum_battery_reserve' and re.search(r'capacity', note, re.I):
            return 'minimum_energy_kwh', capacity*fraction
    quantities = re.findall(r'(?<![\w.])(\d+(?:\.\d+)?)\s*kwh\b', note, re.I)
    if len(quantities) == 1 and not percentages:
        if kind == 'minimum_battery_reserve':
            return 'minimum_energy_kwh', float(quantities[0])
        if kind == 'max_grid_window':
            return 'max_grid_kwh', float(quantities[0])
    return None


def validate_extraction(request, raw):
    data = parse_model_output(raw)
    directives = data['directive_interpretation']
    notes = request['operator_notes']
    if not isinstance(directives, list):
        raise InterpretationError([issue('INVALID_DIRECTIVE_LIST')])
    seen = [d.get('note_index') for d in directives if isinstance(d, dict) and type(d.get('note_index')) is int]
    issues = [issue('MISSING_NOTE', i) for i in range(len(notes)) if i not in seen]
    issues += [issue('DUPLICATE_NOTE', i) for i in range(len(notes)) if seen.count(i) > 1]
    if issues:
        raise InterpretationError(issues)
    try:
        validate_directives(request, directives)
    except ValueError as exc:
        raise InterpretationError([issue('INVALID_DIRECTIVE_SCHEMA', message=str(exc))]) from None
    evidence = data['evidence']
    if not isinstance(evidence, list) or len(evidence) != len(notes):
        raise InterpretationError([issue('INVALID_EVIDENCE_MAPPING')])
    for i, (note, d, ev) in enumerate(zip(notes, directives, evidence)):
        if (not isinstance(ev, dict) or set(ev) != {'note_index', 'time_text', 'value_text'}
                or type(ev.get('note_index')) is not int or ev['note_index'] != i):
            issues.append(issue('INVALID_EVIDENCE_MAPPING', i))
            continue
        for key in ('time_text', 'value_text'):
            quote = ev[key]
            if quote is not None and (not isinstance(quote, str) or not quote.strip() or quote not in note):
                issues.append(issue('UNGROUNDED_EVIDENCE', i, field=key))
        if d['directive_type'] == 'no_op':
            continue
        if ev['time_text'] is None:
            issues.append(issue('MISSING_TIME_EVIDENCE', i))
        adjustment = d['structured_adjustment']
        if len(adjustment) > 1 and ev['value_text'] is None:
            issues.append(issue('MISSING_VALUE_EVIDENCE', i))
        hours = explicit_hours(note)
        if hours is not None and adjustment['hours'] != hours:
            issues.append(issue('HOURS_MISMATCH', i, expected=hours, received=adjustment['hours']))
        numeric = numeric_expectation(note, d['directive_type'], request['battery']['capacity_kwh'])
        if numeric is not None:
            field, expected = numeric
            if abs(adjustment[field]-expected) > 1e-8:
                issues.append(issue('VALUE_MISMATCH', i, field=field, expected=expected, received=adjustment[field]))
    if issues:
        raise InterpretationError(issues)
    return directives
