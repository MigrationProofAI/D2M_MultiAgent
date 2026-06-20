"""Step 5 -- the learning loop wired into the hand-rolled spine. `learning.py` is the engine (capture /
store / recall / promote), ported from D2M with the fixes already in it: a widened correction trigger,
intent-scoped recall behind a similarity floor, and human-gated promotion. This is the thin
integration: recall + INJECT with a request-level marker, plus capture / reflect / promotion hooks."""
import learning

learning.ENABLED = True                       # the rig always learns
LESSON_MARKER = "LESSONS (past sessions)"     # the unique substring that proves injection landed


def recall_and_inject(intent: str, user_text: str, system: str):
    """Recall intent-scoped lessons and inject the LESSONS block into the system instruction. Returns
    (system_with_lessons, injected, lessons). `injected` is the REQUEST-LEVEL assertion: the marker is
    actually present in the outgoing system instruction (the board-amnesia failure must not recur)."""
    lessons = learning.recall(intent, user_text)
    block = learning.format_block(lessons)
    new_system = (system + block) if block else system
    injected = bool(lessons) and (LESSON_MARKER in new_system)
    return new_system, injected, lessons


def capture_correction(intent: str, user_text: str, prev_answer: str):
    """Capture a user correction ('no/wrong/should be' + an entity) as a lesson + queue its promotion."""
    return learning.capture_correction(intent, user_text, prev_answer)


def reflect(intent: str, steps, trigger: str = "reflect"):
    return learning.reflect(intent, steps, trigger)


def promotions():
    return learning.list_promotions()
