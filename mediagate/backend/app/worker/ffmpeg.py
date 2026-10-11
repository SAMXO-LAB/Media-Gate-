"""Safe FFmpeg/ffprobe execution.

* argv lists only (asyncio.create_subprocess_exec) — never a shell, never user strings;
* inputs are server-generated paths inside the job's work dir;
* the demuxer is forced to `mov` (MP4/M4A) and protocols restricted to `file`, so a crafted
  input can't be reinterpreted as a playlist that pulls in other files or URLs;
* hard timeout; the process is killed on expiry or cancellation.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

ProgressCb = Callable[[float], Awaitable[bool]]  # returns False to abort

ALLOWED_FORMATS = {"mov,mp4,m4a,3gp,3g2,mj2"}
SAFE_INPUT = ["-protocol_whitelist", "file", "-f", "mov"]


class FFmpegError(Exception):
    pass


@dataclass
class ProbeResult:
    format_name: str
    duration: float | None
    has_video: bool
    audio_codec: str | None


def _check_path(p: Path, root: Path) -> str:
    rp = p.resolve()
    if not rp.is_relative_to(root.resolve()):
        raise FFmpegError("path outside work dir")
    return str(rp)


async def _run(argv: list[str], timeout: float, on_line: Callable[[str], Awaitable[bool]] | None = None
               ) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out_chunks: list[bytes] = []

    async def read_stdout() -> None:
        assert proc.stdout
        async for raw in proc.stdout:
            out_chunks.append(raw)
            if on_line and not await on_line(raw.decode(errors="replace").strip()):
                proc.kill()
                return

    try:
        err_task = asyncio.create_task(proc.stderr.read())  # type: ignore[union-attr]
        await asyncio.wait_for(read_stdout(), timeout=timeout)
        await asyncio.wait_for(proc.wait(), timeout=max(1.0, timeout))
        err = await err_task
    except (asyncio.TimeoutError, asyncio.CancelledError):
        proc.kill()
        await proc.wait()
        raise FFmpegError("processing timed out") from None
    return proc.returncode or 0, b"".join(out_chunks), err


async def probe(path: Path, root: Path) -> ProbeResult:
    s = get_settings()
    argv = [s.ffprobe_path, "-v", "error", *SAFE_INPUT, "-show_entries",
            "format=format_name,duration:stream=codec_type,codec_name", "-of", "json", _check_path(path, root)]
    code, out, _ = await _run(argv, timeout=60)
    if code != 0:
        raise FFmpegError("file is not a valid MP4")
    data = json.loads(out or b"{}")
    fmt = data.get("format", {})
    if fmt.get("format_name") not in ALLOWED_FORMATS:
        raise FFmpegError("unexpected container")
    streams = data.get("streams", [])
    audio = next((st.get("codec_name") for st in streams if st.get("codec_type") == "audio"), None)
    try:
        duration = float(fmt["duration"]) if fmt.get("duration") else None
    except ValueError:
        duration = None
    return ProbeResult(fmt["format_name"], duration, any(st.get("codec_type") == "video" for st in streams), audio)


async def convert(operation: str, src: Path, dst: Path, root: Path, *, duration: float | None,
                  audio_codec: str | None, on_progress: ProgressCb) -> None:
    s = get_settings()
    base = [s.ffmpeg_path, "-hide_banner", "-nostdin", "-nostats", "-loglevel", "error", "-y",
            "-threads", "2", *SAFE_INPUT, "-i", _check_path(src, root)]
    if operation == "remux_mp4":
        args = ["-map", "0:v?", "-map", "0:a?", "-c", "copy", "-movflags", "+faststart", "-f", "mp4"]
    elif operation == "extract_m4a":
        if audio_codec is None:
            raise FFmpegError("this media has no audio track")
        codec = ["-c:a", "copy"] if audio_codec == "aac" else ["-c:a", "aac", "-b:a", "192k"]
        args = ["-vn", "-map", "0:a:0", *codec, "-movflags", "+faststart", "-f", "ipod"]
    else:
        raise FFmpegError("unsupported operation")
    argv = [*base, *args, "-progress", "pipe:1", _check_path(dst, root)]

    async def on_line(line: str) -> bool:
        if line.startswith("out_time_us=") and duration:
            try:
                return await on_progress(min(1.0, int(line.split("=", 1)[1]) / 1e6 / duration))
            except ValueError:
                return True
        return True

    code, _, err = await _run(argv, s.ffmpeg_timeout_seconds, on_line)
    if code != 0 or not dst.exists() or dst.stat().st_size == 0:
        raise FFmpegError("conversion failed")
