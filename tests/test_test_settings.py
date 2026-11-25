"""The test run's own settings (conftest.py at the repository root)."""

import os

import numpy as np
import scipy.linalg
from threadpoolctl import threadpool_info


def test_blas_runs_the_threads_the_environment_names():
    """conftest.py sets OPENBLAS_NUM_THREADS (default 1) before numpy is first imported, so
    every OpenBLAS that numpy and scipy load runs that many threads. If something imported numpy
    before conftest.py ran, OpenBLAS would have started one thread per CPU and this fails."""
    assert "OPENBLAS_NUM_THREADS" in os.environ
    np.ones((4, 4)) @ np.ones((4, 4))
    scipy.linalg.solve(np.eye(4), np.ones(4))
    openblas = [p for p in threadpool_info() if p["internal_api"] == "openblas"]
    assert openblas, threadpool_info()
    expected = int(os.environ["OPENBLAS_NUM_THREADS"])
    assert {p["num_threads"] for p in openblas} == {expected}, openblas
