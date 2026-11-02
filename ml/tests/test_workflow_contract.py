"""Deployment prerequisites not covered by publisher unit-test fixtures."""
from pathlib import Path

import pytest


WORKFLOWS = Path(__file__).resolve().parents[2] / '.github' / 'workflows'


@pytest.mark.parametrize('filename', [
    'refresh-predictions.yml', 'sync-stats.yml', 'qualifying-monitor.yml',
])
def test_publishing_workflows_configure_git_identity_before_running_jobs(filename):
    content = (WORKFLOWS / filename).read_text(encoding='utf-8')
    name = 'git config user.name "github-actions[bot]"'
    email = 'git config user.email "41898282+github-actions[bot]@users.noreply.github.com"'
    assert name in content, 'commit-tree requires a Git author on clean Actions runners'
    assert email in content, 'commit-tree requires a Git email on clean Actions runners'
    assert content.index('uses: actions/checkout@') < content.index(name)
    assert content.index(email) < content.index('- uses: actions/setup-')
