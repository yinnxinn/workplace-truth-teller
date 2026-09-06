"""Offline decisions: no account credentials or live browser required."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'delivery_plan.py'


def planner():
    assert SCRIPT.exists(), 'Portable delivery planner is missing'
    spec = importlib.util.spec_from_file_location('delivery_plan', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot():
    return {
        'schema_version': 1,
        'account': {'platform': 'wechat_mp', 'alias': 'default'},
        'content_sha256': 'a' * 64,
        'authorized': True,
        'policy': 'allowed',
        'capabilities': {'official_api': 'ready', 'browser': 'ready'},
        'attempts': [],
    }


def test_api_preferred_and_missing_api_falls_back_to_browser():
    p = planner()
    state = snapshot()
    assert p.plan(p.default_config(), state)['route'] == 'official_api'
    state['capabilities']['official_api'] = 'unavailable'
    assert p.plan(p.default_config(), state)['route'] == 'browser'


def test_no_automatic_tools_produces_manual_handoff():
    p = planner()
    state = snapshot()
    state['capabilities'] = {}
    result = p.plan(p.default_config(), state)
    assert result['action'] == 'manual_handoff'
    assert result['saved'] is False


def test_ready_browser_beats_api_requiring_credentials():
    p = planner()
    state = snapshot()
    state['capabilities']['official_api'] = 'requires_user'
    assert p.plan(p.default_config(), state)['route'] == 'browser'
    state['capabilities']['browser'] = 'unavailable'
    assert p.plan(p.default_config(), state)['action'] == 'needs_user'


@pytest.mark.parametrize('policy', ['denied', 'unknown'])
def test_policy_never_falls_through_to_another_surface(policy):
    p = planner()
    state = snapshot()
    state['policy'] = policy
    result = p.plan(p.default_config(), state)
    assert result['route'] is None
    assert result['action'] == ('blocked' if policy == 'denied' else 'check_policy')


def test_config_cannot_grant_authorization():
    p = planner()
    state = snapshot()
    state['authorized'] = False
    assert p.plan(p.default_config(), state)['action'] == 'prepare_only'


@pytest.mark.parametrize('outcome', ['pending', 'unknown', 'saved', 'readback_mismatch'])
def test_uncertain_write_must_reconcile_same_route(outcome):
    p = planner()
    state = snapshot()
    state['attempts'] = [{'route': 'official_api', 'outcome': outcome}]
    result = p.plan(p.default_config(), state)
    assert result['action'] == 'reconcile'
    assert result['route'] == 'official_api'
    assert result['saved'] is False


def test_no_write_failure_allows_fallback():
    p = planner()
    state = snapshot()
    state['attempts'] = [{'route': 'official_api', 'outcome': 'rejected_no_write'}]
    assert p.plan(p.default_config(), state)['route'] == 'browser'


def test_deny_record_is_sticky_even_when_snapshot_says_allowed():
    p = planner()
    state = snapshot()
    state['attempts'] = [{'route': 'browser', 'outcome': 'policy_denied'}]
    assert p.plan(p.default_config(), state)['action'] == 'blocked'


def test_verified_requires_remote_identifier_and_readback_evidence():
    p = planner()
    state = snapshot()
    receipt = {'route': 'browser', 'outcome': 'verified'}
    state['attempts'] = [receipt]
    assert p.plan(p.default_config(), state)['action'] == 'reconcile'
    receipt['draft_id'] = 'fixture-draft'
    receipt['checks'] = dict.fromkeys(['account', 'title', 'body', 'images'], True)
    assert p.plan(p.default_config(), state)['action'] == 'reconcile'
    receipt['readback_at'] = '2026-09-06T10:00:00Z'
    receipt['evidence_ref'] = 'evidence/readback.json'
    assert p.plan(p.default_config(), state)['action'] == 'complete'
    receipt['checks']['body'] = False
    assert p.plan(p.default_config(), state)['saved'] is False


def test_block_does_not_hide_possible_prior_write():
    p = planner()
    state = snapshot()
    state['attempts'] = [{'route': 'official_api', 'outcome': 'unknown'},
                         {'route': 'browser', 'outcome': 'policy_denied'}]
    result = p.plan(p.default_config(), state)
    assert result['action'] == 'blocked'
    assert result['persistence'] == 'unknown'


def test_explicit_bounded_no_write_retry_and_exhaustion():
    p = planner()
    config = p.default_config()
    config['delivery']['max_create_attempts_per_route'] = 2
    state = snapshot()
    state['attempts'] = [{'route': 'official_api', 'outcome': 'rejected_no_write'}]
    assert p.plan(config, state)['route'] == 'official_api'
    state['attempts'].append({'route': 'official_api', 'outcome': 'rejected_no_write'})
    assert p.plan(config, state)['route'] == 'browser'


@pytest.mark.parametrize('stamp', ['', 'not-a-date', '2026-09-06'])
def test_verification_requires_timestamp_with_timezone(stamp):
    p = planner()
    state = snapshot()
    state['attempts'] = [{'route': 'browser', 'outcome': 'verified',
                         'draft_id': 'fixture', 'readback_at': stamp,
                         'evidence_ref': 'evidence/fixture.json',
                         'checks': dict.fromkeys(['account', 'title', 'body', 'images'], True)}]
    assert p.plan(p.default_config(), state)['action'] == 'reconcile'


def test_unresolved_older_write_not_hidden_by_later_failure():
    p = planner()
    state = snapshot()
    state['attempts'] = [
        {'route': 'official_api', 'outcome': 'unknown'},
        {'route': 'browser', 'outcome': 'rejected_no_write'},
    ]
    assert p.plan(p.default_config(), state)['route'] == 'official_api'
    assert p.plan(p.default_config(), state)['action'] == 'reconcile'


def test_preferences_can_disable_api_without_platform_specific_commands():
    p = planner()
    config = p.default_config()
    config['official_api']['enabled'] = False
    assert p.plan(config, snapshot())['route'] == 'browser'
    config['browser']['enabled'] = False
    assert p.plan(config, snapshot())['action'] == 'manual_handoff'


@pytest.mark.parametrize('mutation', [
    lambda c: c.update(schema_version=2),
    lambda c: c['delivery'].update(mode='publish'),
    lambda c: c['delivery'].update(order=['manual', 'browser']),
    lambda c: c['delivery'].update(order=['browser', 'browser', 'manual']),
    lambda c: c['official_api'].update(enabled='false'),
    lambda c: c['official_api'].update(app_secret='fixture-secret'),
    lambda c: c['browser'].update(command='arbitrary command'),
])
def test_bad_config_fails_closed(mutation):
    p = planner()
    config = copy.deepcopy(p.default_config())
    mutation(config)
    with pytest.raises(ValueError):
        p.plan(config, snapshot())


def test_account_or_content_identity_must_be_valid():
    p = planner()
    state = snapshot()
    state['account']['alias'] = 'another-account'
    with pytest.raises(ValueError):
        p.plan(p.default_config(), state)
    state = snapshot()
    state['content_sha256'] = 'missing'
    with pytest.raises(ValueError):
        p.plan(p.default_config(), state)


def test_cli_works_from_unrelated_directory_with_unicode_and_bom(tmp_path):
    p = planner()
    config = tmp_path / '配置.json'
    config.write_text(json.dumps({'schema_version': 1}), encoding='utf-8-sig')
    state = tmp_path / '状态.json'
    state.write_text(json.dumps(snapshot()), encoding='utf-8')
    result = subprocess.run([sys.executable, str(SCRIPT), '--config', str(config),
                             '--snapshot', str(state)], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['route'] == 'official_api'


def test_bad_cli_json_does_not_echo_secret(tmp_path):
    planner()
    config = tmp_path / 'bad.json'
    config.write_text('{"app_secret":"do-not-echo', encoding='utf-8')
    result = subprocess.run([sys.executable, str(SCRIPT), '--config', str(config)],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert 'do-not-echo' not in result.stdout + result.stderr


def test_defaults_without_snapshot_are_not_a_live_probe():
    p = planner()
    assert p.plan(p.default_config(), None)['action'] == 'probe_required'
