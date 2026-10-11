import os
import time
import uuid

import pytest

from app.core.errors import NotFound
from app.services.storage import object_key, safe_local_path
from app.worker.cleanup import sweep_temp_dirs
from app.worker.processor import safe_filename


def test_sweep_removes_only_old_dirs(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    (old / "input.bin").write_bytes(b"x")
    past = time.time() - 7200
    os.utime(old, (past, past))
    removed = sweep_temp_dirs(tmp_path, max_age_seconds=3600)
    assert removed == 1 and not old.exists() and new.exists()


def test_sweep_does_not_follow_symlinks(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    keep = outside / "keep.txt"
    keep.write_text("important")
    root = tmp_path / "work"
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    sweep_temp_dirs(root, max_age_seconds=0)
    assert keep.exists() and not (root / "link").exists()


def test_sweep_missing_root(tmp_path):
    assert sweep_temp_dirs(tmp_path / "nope", 1) == 0


@pytest.mark.parametrize("key", ["../etc/passwd", "a/../../b", "/etc/passwd"])
def test_safe_local_path_blocks_traversal(tmp_path, key):
    with pytest.raises(NotFound):
        safe_local_path(tmp_path, key)


def test_object_key_is_server_generated():
    uid, did = uuid.uuid4(), uuid.uuid4()
    assert object_key(uid, did, "mp4") == f"{uid}/{did}.mp4"
    with pytest.raises(Exception):
        object_key(uid, did, "sh")


@pytest.mark.parametrize("title", ['"; rm -rf / #', "../../etc/passwd", "Ünïcödé 🎬 title", None, "$(whoami)`id`"])
def test_safe_filename(title):
    name = safe_filename(title, "x", "123", "mp4")
    assert name.endswith("_x-123.mp4")
    assert all(c.isalnum() or c in "-_." for c in name)
    assert ".." not in name and "/" not in name
