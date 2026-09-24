from dataclasses import dataclass, field

MAX_HISTORY_MESSAGES = 20  


@dataclass
class Session:
    messages: list = field(default_factory=list)
    itinerary: dict | None = None


SESSIONS = {}


def get_session(session_id):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = Session()
    return SESSIONS[session_id]


def trim_history(messages):
    return messages[-MAX_HISTORY_MESSAGES:]