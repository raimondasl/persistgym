"""Keep the root test run out of the pinned harness and its scratch worktrees.

Those trees have their own environment and are tested by apply_patches.py.
"""

collect_ignore = ["upstream", ".work"]
