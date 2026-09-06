"""Portable, offline draft-delivery decisions. Never connects or writes a draft.

The host agent supplies observations from its authorized tools. A JSON preference
or a planner result grants no permissions and is not evidence of a live save.
Python 3.10+, standard library only.
"""
import argparse
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys

ROUTES = ('official_api', 'browser', 'manual')
CAPABILITIES = ('ready', 'unavailable', 'unsupported', 'requires_user')
OUTCOMES = ('pending', 'unknown', 'saved', 'readback_mismatch', 'verified',
            'unavailable', 'rejected_no_write', 'policy_denied')
CHECKS = ('account', 'title', 'body', 'images')


def default_config():
    return {
        'schema_version': 1,
        'account': {'platform': 'wechat_mp', 'alias': 'default'},
        'delivery': {'mode': 'draft', 'order': list(ROUTES), 'output_dir': './delivery',
                     'max_create_attempts_per_route': 1},
        'official_api': {
            'enabled': True,
            'credential_env': {'app_id': 'WECHAT_APP_ID', 'app_secret': 'WECHAT_APP_SECRET'},
        },
        'browser': {'enabled': True, 'provider': 'auto', 'endpoint_env': 'WECHAT_CDP_ENDPOINT'},
    }


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _merge(base, values):
    _require(isinstance(values, dict), 'configuration must be an object')
    for key, value in values.items():
        # Do not echo unrecognized keys or values: malformed input may be a secret.
        _require(key in base, 'unknown configuration field')
        if isinstance(base[key], dict):
            _merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def normalize_config(values):
    config = _merge(default_config(), values)
    _require(type(config['schema_version']) is int and config['schema_version'] == 1,
             'unsupported configuration version')
    account = config['account']
    _require(account['platform'] == 'wechat_mp', 'unsupported publishing platform')
    _require(isinstance(account['alias'], str) and bool(account['alias'].strip()),
             'account alias is required')
    delivery = config['delivery']
    _require(delivery['mode'] == 'draft', 'only draft delivery is supported')
    limit = delivery['max_create_attempts_per_route']
    _require(type(limit) is int and 1 <= limit <= 2, 'create attempt limit must be 1 or 2')
    order = delivery['order']
    _require(isinstance(order, list) and bool(order)
             and all(isinstance(r, str) and r in ROUTES for r in order)
             and len(set(order)) == len(order) and order[-1] == 'manual',
             'order must contain unique routes and end with manual')
    _require(isinstance(delivery['output_dir'], str) and bool(delivery['output_dir'].strip()),
             'output directory must be a nonempty path')
    for route in ROUTES[:2]:
        _require(type(config[route]['enabled']) is bool, 'enabled must be boolean')
    _require(isinstance(config['browser']['provider'], str)
             and bool(config['browser']['provider'].strip()), 'browser provider is required')
    env_names = list(config['official_api']['credential_env'].values())
    env_names.append(config['browser']['endpoint_env'])
    _require(all(isinstance(name, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name)
                 for name in env_names), 'credentials and endpoints must use environment names')
    return config


def load_config(path=None):
    """One config file, no implicit search or secret environment substitution."""
    selected = path or os.environ.get('TRUTH_TELLER_CONFIG')
    if not selected:
        return default_config(), Path.cwd()
    file = Path(selected).expanduser().resolve()
    with file.open(encoding='utf-8-sig') as stream:
        values = json.load(stream)
    return normalize_config(values), file.parent


def _validate_snapshot(state, config):
    _require(isinstance(state, dict), 'snapshot must be an object')
    _require(state.get('schema_version') == 1, 'unsupported snapshot version')
    _require(state.get('account') == config['account'], 'snapshot account mismatch')
    digest = state.get('content_sha256')
    _require(isinstance(digest, str) and re.fullmatch('[a-f0-9]{64}', digest),
             'snapshot requires a SHA256 content identity')
    _require(type(state.get('authorized')) is bool, 'snapshot requires observed authorization')
    _require(state.get('policy') in ('allowed', 'denied', 'unknown'), 'invalid policy state')
    caps = state.get('capabilities')
    _require(isinstance(caps, dict), 'snapshot capabilities must be an object')
    _require(all(k in ROUTES[:2] and v in CAPABILITIES for k, v in caps.items()),
             'invalid capability state')
    attempts = state.get('attempts')
    _require(isinstance(attempts, list), 'snapshot attempts must be a list')
    for attempt in attempts:
        _require(isinstance(attempt, dict) and attempt.get('route') in ROUTES[:2]
                 and attempt.get('outcome') in OUTCOMES, 'invalid attempt receipt')


def _verified(receipt):
    checks = receipt.get('checks')
    try:
        stamp = datetime.fromisoformat(receipt.get('readback_at', '').replace('Z', '+00:00'))
        timed = stamp.tzinfo is not None
    except (ValueError, AttributeError, TypeError):
        timed = False
    return (receipt['outcome'] == 'verified'
            and isinstance(receipt.get('draft_id'), str) and bool(receipt['draft_id'].strip())
            and timed and isinstance(receipt.get('evidence_ref'), str)
            and bool(receipt['evidence_ref'].strip())
            and isinstance(checks, dict) and all(checks.get(k) is True for k in CHECKS))


def plan(config, snapshot=None):
    config = normalize_config(config)

    def result(action, route=None, reason=None):
        attempts = snapshot['attempts'] if snapshot else []
        possible = [a for a in attempts if a['outcome'] in
                    ('pending', 'unknown', 'saved', 'readback_mismatch', 'verified')]
        unresolved = [a for a in possible if not _verified(a)]
        persistence = 'unknown' if unresolved else ('verified' if possible else 'not_saved')
        return {'schema_version': 1, 'action': action, 'route': route,
                'saved': persistence == 'verified', 'persistence': persistence,
                'draft_ids': list(dict.fromkeys(a['draft_id'] for a in possible
                                               if isinstance(a.get('draft_id'), str))),
                'unresolved_routes': sorted({a['route'] for a in unresolved}),
                'reason': reason or action}

    if snapshot is None:
        return result('probe_required')
    _validate_snapshot(snapshot, config)
    attempts = snapshot['attempts']
    if snapshot['policy'] == 'denied' or any(a['outcome'] == 'policy_denied' for a in attempts):
        return result('blocked', reason='policy_denied')
    if not snapshot['authorized']:
        return result('prepare_only', reason='draft_not_authorized')
    if snapshot['policy'] == 'unknown':
        return result('check_policy')
    # Any possible write must be reconciled before another create, even if a later
    # attempt failed. Update that receipt after readback; do not erase history.
    for attempt in attempts:
        if attempt['outcome'] in ('pending', 'unknown', 'saved', 'readback_mismatch', 'verified'):
            if not _verified(attempt):
                return result('reconcile', attempt['route'], 'write_not_verified')
    if any(_verified(a) for a in attempts):
        return result('complete', next(a['route'] for a in attempts if _verified(a)))
    counts = {r: sum(a['route'] == r and a['outcome'] != 'unavailable' for a in attempts)
              for r in ROUTES[:2]}
    needs_user = []
    for route in config['delivery']['order']:
        if route == 'manual':
            break
        if not config[route]['enabled'] or counts[route] >= config['delivery']['max_create_attempts_per_route']:
            continue
        status = snapshot['capabilities'].get(route, 'unavailable')
        if status == 'ready':
            return result('deliver', route, 'capability_ready')
        if status == 'requires_user':
            needs_user.append(route)
    if needs_user:
        return result('needs_user', needs_user[0], 'login_or_setup_required')
    return result('manual_handoff', 'manual', 'no_available_automatic_route')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', help='UTF-8 JSON; otherwise TRUTH_TELLER_CONFIG or defaults')
    parser.add_argument('--snapshot', help='observations from the host; omission never implies readiness')
    args = parser.parse_args(argv)
    try:
        config, base = load_config(args.config)
        state = None
        if args.snapshot:
            with Path(args.snapshot).open(encoding='utf-8-sig') as stream:
                state = json.load(stream)
        output = plan(config, state)
        output['output_dir'] = str((base / config['delivery']['output_dir']).resolve())
        print(json.dumps(output, ensure_ascii=True))
        return 0
    except (OSError, ValueError, TypeError):
        print(json.dumps({'error': 'invalid_or_unreadable_delivery_input'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
