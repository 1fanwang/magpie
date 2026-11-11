# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Save names built from repository paths."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pr_management.code_review import data

from .builders import node, thread

# The rule vetted-ops applies to every `--save` name (`_SAVE_NAME` in vetted_ops/ops.py).
SAVE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")

LONG = "plugins/magpie-security-tools/tools/security-management/src/security_management/issue_sync/state.py"


def test_a_short_path_keeps_its_readable_slug() -> None:
    assert data.slug("tools/foo/bar.py") == "tools_foo_bar.py"


@pytest.mark.parametrize("path", ["tools/foo/bar.py", LONG, "x/" * 200 + "y.py"])
def test_the_path_commits_save_name_is_one_vetted_ops_accepts(path: str) -> None:
    assert SAVE_NAME.match(f"path-commits-{data.slug(path)}.json")


def test_long_paths_that_share_a_stem_get_different_names() -> None:
    assert data.slug(LONG) != data.slug(LONG.replace("state.py", "other.py"))


def test_load_pr_combines_paginated_threads(tmp_path: Path) -> None:
    first = node(7, threads=[thread("one", outdated=False, resolved=True)])
    second = node(7, threads=[thread("two", outdated=True)])
    for pr, has_next in ((first, True), (second, False)):
        pr["reviewThreads"]["totalCount"] = 2
        pr["reviewThreads"]["pageInfo"] = {"hasNextPage": has_next, "endCursor": "cursor"}
    path = tmp_path / "pr.json"
    path.write_text(
        json.dumps(
            [
                {"data": {"viewer": {"login": "alice"}, "repository": {"pullRequest": pr}}}
                for pr in (first, second)
            ]
        )
    )
    loaded = data.load_pr(path)
    assert loaded.threads_complete
    assert loaded.unresolved_threads == 1
    assert [item["id"] for item in data.outdated_threads(loaded)] == ["two"]


@pytest.mark.parametrize(
    "damage", ["truncated", "duplicate", "changed-head", "changed-count", "changed-updated"]
)
def test_load_pr_rejects_inconsistent_pages(tmp_path: Path, damage: str) -> None:
    first = node(7, threads=[thread("one", outdated=False, resolved=True)])
    second = node(7, threads=[thread("two", outdated=False)])
    for pr, has_next in ((first, True), (second, False)):
        pr["reviewThreads"]["totalCount"] = 2
        pr["reviewThreads"]["pageInfo"] = {"hasNextPage": has_next, "endCursor": "cursor"}
    if damage == "truncated":
        second["reviewThreads"]["pageInfo"]["hasNextPage"] = True
    elif damage == "duplicate":
        second["reviewThreads"]["nodes"][0]["id"] = "one"
    elif damage == "changed-head":
        second["headRefOid"] = "different"
    elif damage == "changed-count":
        second["reviewThreads"]["totalCount"] = 3
    else:
        second["updatedAt"] = "2026-10-02T00:00:00Z"
    path = tmp_path / "pr.json"
    path.write_text(json.dumps([{"data": {"repository": {"pullRequest": pr}}} for pr in (first, second)]))
    assert not data.load_pr(path).threads_complete
