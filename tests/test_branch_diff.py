import pytest
from brain.branch_diff import BranchDiff
from brain.config import Config
from brain.embedder import Embedder

def test_branch_validation_invalid_names():
    config = Config()
    embedder = Embedder("all-MiniLM-L6-v2")
    engine = BranchDiff(config, embedder)

    # These should throw ValueError during validation
    invalid_branches = [
        "; rm -rf /",
        "branch1 & branch2",
        "branch|ls",
        "-flags",
        "--another-flag",
        "some`command`here",
        "$(whoami)",
    ]

    for invalid in invalid_branches:
        with pytest.raises(ValueError) as excinfo:
            engine.compare_branches(invalid, "main")
        assert "Invalid branch name" in str(excinfo.value)

        with pytest.raises(ValueError) as excinfo:
            engine.compare_branches("main", invalid)
        assert "Invalid branch name" in str(excinfo.value)
