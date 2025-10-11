from fastapi import APIRouter, Depends, HTTPException, Query

from src.storage.db.models import User
from server.services.tasker import tasker
from server.utils.auth_middleware import get_admin_user

tasks = APIRouter(prefix="/tasks", tags=["tasks"])


@tasks.get("")
async def list_tasks(
    status: str | None = Query(default=None),
    current_user: User = Depends(get_admin_user),
):
    """List tasks, optionally filtered by status."""
    task_list = await tasker.list_tasks(status=status)
    return {"tasks": task_list}


@tasks.get("/{task_id}")
async def get_task(task_id: str, current_user: User = Depends(get_admin_user)):
    """Retrieve a single task by id."""
    task = await tasker.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task}


@tasks.post("/{task_id}/cancel")
async def cancel_task(task_id: str, current_user: User = Depends(get_admin_user)):
    """Request cancellation of a task."""
    success = await tasker.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Task cannot be cancelled")
    return {"task_id": task_id, "status": "cancelled"}
