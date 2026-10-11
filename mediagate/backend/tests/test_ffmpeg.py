"""Exercises the real ffmpeg/ffprobe binaries (skipped if absent)."""
import shutil
import subprocess

import pytest

from app.worker.ffmpeg import FFmpegError, convert, probe

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture
def sample(tmp_path):
    p = tmp_path / "input.bin"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", "-f", "mp4", str(p)], check=True)
    return p


async def _ok(_):
    return True


async def test_probe_and_remux(sample, tmp_path):
    info = await probe(sample, tmp_path)
    assert info.has_video and info.audio_codec == "aac" and 1.5 < info.duration < 2.5
    out = tmp_path / "output.mp4"
    await convert("remux_mp4", sample, out, tmp_path, duration=info.duration, audio_codec=info.audio_codec,
                  on_progress=_ok)
    assert (await probe(out, tmp_path)).has_video


async def test_extract_audio(sample, tmp_path):
    info = await probe(sample, tmp_path)
    out = tmp_path / "output.m4a"
    await convert("extract_m4a", sample, out, tmp_path, duration=info.duration, audio_codec="aac", on_progress=_ok)
    res = await probe(out, tmp_path)
    assert not res.has_video and res.audio_codec == "aac"


async def test_rejects_playlist_disguised_as_input(tmp_path):
    evil = tmp_path / "input.bin"
    evil.write_text("#EXTM3U\n#EXTINF:1,\nfile:///etc/passwd\n")
    with pytest.raises(FFmpegError):
        await probe(evil, tmp_path)


async def test_rejects_paths_outside_workdir(sample, tmp_path):
    other = tmp_path / "sub"
    other.mkdir()
    with pytest.raises(FFmpegError):
        await probe(sample, other)


async def test_unknown_operation(sample, tmp_path):
    with pytest.raises(FFmpegError):
        await convert("rm -rf", sample, tmp_path / "o.mp4", tmp_path, duration=1, audio_codec="aac", on_progress=_ok)


async def test_abort_via_progress(sample, tmp_path):
    async def stop(_):
        return False
    with pytest.raises(FFmpegError):
        await convert("extract_m4a", sample, tmp_path / "o.m4a", tmp_path, duration=0.01, audio_codec="opus",
                      on_progress=stop)
