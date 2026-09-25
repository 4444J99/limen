import copy
import unittest
from quota_status import current_quota, safe_failure, annotate

STAMP = '2026-09-24T11:46:01.509922+00:00'
DAY = {'date': '2026-09-24', 'kv': {'read': 704, 'write': 57, 'list': 37},
       'd1': {'rowsRead': 5992, 'rowsWritten': 6431}}

class QuotaStatusTests(unittest.TestCase):
    def test_current_counts_and_missing_deletes(self):
        got = current_quota([DAY], STAMP)
        self.assertEqual(got['state'], 'BELOW_REPORTED_LIMITS_SO_FAR')
        self.assertEqual(got['metrics']['kv.write']['percent_used'], 5.7)
        self.assertEqual(got['metrics']['d1.rowsWritten']['percent_used'], 6.431)
        self.assertEqual(got['unreported_metrics'], ['kv.delete'])
        self.assertFalse(got['whole_day_verified'])
        self.assertEqual(got['reset_at'], '2026-09-25T00:00:00Z')

    def test_yesterdays_exhaustion_does_not_become_todays(self):
        past = {'date': '2026-09-23', 'kv': {'write': 5125}}
        self.assertEqual(current_quota([past, DAY], STAMP)['state'], 'BELOW_REPORTED_LIMITS_SO_FAR')
        self.assertEqual(current_quota([past], STAMP)['state'], 'UNOBSERVED')

    def test_missing_day_or_duplicate_data_cannot_pass(self):
        for days in ([], [DAY, DAY]):
            self.assertEqual(current_quota(days, STAMP)['state'], 'UNOBSERVED')

    def test_limit_thresholds_apply_before_day_finishes(self):
        for count, state in ((799, 'BELOW_REPORTED_LIMITS_SO_FAR'),
                             (800, 'HEADROOM_LOW'), (1000, 'AT_OR_OVER_REPORTED_LIMIT')):
            day = copy.deepcopy(DAY); day['kv']['write'] = count
            self.assertEqual(current_quota([day], STAMP)['state'], state)

    def test_d1_has_independent_limits(self):
        day = copy.deepcopy(DAY); day['d1']['rowsWritten'] = 100001
        self.assertEqual(current_quota([day], STAMP)['state'], 'AT_OR_OVER_REPORTED_LIMIT')

    def test_bad_counts_not_coerced_to_zero(self):
        for count in (True, '57', float('nan'), float('inf'), -1):
            day = copy.deepcopy(DAY); day['kv']['write'] = count
            self.assertEqual(current_quota([day], STAMP)['state'], 'UNOBSERVED')

    def test_utc_normalization_and_explicit_timezone(self):
        got = current_quota([DAY], '2026-09-23T20:17:43-04:00')
        self.assertEqual(got['date'], '2026-09-24')
        with self.assertRaises(ValueError): current_quota([DAY], '2026-09-24T11:00:00')

    def test_failure_projection_never_echoes_raw_content(self):
        got = safe_failure({'lastStatus': 'failure', 'lastFailureCode': 'private-secret',
                            'lastFailureDetail': {'category': 'private-detail', 'token': 'private-token'}})
        self.assertNotIn('private', str(got))
        self.assertEqual(got['failure_code'], 'unclassified_failure')
        self.assertEqual(safe_failure({'lastStatus': 'failure', 'lastFailureCode': 'invocation_request_limit'})['failure_code'], 'invocation_request_limit')

    def test_success_drops_stale_failure(self):
        self.assertEqual(safe_failure({'lastStatus': 'success', 'lastFailureCode': 'database'})['failure_code'], None)

    def test_low_quota_does_not_mask_failed_jobs(self):
        report = {'observed_at': STAMP, 'usage': {'days': [DAY]}, 'state': 'ACTION_REQUIRED',
                  'schedulers': {'ops-scheduler-production': {'jobs': {'ucc-staging': {'healthy': False}}}}}
        got = annotate(report)
        self.assertEqual(got['state'], 'ACTION_REQUIRED')
        self.assertEqual(got['failed_active_jobs'], ['ucc-staging'])

    def test_current_exhaustion_cannot_hide_behind_observing(self):
        day = copy.deepcopy(DAY); day['kv']['write'] = 1001
        got = annotate({'observed_at': STAMP, 'usage': {'days': [day]}, 'state': 'OBSERVING'})
        self.assertEqual(got['state'], 'ACTION_REQUIRED')

if __name__ == '__main__': unittest.main()
