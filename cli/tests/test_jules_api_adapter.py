"""Unit tests for the REST adapter; provider/network/landing operations are mocked."""
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from limen.jules_api import Catalog, JulesApiError, JulesMutationUnknown
from limen.jules_api_adapter import JulesApiExecutionAdapter, create_adapter
from limen.fanout_executor import AmbiguousProviderLaunchError, FanoutExecutionError

SOURCE = 'sources/github/owner/repo'
HEAD = 'a' * 40


def client():
    value = MagicMock()
    value.sources.return_value = Catalog(({'name': SOURCE, 'githubRepo': {'owner': 'owner', 'repo': 'repo'}},), 1, '')
    value.sessions.return_value = Catalog((), 1, '')
    value.create.return_value = {'name': 'sessions/123456789012', 'id': '123456789012', 'url': 'https://jules.google.com/task/123456789012'}
    return value


def packet():
    return {'effect': 'write', 'execution': {'owner_repository': 'owner/repo', 'exact_base': HEAD, 'topic_branch': 'fix/example'},
            'authority': {'path_prefixes': ['src/']}, 'intent': {'intended_effect': 'repair verified defect'}, 'predicate': 'python -m unittest'}


class AdapterTests(unittest.TestCase):
    def test_unarmed_does_not_make_network_request(self):
        with patch.dict('os.environ', {}, clear=True), patch('limen.jules_api_adapter.JulesApiClient.from_env') as init:
            adapter = create_adapter()
        init.assert_not_called()
        self.assertFalse(adapter.eligible(packet()))

    def test_no_fictional_hard_deadline(self):
        self.assertIs(JulesApiExecutionAdapter.enforces_deadline, False)

    def test_source_discovery_without_cli(self):
        adapter = JulesApiExecutionAdapter(client())
        self.assertTrue(adapter.eligible({'execution': {'owner_repository': 'owner/repo'}}))
        self.assertFalse(adapter.eligible({'effect': 'read', 'execution': {'owner_repository': 'owner/repo'}}))

    def test_rejects_unknown_repository(self):
        value = packet()
        value['execution']['owner_repository'] = 'other/repo'
        adapter = JulesApiExecutionAdapter(client())
        self.assertFalse(adapter.eligible(value))

    def test_invalid_concurrency(self):
        for value in [0, 16, True]:
            with self.assertRaises(FanoutExecutionError):
                JulesApiExecutionAdapter(None, concurrency=value)

    def test_bad_source_shape(self):
        remote = client()
        remote.sources.return_value = Catalog(({'name': SOURCE, 'githubRepo': None},), 1, '')
        with self.assertRaises(JulesApiError):
            JulesApiExecutionAdapter(remote)

    def test_api_launch_uses_branch_marker_and_no_auto_pr(self):
        remote = client()
        adapter = JulesApiExecutionAdapter(remote)
        with patch('limen.jules_api_adapter._default_branch', return_value='trunk'), patch('limen.jules_api_adapter.remote_branch_head', return_value=HEAD):
            result = adapter.launch(packet(), 'attempt-abc-1')
        self.assertEqual(result.provider_run_id, '123456789012')
        kwargs = remote.create.call_args.kwargs
        self.assertEqual(kwargs['branch'], 'trunk')
        self.assertFalse(kwargs['auto_create_pr'])
        self.assertTrue(kwargs['prompt'].startswith('[limen-fanout:attempt-abc-1]\n'))

    def test_changed_source_head_stops_before_create(self):
        remote = client()
        adapter = JulesApiExecutionAdapter(remote)
        with patch('limen.jules_api_adapter._default_branch', return_value='main'), patch('limen.jules_api_adapter.remote_branch_head', return_value='b' * 40):
            with self.assertRaises(FanoutExecutionError):
                adapter.launch(packet(), 'attempt-abc-1')
        remote.create.assert_not_called()

    def test_indeterminate_post_uses_existing_pending_attempt_path(self):
        remote = client()
        remote.create.side_effect = JulesMutationUnknown('mutation_outcome_unknown')
        adapter = JulesApiExecutionAdapter(remote)
        with patch('limen.jules_api_adapter._default_branch', return_value='main'), patch('limen.jules_api_adapter.remote_branch_head', return_value=HEAD):
            with self.assertRaises(AmbiguousProviderLaunchError):
                adapter.launch(packet(), 'attempt-abc-1')
        self.assertEqual(remote.create.call_count, 1)

    def test_no_free_slot_stops_before_create(self):
        remote = client()
        now = datetime.now(timezone.utc).isoformat()
        remote.sessions.return_value = Catalog(tuple({'name': f'sessions/{i}', 'state': 'PAUSED', 'createTime': now} for i in range(15)), 1, '')
        with self.assertRaises(FanoutExecutionError):
            JulesApiExecutionAdapter(remote).launch(packet(), 'attempt-abc-1')
        remote.create.assert_not_called()

    def test_roll_limit_stops_before_create(self):
        remote = client()
        now = datetime.now(timezone.utc).isoformat()
        remote.sessions.return_value = Catalog(tuple({'name': f'sessions/{i}', 'state': 'COMPLETED', 'createTime': now} for i in range(100)), 1, '')
        with self.assertRaises(FanoutExecutionError):
            JulesApiExecutionAdapter(remote).launch(packet(), 'attempt-abc-1')
        remote.create.assert_not_called()

    def test_recovery_miss_never_creates(self):
        remote = client()
        remote.find_attempt.return_value = None
        self.assertIsNone(JulesApiExecutionAdapter(remote).recover(packet(), 'attempt-abc-1'))
        remote.create.assert_not_called()

    def test_recovery_outage_never_creates(self):
        remote = client()
        remote.find_attempt.side_effect = JulesApiError('transport_unavailable')
        self.assertIsNone(JulesApiExecutionAdapter(remote).recover(packet(), 'attempt-abc-1'))
        remote.create.assert_not_called()

    def test_recovery_adopts_actual_provider_identity(self):
        remote = client()
        remote.find_attempt.return_value = remote.create.return_value
        record = JulesApiExecutionAdapter(remote).recover(packet(), 'attempt-abc-1')
        self.assertEqual(record.provider_run_id, '123456789012')
        remote.find_attempt.assert_called_once_with(marker='[limen-fanout:attempt-abc-1]', source=SOURCE)

    def test_observation_failure_is_not_reported_as_executing(self):
        remote = client()
        remote.session.side_effect = JulesApiError('transport_unavailable')
        state = JulesApiExecutionAdapter(remote).probe('123456789012')
        self.assertEqual(state.status, 'submitted')
        self.assertIn('unavailable', state.detail)

    def test_waiting_states_remain_owned_not_failed_or_executing(self):
        remote = client()
        adapter = JulesApiExecutionAdapter(remote)
        for status in ['PAUSED', 'AWAITING_PLAN_APPROVAL', 'AWAITING_USER_FEEDBACK', 'QUEUED']:
            remote.session.return_value = {'state': status}
            self.assertEqual(adapter.probe('123456789012').status, 'submitted')

    def test_completion_does_not_claim_merged(self):
        remote = client()
        remote.session.return_value = {'state': 'COMPLETED'}
        state = JulesApiExecutionAdapter(remote).probe('123456789012')
        self.assertEqual(state.status, 'succeeded')
        self.assertIn('landing still required', state.detail)

    def test_landing_patch_is_bound_to_source_and_head(self):
        remote = client()
        remote.completed_patch.return_value = 'diff'
        adapter = JulesApiExecutionAdapter(remote)
        with patch('limen.jules_api_adapter._checked', side_effect=['https://github.com/owner/repo.git', HEAD, '']) as command:
            adapter.apply_result('123456789012', Path('/synthetic/worktree'))
        remote.completed_patch.assert_called_once_with('123456789012', source=SOURCE, exact_base=HEAD)
        self.assertEqual(command.call_args.args[0], ['git', 'apply', '--index', '--whitespace=error-all', '-'])

    def test_other_repository_never_gets_patch(self):
        remote = client()
        adapter = JulesApiExecutionAdapter(remote)
        with patch('limen.jules_api_adapter._checked', return_value='https://github.com/other/repo.git'):
            with self.assertRaises(FanoutExecutionError):
                adapter.apply_result('123456789012', Path('/synthetic/worktree'))
        remote.completed_patch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
