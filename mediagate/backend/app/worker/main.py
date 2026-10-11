"""Worker entrypoint: `python -m app.worker.main`.

Claims queued jobs with FOR UPDATE SKIP LOCKED (safe with many workers), wakes on
pg NOTIFY with a polling fallback, and runs cleanup every minute.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket

from aiohttp import web  # tiny health endpoint

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services import db, jobs
from app.worker import cleanup
from app.worker.processor import process

log = logging.getLogger("mediagate.worker")
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"


class Worker:
    def __init__(self) -> None:
        self.sem = asyncio.Semaphore(get_settings().worker_concurrency)
        self.wake = asyncio.Event()
        self.stopping = asyncio.Event()
        self.tasks: set[asyncio.Task] = set()
        self.last_loop = 0.0

    async def listen(self) -> None:
        conn = await db.pool().acquire()
        try:
            await conn.add_listener("mediagate_jobs", lambda *_: self.wake.set())
            await self.stopping.wait()
        finally:
            await db.pool().release(conn)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        while not self.stopping.is_set():
            self.last_loop = loop.time()
            await self.sem.acquire()
            try:
                job = await jobs.claim_next(WORKER_ID)
            except Exception:  # noqa: BLE001
                log.exception("claim_failed")
                job = None
            if job is None:
                self.sem.release()
                self.wake.clear()
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
                continue
            t = asyncio.create_task(self._run_job(job))
            self.tasks.add(t)
            t.add_done_callback(self.tasks.discard)

    async def _run_job(self, job) -> None:
        try:
            await process(job)
        finally:
            self.sem.release()

    async def cleanup_loop(self) -> None:
        while not self.stopping.is_set():
            try:
                await cleanup.run_once()
            except Exception:  # noqa: BLE001
                log.exception("cleanup_failed")
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass


async def health_server(worker: Worker) -> web.AppRunner:
    async def health(_: web.Request) -> web.Response:
        loop = asyncio.get_running_loop()
        ok = loop.time() - worker.last_loop < 30
        return web.json_response({"status": "ok" if ok else "stalled", "active": len(worker.tasks)},
                                 status=200 if ok else 503)
    app = web.Application()
    app.router.add_get("/healthz", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("WORKER_HEALTH_PORT", "8081"))).start()
    return runner


async def main() -> None:
    configure_logging()
    await db.init_pool(min_size=2, max_size=get_settings().worker_concurrency + 3)
    w = Worker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, w.stopping.set)
    runner = await health_server(w)
    log.info("worker_started", extra={"status": WORKER_ID})
    bg = [asyncio.create_task(w.listen()), asyncio.create_task(w.cleanup_loop())]
    runner_task = asyncio.create_task(w.run())
    await w.stopping.wait()
    runner_task.cancel()
    # Let in-flight jobs finish (up to 60s); stale-job recovery requeues anything cut off.
    if w.tasks:
        await asyncio.wait(w.tasks, timeout=60)
    for t in bg:
        t.cancel()
    await runner.cleanup()
    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
