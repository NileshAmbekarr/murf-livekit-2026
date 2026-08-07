"""Curated public-health reference data for Sehat Sathi.

Everything in this module is *general public information* about Indian public
health services — helpline numbers and scheme names that a community health
worker would hand out. None of it is medical advice, and none of it is
personalised to a caller.

Design rule for this file: prefer facts that are stable and verifiable over
specifics that drift year to year. Where an amount or eligibility rule changes
between states or budget cycles, we describe the benefit qualitatively and tell
the caller to confirm locally. A voice agent that says "ask your ASHA didi to
confirm the current amount" is more useful than one that confidently states a
stale rupee figure.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Helpline:
    """A nationally recognised health helpline number."""

    number: str
    name: str
    detail: str
    keywords: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Scheme:
    """A government health scheme a caller may be entitled to."""

    name: str
    summary: str
    where: str
    keywords: tuple[str, ...] = field(default_factory=tuple)


# --- Emergency numbers -------------------------------------------------------
# These are the two numbers the agent should be able to produce without any
# lookup, in any conversation, in any language.
EMERGENCY_AMBULANCE = "108"
NATIONAL_EMERGENCY = "112"


HELPLINES: tuple[Helpline, ...] = (
    Helpline(
        number="112",
        name="National emergency number",
        detail="Single number for police, fire and medical emergencies across India.",
        keywords=("emergency", "police", "fire", "urgent", "accident"),
    ),
    Helpline(
        number="108",
        name="Emergency ambulance",
        detail="Free emergency ambulance service in most states.",
        keywords=("ambulance", "emergency", "accident", "chest pain", "unconscious"),
    ),
    Helpline(
        number="102",
        name="Ambulance for pregnant women and infants",
        detail=(
            "Free transport for pregnant women and sick infants to and from a "
            "government facility in most states."
        ),
        keywords=("pregnancy", "pregnant", "delivery", "newborn", "infant", "baby"),
    ),
    Helpline(
        number="104",
        name="State health advice helpline",
        detail=(
            "Free health advice and counselling line run by many state health "
            "departments."
        ),
        keywords=("advice", "counselling", "information", "doctor on phone"),
    ),
    Helpline(
        number="1075",
        name="National health helpline",
        detail="Central health helpline for general public health queries.",
        keywords=("national", "helpline", "general", "information"),
    ),
    Helpline(
        number="14416",
        name="Tele-MANAS mental health helpline",
        detail=(
            "Free, confidential mental health support in many Indian languages, "
            "24 hours a day. Also reachable on 1-800-891-4416."
        ),
        keywords=(
            "mental",
            "depression",
            "depressed",
            "anxiety",
            "stress",
            "suicide",
            "suicidal",
            "sad",
            "tension",
            "lonely",
            "hopeless",
        ),
    ),
    Helpline(
        number="14555",
        name="Ayushman Bharat PM-JAY helpline",
        detail="Questions about PM-JAY eligibility, cards and empanelled hospitals.",
        keywords=(
            "ayushman",
            "pmjay",
            "insurance",
            "card",
            "hospital",
            "money",
            "afford",
            "cost",
            "expensive",
            "operation",
            "surgery",
            "admitted",
        ),
    ),
    Helpline(
        number="1098",
        name="Childline",
        detail="Emergency help for children in distress or in need of care.",
        # Deliberately narrow: a routine question about a child's health should
        # reach a PHC, not a child-protection emergency line.
        keywords=("child abuse", "child labour", "runaway", "abuse", "neglect"),
    ),
    Helpline(
        number="181",
        name="Women's helpline",
        detail="Support for women facing violence or in distress.",
        keywords=("women", "violence", "domestic", "abuse", "mahila"),
    ),
)


SCHEMES: tuple[Scheme, ...] = (
    Scheme(
        name="Ayushman Bharat PM-JAY",
        summary=(
            "Health cover of up to five lakh rupees per eligible family per year "
            "for hospital treatment, cashless at empanelled hospitals."
        ),
        where=(
            "Check eligibility and find empanelled hospitals by calling 14555, or "
            "ask at your nearest Common Service Centre or government hospital."
        ),
        keywords=(
            "ayushman",
            "pmjay",
            "insurance",
            "hospital",
            "surgery",
            "operation",
            "cost",
            "money",
            "afford",
        ),
    ),
    Scheme(
        name="Ayushman Arogya Mandir",
        summary=(
            "Upgraded primary health centres offering free basic care, and "
            "screening for blood pressure, diabetes and common cancers."
        ),
        where="Your nearest sub-centre or primary health centre (PHC).",
        keywords=(
            "checkup",
            "screening",
            "bp",
            "blood pressure",
            "diabetes",
            "sugar",
            "cancer",
            "phc",
            "primary",
        ),
    ),
    Scheme(
        name="Janani Suraksha Yojana (JSY)",
        summary=(
            "Cash assistance for eligible mothers who deliver in a government or "
            "accredited health facility, paid along with support from an ASHA worker."
        ),
        where="Register with your ASHA worker or at your nearest PHC during pregnancy.",
        keywords=("pregnancy", "pregnant", "delivery", "mother", "janani", "garbh"),
    ),
    Scheme(
        name="Janani Shishu Suraksha Karyakram (JSSK)",
        summary=(
            "Free delivery including caesarean, free medicines, diagnostics, diet "
            "and transport for pregnant women and sick newborns at public facilities."
        ),
        where="Any government hospital or PHC.",
        keywords=("delivery", "caesarean", "newborn", "infant", "free", "transport"),
    ),
    Scheme(
        name="Universal Immunisation Programme / Mission Indradhanush",
        summary=(
            "Free routine vaccination for children and pregnant women against "
            "several preventable diseases."
        ),
        where=(
            "Village Health and Nutrition Day sessions, anganwadi centres, or your "
            "nearest PHC. Your ASHA worker keeps the schedule."
        ),
        keywords=(
            "vaccine",
            "vaccination",
            "immunisation",
            "immunization",
            "tika",
            "child",
            "baby",
        ),
    ),
    Scheme(
        name="National TB Elimination Programme",
        summary=(
            "Free TB testing and full treatment at government facilities, plus "
            "monthly nutrition support for people on TB treatment under Ni-kshay "
            "Poshan Yojana."
        ),
        where="Any government hospital, PHC or designated microscopy centre.",
        keywords=(
            "tb",
            "tuberculosis",
            "cough",
            "khansi",
            "weight loss",
            "night sweats",
        ),
    ),
)


# --- Red flags ---------------------------------------------------------------
# Plain-language danger signs. This list exists so that escalation is driven by
# a fixed, reviewable rule set rather than left entirely to the model's judgement.
RED_FLAG_SIGNS: tuple[str, ...] = (
    "chest pain, pressure or tightness",
    "difficulty breathing or breathlessness at rest",
    "sudden weakness, numbness, drooping face or slurred speech",
    "fainting, unconsciousness or a fit/seizure",
    "bleeding that will not stop, or vomiting blood",
    "a severe injury, burn, fall or road accident",
    "severe abdominal pain",
    "high fever in a newborn, or a baby who will not feed",
    "any bleeding, severe pain or reduced baby movement during pregnancy",
    "thoughts of harming yourself or ending your life",
)


# Phrases that mean a caller is describing a danger sign right now, in the
# romanised Hindi and English people actually speak into a phone.
#
# This exists because "the model will notice" is not a guarantee. A confused or
# rambling caller can bury "seene mein dard" in the middle of a story about
# their nephew's wedding, and a small fast model may keep chatting. Matching
# these phrases lets us force the escalation path open regardless.
#
# Phrases only, never bare words: "dard" and "fit" on their own would fire on
# half of all normal conversation. Precision matters more than recall here,
# because the model's own judgement is still the second line of defence.
RED_FLAG_PHRASES: tuple[tuple[str, str], ...] = (
    # Cardiac / respiratory
    ("chest pain", "chest pain"),
    ("pain in my chest", "chest pain"),
    ("pain in his chest", "chest pain"),
    ("pain in her chest", "chest pain"),
    ("chest is tight", "chest tightness"),
    ("tightness in my chest", "chest tightness"),
    ("seene mein dard", "chest pain"),
    ("seene me dard", "chest pain"),
    ("chhaati mein dard", "chest pain"),
    ("chaati mein dard", "chest pain"),
    ("cannot breathe", "breathlessness"),
    ("can't breathe", "breathlessness"),
    ("cant breathe", "breathlessness"),
    ("trouble breathing", "breathlessness"),
    ("difficulty breathing", "breathlessness"),
    ("shortness of breath", "breathlessness"),
    ("saans nahi aa", "breathlessness"),
    ("saans nahin aa", "breathlessness"),
    ("saans phool", "breathlessness"),
    ("dam ghut", "breathlessness"),
    # Neurological
    ("slurred speech", "stroke signs"),
    ("face is drooping", "stroke signs"),
    ("face drooping", "stroke signs"),
    ("one side is numb", "stroke signs"),
    ("cannot move one side", "stroke signs"),
    ("muh tedha", "stroke signs"),
    ("bolne mein dikkat", "stroke signs"),
    ("unconscious", "unconsciousness"),
    ("passed out", "unconsciousness"),
    ("fainted", "unconsciousness"),
    ("behosh", "unconsciousness"),
    ("seizure", "seizure"),
    ("convulsion", "seizure"),
    ("fit aa raha", "seizure"),
    ("fits aa rahe", "seizure"),
    ("daura pad", "seizure"),
    ("mirgi", "seizure"),
    # Bleeding
    ("bleeding heavily", "uncontrolled bleeding"),
    ("won't stop bleeding", "uncontrolled bleeding"),
    ("wont stop bleeding", "uncontrolled bleeding"),
    ("will not stop bleeding", "uncontrolled bleeding"),
    ("vomiting blood", "vomiting blood"),
    ("coughing up blood", "coughing blood"),
    ("khoon nahi ruk", "uncontrolled bleeding"),
    ("khoon band nahi", "uncontrolled bleeding"),
    ("ulti mein khoon", "vomiting blood"),
    ("khoon ki ulti", "vomiting blood"),
    # Maternal & newborn
    ("bleeding during pregnancy", "bleeding in pregnancy"),
    ("baby is not moving", "reduced fetal movement"),
    ("baby not moving", "reduced fetal movement"),
    ("bachcha hil nahi", "reduced fetal movement"),
    ("baby will not feed", "newborn not feeding"),
    ("baby won't feed", "newborn not feeding"),
    ("baby wont feed", "newborn not feeding"),
    ("baby is not feeding", "newborn not feeding"),
    ("baby not feeding", "newborn not feeding"),
    ("doodh nahi pi", "newborn not feeding"),
    # Self-harm
    ("kill myself", "self-harm"),
    ("end my life", "self-harm"),
    ("harm myself", "self-harm"),
    ("hurt myself", "self-harm"),
    ("suicide", "self-harm"),
    ("suicidal", "self-harm"),
    ("marna chahta", "self-harm"),
    ("marna chahti", "self-harm"),
    ("jaan dena", "self-harm"),
    ("jeena nahi chahta", "self-harm"),
    ("khud ko nuksan", "self-harm"),
)

# Signs that mean the caller is pregnant or handling a newborn, so escalation
# can also offer the 102 maternal ambulance.
_MATERNAL_HINTS: tuple[str, ...] = (
    "pregnan",
    "pregnancy",
    "garbh",
    "expecting",
    "newborn",
    "new born",
    "baby",
    "bachcha",
    "bachche",
    "infant",
    "delivery",
    "labour",
    "labor",
)


# Bleeding on its own is not an emergency — a cut finger is bleeding. Bleeding
# *during a pregnancy* always is, so those two facts are combined rather than
# either one firing alone.
_BLEEDING_TERMS: tuple[str, ...] = (
    "bleeding",
    "blood aa",
    "khoon aa",
    "khoon ja",
    "khoon beh",
    "spotting",
    "rakt",
)


def detect_red_flags(text: str) -> list[str]:
    """Return the distinct danger signs mentioned in `text`, if any.

    Used to force the escalation path open on the user's turn, before the model
    gets a chance to keep chatting.
    """
    haystack = " ".join((text or "").lower().split())
    found: list[str] = []

    for phrase, label in RED_FLAG_PHRASES:
        if phrase in haystack and label not in found:
            found.append(label)

    # Compound rule: bleeding + a pregnancy or newborn in the same breath.
    if (
        "bleeding in pregnancy" not in found
        and mentions_maternal_context(haystack)
        and any(term in haystack for term in _BLEEDING_TERMS)
    ):
        found.append("bleeding in pregnancy")

    return found


def mentions_maternal_context(text: str) -> bool:
    """True if the caller appears to be pregnant or talking about a newborn."""
    haystack = " ".join((text or "").lower().split())
    return any(hint in haystack for hint in _MATERNAL_HINTS)


def find_helplines(topic: str, limit: int = 3) -> list[Helpline]:
    """Return helplines whose name or keywords match `topic`, best match first."""
    return _rank(topic, HELPLINES, limit, lambda h: (h.name, h.detail, h.keywords))


def find_schemes(topic: str, limit: int = 2) -> list[Scheme]:
    """Return schemes whose name or keywords match `topic`, best match first."""
    return _rank(topic, SCHEMES, limit, lambda s: (s.name, s.summary, s.keywords))


# Callers speak, so the transcript carries whatever inflection they used —
# "depressed" for "depression", "children" for "child". Matching on a shared
# prefix catches those without pulling in a stemming dependency.
_STEM_PREFIX = 5


def _rank(topic, items, limit, fields):
    """Score items by keyword overlap with `topic` and return the top `limit`."""
    query = (topic or "").lower()
    words = {w for w in _tokenise(query) if len(w) > 2}

    scored = []
    for item in items:
        name, detail, keywords = fields(item)
        score = 0
        for keyword in keywords:
            # Multi-word keywords ("chest pain") only count as a phrase match.
            if " " in keyword:
                if keyword in query:
                    score += 3
            elif any(_stem_match(word, keyword) for word in words):
                score += 2
        if name.lower() in query:
            score += 5
        # Description overlap only breaks ties between entries that already
        # matched on a keyword. On its own it is too loose — "child vaccination"
        # would otherwise reach the child-protection line via the word "children".
        if score:
            score += sum(
                1
                for word in words
                if any(_stem_match(word, d) for d in _tokenise(detail.lower()))
            )
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]


def _stem_match(word: str, keyword: str) -> bool:
    """True if `word` and `keyword` are the same word or share a long prefix."""
    if word == keyword:
        return True
    if len(word) < _STEM_PREFIX or len(keyword) < _STEM_PREFIX:
        return False
    shortest = min(len(word), len(keyword))
    common = 0
    while common < shortest and word[common] == keyword[common]:
        common += 1
    return common >= _STEM_PREFIX


def _tokenise(text: str) -> set[str]:
    return {"".join(c for c in word if c.isalnum()) for word in text.split()}
