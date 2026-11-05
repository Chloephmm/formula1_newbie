"""Fail closed when a diagnostic checkout attempts production publication."""
import os


def require_production():
    if (os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('GITHUB_REF') != 'refs/heads/main'
            or os.environ.get('GITHUB_REPOSITORY') != 'Chloephmm/formula1_newbie'
            or os.environ.get('PREDICTION_BRANCH', 'main') != 'main'):
        raise SystemExit('production publication requires this repository GitHub Action on main; use --dry-run locally')
