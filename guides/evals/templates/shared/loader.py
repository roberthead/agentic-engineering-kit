"""Load and validate the YAML golden cases.

Reads every ``*.yaml`` under ``cases_dir``, parses it with ``yaml.safe_load``,
and validates it into a ``GoldenCase``. Cases are returned sorted by ``id`` so
runner output is stable across machines.

``prompt_sha`` is deliberately NOT computed here: cases ship ``prompt_sha: null``
and the harness overlay's ``produce_run.py`` injects the real sha at run time
(agent-sdk hashes the concierge ``prompt.md``; claude-api computes it from its
block-list prompt). The sha source is genuinely harness-divergent, so it lives in
the overlay, not in this shared loader.

# TODO(kickstart): a verify-against-pinned-sha path (fail a case if the run's
# injected prompt_sha doesn't match a sha pinned in the YAML) is a documented
# extension point, not shipped logic. Today cases pin null and grouping rides on
# the run-time sha.
"""

from pathlib import Path

import yaml

from .models import GoldenCase


def load_cases(cases_dir: Path) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for path in sorted(cases_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        if raw is None:
            raise ValueError(f"Empty or invalid case file: {path}")
        cases.append(GoldenCase.model_validate(raw))
    return sorted(cases, key=lambda case: case.id)
