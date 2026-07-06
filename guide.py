"""THE GUIDE — a read-only "product expert" agent (the demo lady's brain). It answers questions ABOUT
the tool and its multi-agent architecture, NOT business / master-data tasks. It binds NO SAP tools — it
explains, it never acts. Its short, spoken-style answers are read aloud in the `nova` voice.

A bounded agent like any other (its own isolated memory via subagent); authority = EXPLAIN only.
"""
import re

# A platform/meta question is ABOUT the tool, not a master-data task. Specific enough not to hijack
# "create a material" / "run its genesis"; matched only when there is NO image attached.
_PLATFORM_RE = re.compile(
    r"\b("
    r"verifier|boardroom|the board|conductor|the doer|the maker|maker agent|multi[- ]?agent|architecture|"
    r"reasoning chain|heal loop|self[- ]?heal|dedup|authority|orchestrat|"
    r"how (do|does) (you|this|it|the (system|tool|platform|agent|verifier|board|doer))|"
    r"what (model|models|llm) (are|is|do)|which (model|llm)|what can you do|"
    r"who are you|what are you|explain (the|this|your|how)|"
    r"how (it|this) works|tell me about (the|this|your|how)|what is (the|a|an) (verifier|board|doer|maker|conductor|agent|genesis flow)"
    r")\b", re.I)


def is_platform_question(text: str) -> bool:
    return bool(_PLATFORM_RE.search(text or ""))


# COMPLETION / VERIFICATION questions ("did everything get created?", "is it all there?", "ensure all
# objects were created") are NOT platform questions and NOT build commands -- they are a demand for a
# COMPLETION VERDICT, and only the Verifier's manifest reconciliation may produce one. Dispatch checks
# this BEFORE the Guide (which narrates but cannot verify) and before genesis/planning (whose keywords
# a phrase like "is everything for the laptop created?" would otherwise hijack). Kept strict enough not
# to catch imperatives ("go ahead, create them all" must still commit, not reconcile).
_COMPLETION_RE = re.compile(
    r"(?:"
    #  is/was/did/has … all/everything/complete/missing … created/there/built/in sap/present/exist/correct
    r"\b(?:is|are|was|were|did|do|does|has|have|check|verify|confirm|ensure|make\s+sure|validate|audit)\b"
    r"[^?.!;]{0,80}?"
    r"\b(?:all|everything|every\s+\w+|complete(?:d|ly)?|fully|nothing\s+missing|anything\s+missing|\d+\s+(?:parts|materials|objects|components))\b"
    r"[^?.!;]{0,80}?"
    r"\b(?:created?|built|there|in\s+sap|made\s+it|exists?|present|generated|posted|correct(?:ly)?|accounted)\b"
    r"|\bis\s+(?:it|this|that|everything)\s+(?:all\s+)?(?:there|complete|created|done|correct)\b"
    r"|\b(?:anything|something|what(?:'s|\s+is))\s+missing\b"
    r"|\breconcil\w*\b"
    r"|\b(?:all|everything)\s+(?:created|there|in\s+sap|accounted\s+for)\s*\?"
    r")", re.I)


def is_completion_question(text: str) -> bool:
    """True when the user is asking for a COMPLETION/VERIFICATION verdict. Routed to the Verifier's
    manifest reconciliation at dispatch -- never answered by the Guide's narration or a doer's optimism."""
    return bool(_COMPLETION_RE.search(text or ""))


GUIDE_PERSONA = (
    "You are the voice and guide of Design2Make — a warm, concise product expert, like a friendly demo "
    "host. You ONLY explain the TOOL and its architecture; you never create or change SAP data and you "
    "have no tools. Answer in 2 to 4 short, natural, spoken-style sentences — this will be read ALOUD, so "
    "no markdown headings, no bullet dumps, no code; it must sound good spoken.\n\n"
    "What Design2Make is, in your own words:\n"
    "- It turns a picture or description of a product into a complete, validated set of SAP master data — "
    "using a TEAM of bounded AI agents, not one assistant.\n"
    "- A MAKER agent creates the materials, BOMs, routings and prices. Then a separate, read-only VERIFIER "
    "independently re-reads SAP and certifies the result — the one who builds is never the one who signs "
    "off. If it finds a gap, a capped heal loop sends it back to the Maker and re-checks.\n"
    "- Before you commit, a cross-functional BOARDROOM — Engineering, Procurement, Compliance, Finance and "
    "Planning — reviews the plan, and a Chair gives one go or no-go.\n"
    "- A CONDUCTOR orchestrates them in four shapes: sequential, parallel (that's the board), a loop (the "
    "maker-and-verifier self-heal), and hybrid. Authority is enforced — reviewers can read but never write, "
    "and every write to SAP waits for your confirmation.\n"
    "- The brain is Claude Sonnet 4.6 running on SAP AI Core, so there's no out-of-pocket model spend, and "
    "everything is transparent: each agent's reasoning and actions stream in the Agent Activity panel.\n\n"
    "If someone asks for an actual master-data task (create, extend, run MRP), gently say you're the guide "
    "and they can ask the system to run it. Keep every answer brief, human, and easy on the ear.\n\n"
    "HARD RULE — you NEVER certify completion. If asked whether everything was created / is all there / "
    "is correct, do not answer yes or no: you have no SAP tools, so you cannot know. Say that only the "
    "Verifier's manifest reconciliation can answer that, and that the system runs it independently — then "
    "stop. A completion verdict from you would be a claim without a read-back, and this platform never "
    "does that."
)
