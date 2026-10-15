from fastapi import APIRouter, Depends, HTTPException, Query

from yuxi.api.dependencies.auth import get_admin_user
from yuxi.modules.background_jobs.service import job_tracker
from yuxi.modules.identity.models import User

background_jobs = APIRouter(prefix="/background-jobs", tags=["background-jobs"])


@background_jobs.get("")
async def list_jobs(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
    current_user: User = Depends(get_admin_user),
):
    """按状态查询后台作业。"""
    return await job_tracker.list_jobs(status=status, limit=limit)


@background_jobs.get("/{job_id}")
async def get_job(job_id: str, current_user: User = Depends(get_admin_user)):
    """读取单项后台作业摘要。"""
    job = await job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="BackgroundJob not found")
    return {"job": job}


@background_jobs.post("/{job_id}/cancel")
async def cancel_job(job_id: str, current_user: User = Depends(get_admin_user)):
    """登记后台作业取消请求。"""
    job = await job_tracker.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=400, detail="BackgroundJob cannot be cancelled")
    return {
        "job_id": job_id,
        "status": job.status,
        "cancel_requested": bool(job.cancel_requested),
    }


@background_jobs.delete("/{job_id}")
async def delete_job(job_id: str, current_user: User = Depends(get_admin_user)):
    """删除已经终态的后台作业。"""
    success = await job_tracker.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=409, detail="BackgroundJob must exist and be terminal before deletion")
    return {"job_id": job_id, "status": "deleted"}
