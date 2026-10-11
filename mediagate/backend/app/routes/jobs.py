from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.core.auth import CurrentUser, require_user
from app.core.ratelimit import rate_limit
from app.models.schemas import CreateJobRequest, DownloadLinkResponse, JobResponse
from app.services import jobs

router = APIRouter(prefix="/api", tags=["jobs"])


@router.post("/jobs", response_model=JobResponse, status_code=202,
             summary="Create a processing job for an authorized download")
@router.post("/download", response_model=JobResponse, status_code=202, include_in_schema=True,
             summary="Alias of POST /api/jobs")
async def create_job(body: CreateJobRequest, user: CurrentUser = Depends(require_user),
                     _: None = Depends(rate_limit("jobs", "rate_limit_jobs_per_min"))) -> JobResponse:
    return await jobs.create_job(user, body.url, body.format_id)


@router.get("/jobs", response_model=list[JobResponse], summary="Your recent jobs")
async def list_jobs(user: CurrentUser = Depends(require_user)) -> list[JobResponse]:
    return await jobs.list_jobs(user)


@router.get("/jobs/{job_id}", response_model=JobResponse, summary="Job status and progress")
async def get_job(job_id: UUID, user: CurrentUser = Depends(require_user)) -> JobResponse:
    return await jobs.get_job(user, job_id)


@router.delete("/jobs/{job_id}", status_code=204, response_class=Response, summary="Cancel a job and delete its files")
async def delete_job(job_id: UUID, user: CurrentUser = Depends(require_user)) -> Response:
    await jobs.cancel_or_delete(user, job_id)
    return Response(status_code=204)


@router.get("/downloads/{download_id}", response_model=DownloadLinkResponse,
            summary="Mint a short-lived signed link for a completed download")
async def get_download(download_id: UUID, response: Response,
                       user: CurrentUser = Depends(require_user)) -> DownloadLinkResponse:
    response.headers["Cache-Control"] = "no-store"
    return await jobs.download_link(user, download_id)
