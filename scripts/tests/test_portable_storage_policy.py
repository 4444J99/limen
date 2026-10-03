"""Optional mounts never waive independent custody or hide provider capability."""

from pathlib import Path

import yaml


def test_portable_recovery_preserves_all_rails_and_full_acceptance():
    root = Path(__file__).resolve().parents[2]
    registry = yaml.safe_load((root / 'institutio/governance/storage-roles.yaml').read_text())
    policy = registry['portable_recovery']
    assert policy['external_drives_required'] is False
    assert policy['dropbox_bulk_fallback_allowed'] is False
    assert policy['capacity_authority'] == 'authenticated-live-provider-quota'
    assert policy['unavailable_rails_remain_visible'] is True
    assert policy['retirement_requires_separate_proof'] is True
    assert set(policy['acceptance']) == {
        'complete-original-capture-and-current-delta-denominator',
        'authenticated-exact-object-revision-readback-on-each-replica',
        'independent-provider-or-device-failure-domains',
        'full-logical-and-native-metadata-restore-from-each-replica',
        'evidenced-retention-beyond-restoration',
        'explicit-original-root-to-restored-root-relocation',
    }
    rails = registry['rails']
    assert set(rails) == {'icloud', 'googledrive', 'dropbox', 'onedrive', 'backblaze',
                          'archive4t', 't7recovery', 'time-machine', 'ingress', 'scratch'}
    assert rails['archive4t']['required_mounted'] is False
    assert rails['archive4t']['trust_gates'] == [
        {'id': 'mounted', 'gate': 'volume mounted', 'automatable': True}]
    assert rails['googledrive']['declared_state'] == 'pending-trust-gates'
    assert rails['dropbox']['declared_state'] == 'pending-trust-gates'
