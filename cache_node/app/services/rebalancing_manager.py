import asyncio
import logging
import uuid
from datetime import datetime, UTC
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RebalancingJob:
    """Represents a single rebalancing job."""

    def __init__(self, job_id: str, operation_type: str):
        self.job_id = job_id
        self.operation_type = operation_type  # "join", "leave", "manual"
        self.status = "pending"  # pending, in_progress, completed, failed
        self.created_at = datetime.now(UTC)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.total_keys = 0
        self.keys_moved = 0
        self.keys_failed = 0
        self.affected_nodes = []

    def start(self) -> None:
        """Mark job as started."""
        self.status = "in_progress"
        self.started_at = datetime.now(UTC)

    def complete(self) -> None:
        """Mark job as completed."""
        self.status = "completed"
        self.completed_at = datetime.now(UTC)

    def fail(self) -> None:
        """Mark job as failed."""
        self.status = "failed"
        self.completed_at = datetime.now(UTC)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "operation_type": self.operation_type,
            "status": self.status,
            "total_keys": self.total_keys,
            "keys_moved": self.keys_moved,
            "keys_failed": self.keys_failed,
            "progress_percent": int((self.keys_moved / self.total_keys * 100))
            if self.total_keys > 0
            else 0,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
        }


class RebalancingManager:
    """
    Manages data rebalancing when nodes join/leave the cluster.
    """

    def __init__(self):
        self.jobs: Dict[str, RebalancingJob] = {}
        self.active_job: Optional[str] = None

    def create_job(self, operation_type: str, affected_nodes: List[str]) -> str:
        """Create a new rebalancing job."""
        job_id = str(uuid.uuid4())
        job = RebalancingJob(job_id, operation_type)
        job.affected_nodes = affected_nodes
        self.jobs[job_id] = job
        logger.info(f"Created rebalancing job {job_id} for {operation_type}")
        return job_id

    def start_job(self, job_id: str) -> bool:
        """Start a rebalancing job."""
        if job_id not in self.jobs:
            return False

        if self.active_job is not None and self.active_job != job_id:
            logger.warning(f"Another job {self.active_job} is already running")
            return False

        job = self.jobs[job_id]
        job.start()
        self.active_job = job_id
        logger.info(f"Started rebalancing job {job_id}")
        return True

    def complete_job(self, job_id: str) -> bool:
        """Mark a job as completed."""
        if job_id not in self.jobs:
            return False

        job = self.jobs[job_id]
        job.complete()
        
        if self.active_job == job_id:
            self.active_job = None
        
        logger.info(f"Completed rebalancing job {job_id}")
        return True

    def fail_job(self, job_id: str) -> bool:
        """Mark a job as failed."""
        if job_id not in self.jobs:
            return False

        job = self.jobs[job_id]
        job.fail()
        
        if self.active_job == job_id:
            self.active_job = None
        
        logger.error(f"Failed rebalancing job {job_id}")
        return True

    def update_progress(self, job_id: str, keys_moved: int, keys_failed: int = 0) -> None:
        """Update progress on a job."""
        if job_id not in self.jobs:
            return

        job = self.jobs[job_id]
        job.keys_moved = keys_moved
        job.keys_failed = keys_failed

    def set_total_keys(self, job_id: str, total: int) -> None:
        """Set total number of keys to move."""
        if job_id not in self.jobs:
            return

        self.jobs[job_id].total_keys = total

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Get the status of a job."""
        if job_id not in self.jobs:
            return None

        return self.jobs[job_id].to_dict()

    def get_all_jobs(self) -> List[dict]:
        """Get status of all jobs."""
        return [job.to_dict() for job in self.jobs.values()]

    def has_active_job(self) -> bool:
        """Check if there's an active rebalancing job."""
        return self.active_job is not None

    def get_active_job_id(self) -> Optional[str]:
        """Get the ID of the active job."""
        return self.active_job
