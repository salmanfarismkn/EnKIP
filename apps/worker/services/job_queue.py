from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.models import IngestionJob, IngestionStatus
from sqlalchemy import or_, update


logger = logging.getLogger(__name__)



class JobQueue:
    def claim_next(self, db: Session) -> UUID | None:
        now = datetime.now(timezone.utc)

        stmt = (
            select(IngestionJob)
            .where(
                IngestionJob.status == IngestionStatus.PENDING
            )
            .order_by(IngestionJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )

        job = db.scalars(stmt).first()

        if job is None:
            return None

        job.status = IngestionStatus.PROCESSING
        job.attempt_count += 1
        job.claimed_at = now

        db.commit()
        return job.id

    def recover_stale_jobs(
        self,
        db: Session,
        stale_after_minutes: int = 15,
    ) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=stale_after_minutes
        )

        stmt = (
            update(IngestionJob)
            .where(
                IngestionJob.status == IngestionStatus.PROCESSING
            )
            .where(
                or_(
                    IngestionJob.claimed_at.is_(None),
                    IngestionJob.claimed_at < cutoff,
                )
            )
            .values(
                status=IngestionStatus.PENDING,
                claimed_at=None,
                last_error=(
                    "stale_claim_recovered:"
                    f"{stale_after_minutes}_minutes"
                ),
            )
        )

        result = db.execute(stmt)
        if result.rowcount:
            logger.warning(
                "Recovered %d stale ingestion jobs after %d minutes; "
                "reset_to_pending",
                result.rowcount,
                stale_after_minutes,
                extra={
                    "event": "ingestion_stale_recovery",
                    "recovered_count": result.rowcount,
                    "stale_after_minutes": stale_after_minutes,
                    "action": "reset_to_pending",
                },
            )
        db.commit()

        return result.rowcount or 0