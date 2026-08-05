"""Voice call enums."""

from enum import Enum


class VoiceCallStatus(str, Enum):
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    FAILED = "failed"
    NO_ANSWER = "no_answer"


class VoiceTurnRole(str, Enum):
    CALLER = "caller"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class VoiceStreamEventType(str, Enum):
    START = "start"
    MEDIA = "media"
    STOP = "stop"
    MARK = "mark"
    INTERRUPT = "interrupt"
