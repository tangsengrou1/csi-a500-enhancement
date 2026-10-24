"""Ridge/linear-model compatibility module.

The implementation lives in :mod:`a500.linear_model`, copied from the
project source snapshot. ``run.py --train-linear`` is the supported runner.
"""

from a500.linear_model import (  # noqa: F401
    LinearScreenResult,
    candidate_grid,
    make_pipeline,
    run_linear_folds,
    screen_linear_features,
)
