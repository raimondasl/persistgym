"""Free analysis of ARC Prize's published public-set runs (PLAN.md §8.1, amendment §16.3).

This package holds only the OPERATIONAL slice: how published runs ended, time and cost per
action, cached share, clean-run cost bounds and the eligibility re-check. The hypothesis
slice (H5, per-level P(clear | reached) by harness) waits for the PREREG commit and must not
be computed here.
"""
