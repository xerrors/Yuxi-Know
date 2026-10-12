"""与主生命周期同事务写入的协作通知。"""

from sqlalchemy import select
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.repositories.cooperation import CooperationRepository


async def notify_turn_state(db, run: AgentRun) -> None:
    """与 Turn 状态同事务发布可补读的通知；完成通知不创建 Input。"""
    sender = await db.get(Session, run.session_record_id)
    turn = await db.get(AgentTurn, run.turn_id)
    if sender is None or turn is None:
        raise ValueError("协作通知缺少会话或轮次")
    recipients = [sender]
    if sender.parent_thread_id:
        parent = await db.scalar(select(Session).where(Session.thread_id == sender.parent_thread_id))
        recipients.append(parent)
    for recipient in recipients:
        await CooperationRepository(db).append(
            sender=sender,
            recipient=recipient,
            key=f"turn:{run.id}:{turn.status}",
            kind="turn_status",
            run_id=run.id,
            turn_id=turn.id,
            payload={
                "status": turn.status,
                "result_run_id": turn.result_run_id,
                "waiting_for": (turn.waitpoint or {}).get("kind"),
            },
        )


async def notify_user_intervention(db, member: Session, *, key: str, action: str) -> None:
    """用户直接操作成员时告知父会话，不创建父工作。"""
    if member.parent_thread_id is None:
        return
    parent = await db.scalar(select(Session).where(Session.thread_id == member.parent_thread_id))
    await CooperationRepository(db).append(
        sender=member,
        recipient=parent,
        key=f"user:{key}",
        kind="user_intervention",
        payload={"action": action},
    )
