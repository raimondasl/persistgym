"""Settings for every test run, whichever test directory it covers.

**One BLAS thread per process.** numpy and scipy use OpenBLAS, which by default starts a
thread per logical CPU for each matrix operation. When the CPUs are busy (other jobs on the
machine, or pytest-xdist's workers), those threads wait on one another, and a test full of
small fits slows down by orders of magnitude:
analysis/tests/test_persistgym_h1h3.py::test_emulate_reports_the_route_power_sims_fit_took
took 207 s with OpenBLAS's default threads and 3.2 s with one thread, measured back to back on
2026-11-25 with the CPU at 100%. The tests' matrices are small, so one thread loses nothing.

The variables must be set before numpy is first imported. pytest imports this file before any
test module, and pytest-xdist's workers inherit the environment. A value already set in the
environment is kept. tests/test_test_settings.py checks that the setting took effect.
"""

import os

BLAS_THREAD_VARIABLES = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")

for _variable in BLAS_THREAD_VARIABLES:
    os.environ.setdefault(_variable, "1")
