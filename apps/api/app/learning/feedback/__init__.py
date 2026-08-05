"""Learning feedback adapters."""

from app.learning.feedback.customer import CustomerFeedbackService
from app.learning.feedback.staff import StaffFeedbackService
from app.learning.feedback.workflow import WorkflowFeedbackService

__all__ = [
    "CustomerFeedbackService",
    "StaffFeedbackService",
    "WorkflowFeedbackService",
]
