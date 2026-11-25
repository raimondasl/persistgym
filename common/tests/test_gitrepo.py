"""The test helper `guarded_repo` (common/tests/gitrepo.py): a copy of its per-process template
holds what a repo built in place with git holds, and copies share nothing."""

from pathlib import Path

import pytest

from common.tests import gitrepo
from common.tests.gitrepo import (
    FROZEN_PREREG,
    bare_origin,
    build_guarded_repo,
    copied_repo,
    decisions_text,
    git_in,
    git_out,
    guarded_repo,
    push_main,
    write_decisions,
)


def _state(repo: Path) -> dict:
    """What the paid guard and the tests can see of a repo, apart from commit times."""
    head = git_out(repo, "rev-parse", "HEAD").strip()
    return {"tree": git_out(repo, "rev-parse", "HEAD^{tree}").strip(),
            "files": git_out(repo, "ls-tree", "-r", "HEAD"),
            "message": git_out(repo, "log", "-1", "--format=%s%n%an <%ae>"),
            "status": git_out(repo, "status", "--porcelain"),
            "branch": git_out(repo, "rev-parse", "--abbrev-ref", "HEAD").strip(),
            "origin_url": git_out(repo, "remote", "get-url", "origin").strip(),
            "origin_heads": git_out(repo, "ls-remote", "--heads", "origin")
            .replace(head, "HEAD"),
            "tracking": git_out(repo, "for-each-ref", "--format=%(refname) %(objectname)",
                                "refs/remotes").replace(head, "HEAD")}


@pytest.mark.parametrize("push", [True, False])
def test_a_copy_holds_what_a_repo_built_in_place_holds(tmp_path, push):
    decisions = decisions_text("1-pilots", "2-arc")
    built = tmp_path / "built"
    built.mkdir()
    build_guarded_repo(built, prereg=FROZEN_PREREG, decisions=decisions, push=push)
    copy = tmp_path / "copy"
    copy.mkdir()
    assert guarded_repo(copy, prereg=FROZEN_PREREG, decisions=decisions, push=push) == copy
    want, got = _state(built), _state(copy)
    assert want.pop("origin_url") == str(bare_origin(built))
    assert got.pop("origin_url") == str(bare_origin(copy))
    assert got == want
    assert ("HEAD\trefs/heads/main" in got["origin_heads"]) is push
    assert (copy / "PREREG.md").read_text(encoding="utf-8") == FROZEN_PREREG
    assert (copy / "results" / "decisions.md").read_text(encoding="utf-8") == decisions


def test_copies_share_nothing(tmp_path):
    first, second = tmp_path / "a" / "repo", tmp_path / "b" / "repo"
    guarded_repo(first)
    head = git_out(first, "rev-parse", "HEAD").strip()
    write_decisions(first, decisions_text("1-pilots", "9-other"))
    git_in(first, "commit", "-q", "-am", "approve 9-other")
    push_main(first)
    guarded_repo(second)
    assert git_out(second, "rev-parse", "HEAD").strip() == head
    assert git_out(second, "ls-remote", "--heads", "origin").split()[0] == head
    assert git_out(second, "status", "--porcelain") == ""
    assert "9-other" not in (second / "results" / "decisions.md").read_text(encoding="utf-8")
    git_in(second, "fetch", "-q", "origin", "main")
    assert git_out(second, "rev-parse", "FETCH_HEAD").strip() == head


def test_the_origin_is_the_copys_own(tmp_path):
    """A push from a copy reaches its own bare origin, not the template's or another copy's."""
    first, second, third = (tmp_path / x / "repo" for x in "abc")
    guarded_repo(first)
    guarded_repo(second)
    # the empty global git config that git_in points git at, as a repo built in place leaves it
    assert (tmp_path / "b" / ".test-gitconfig").exists()
    (first / "x.txt").write_text("x", encoding="utf-8")
    git_in(first, "add", "x.txt")
    git_in(first, "commit", "-q", "-m", "x")
    push_main(first)
    moved = git_out(first, "rev-parse", "HEAD").strip()
    assert git_out(bare_origin(first), "rev-parse", "main").strip() == moved
    assert git_out(bare_origin(second), "rev-parse", "main").strip() != moved
    guarded_repo(third)
    assert git_out(bare_origin(third), "rev-parse", "main").strip() != moved


def test_a_copy_runs_no_git_process(tmp_path, monkeypatch):
    """Once this process has the template, a copy is made without git (its origin URL is
    rewritten in .git/config, the fallback `git remote set-url` is not needed)."""
    guarded_repo(tmp_path / "a" / "repo")

    def no_git(*args, **kwargs):
        raise AssertionError(f"a git process: {args!r}")
    monkeypatch.setattr(gitrepo.subprocess, "run", no_git)
    copy = guarded_repo(tmp_path / "b" / "repo")
    monkeypatch.undo()
    assert git_out(copy, "remote", "get-url", "origin").strip() == str(bare_origin(copy))


def test_a_template_whose_build_copies_another(tmp_path):
    """`copied_repo`'s build may itself copy a template, as arc/test_run_path.py's `_repo`
    does: each template gets a folder of its own, and the copies hold the outer build."""
    def build(template):
        guarded_repo(template, push=False)
        (template / "x.txt").write_text("x", encoding="utf-8")
        git_in(template, "add", "x.txt")
        git_in(template, "commit", "-q", "-m", "x")
        push_main(template)

    key = ("test_a_template_whose_build_copies_another", str(tmp_path))
    first = copied_repo(tmp_path / "a" / "repo", key, build)
    second = copied_repo(tmp_path / "b" / "repo", key, build)
    head = git_out(first, "rev-parse", "HEAD").strip()
    assert git_out(second, "rev-parse", "HEAD").strip() == head
    assert git_out(second, "log", "--format=%s").split() == ["x", "prereg"]
    assert git_out(second, "ls-remote", "--heads", "origin").split()[0] == head
    assert git_out(second, "remote", "get-url", "origin").strip() == str(bare_origin(second))
    assert git_out(second, "status", "--porcelain") == ""
