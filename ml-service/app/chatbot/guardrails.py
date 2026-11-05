"""Replies decided in code, before any model runs.

Requests for secrets, system details or other users' data get a clear refusal here, so a clever
prompt can't talk a model into anything. Small talk gets a friendly fixed reply, which also saves
the free Groq quota. Questions about how to use the app ("how do I reset my password?", "can other
users see my expenses?") deliberately don't match, and go to the articles.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}"
_PASSWORD = re.compile(
    r"\b(tell|show|give|send|reveal|share|what(?:'s| is| was)|whats)\b.{0,25}\b(password|otp|pin)\b"
    r"|\bmy (password|otp|pin) is what\b"
)
_SYSTEM = re.compile(
    r"\b(database|db)\b.{0,15}\b(name|password|schema|url|host|tables?)\b"
    r"|\b(name|schema|tables?) of (your|the) (database|db)\b"
    r"|\byour (database|db|server|backend|source code|code|system prompt|prompt|instructions)\b"
    r"|\b(system prompt|api key|secret key|service role|access token|env(ironment)? variables?)\b"
)
_OTHER_USERS = re.compile(
    r"\bhow many (users|customers|people|accounts)\b"
    r"|\b(show|give|tell|list|get|see)\b.{0,30}\b(another|other|all|every)\b.{0,10}\b(users?|customers?|accounts?)\b"
    rf"|\buser\b.{{0,6}}{_UUID}"
)
_CREATOR = re.compile(
    r"\bwho (made|created|built|developed|designed|owns) (you|this|the (app|chatbot|bot))\b"
    r"|\byour (creator|developer|maker|owner)\b|\bwho is ketul( mehta)?\b"
)
_IDENTITY = re.compile(
    r"\b(your name|who are (you|u)|what are you|are (you|u) (a |an )?(bot|robot|human|ai|real|person))\b"
)
_CAPABILITIES = re.compile(
    r"\b(what (can|do) (you|u) do|how can (you|u) help|what can i ask)\b|^help( me)?[.!?]*$"
)
_PERSONAL = re.compile(
    r"\byour (father|mother|mom|dad|parents?|family|brother|sister|wife|husband|girlfriend|boyfriend|age)\b"
    r"|\bare (you|u) (married|single|happy)\b|\bhow old are (you|u)\b"
)
_HOW_ARE_YOU = re.compile(r"\bhow are (you|u)\b|\bkaise ho\b|\bwhat'?s up\b")
_THANKS = re.compile(r"^(thanks|thank you|thx|ty|shukriya|dhanyavaad)\b[\s\w]{0,20}[.!]*$")
_GREETING = re.compile(r"^(hi+|hello+|hey+|namaste|good (morning|afternoon|evening))\b[\s\w]{0,12}[.!]*$")
_NAME = re.compile(r"\bwhat(?:'s| is) my (name|username)\b|\bwho am i\b|\bmera naam\b")
_EMAIL = re.compile(r"\bwhat(?:'s| is) my (email|e-mail|email address)\b")

CAPABILITIES = (
    "I can work out your spending and income, compare months, show your biggest payments and check your "
    "budget. I can also explain money topics like budgeting and saving, and help you use the app."
)
_OFF_TOPIC = (
    "That one's outside what I do, but I'm happy to help with your money. {capabilities}",
    "I can't help with that, I'm afraid. {capabilities}",
    "I'll have to skip that one, since I stick to your money and this app. {capabilities}",
)
_DONT_KNOW = (
    "I don't have an answer for that yet. {capabilities}",
    "I couldn't find that in what I know. {capabilities}",
    "I'm not sure about that one. {capabilities}",
)
OFF_TOPIC_SUGGESTIONS = ["Where did my money go this month?", "Explain the 50/30/20 rule"]


@dataclass(frozen=True)
class Fixed:
    text: str
    suggestions: list[str] = field(default_factory=list)


def _varied(options: tuple[str, ...], message: str) -> str:
    """The same question gets the same reply, but different questions don't all read alike."""
    choice = options[zlib.crc32(message.lower().encode()) % len(options)]
    return choice.format(capabilities=CAPABILITIES)


def off_topic_reply(message: str) -> Fixed:
    return Fixed(_varied(_OFF_TOPIC, message), OFF_TOPIC_SUGGESTIONS)


def dont_know_reply(message: str) -> Fixed:
    return Fixed(_varied(_DONT_KNOW, message), OFF_TOPIC_SUGGESTIONS)


def fixed_reply(message: str) -> Fixed | None:
    """A reply decided in code, or None for questions that need the tools or the articles."""
    t = " ".join(message.lower().split())
    # Security first, so "hi, what's your api key" is never treated as a greeting
    if _PASSWORD.search(t):
        return Fixed(
            "I can't see or share passwords: they're stored in a form nobody can read. "
            "If you've forgotten yours, use Forgot password on the login page.",
            ["How do I reset my password?"],
        )
    if _SYSTEM.search(t):
        return Fixed("I can't share details about how the app is built or run.", OFF_TOPIC_SUGGESTIONS)
    if _OTHER_USERS.search(t):
        return Fixed(
            "I can't share anything about other users. Everyone's data is private, and I can only see yours.",
            OFF_TOPIC_SUGGESTIONS,
        )
    if _CREATOR.search(t):
        return Fixed("I was built by Ketul Mehta as part of the Expense Tracker app.")
    if _IDENTITY.search(t):
        return Fixed(f"I'm the Expense Tracker assistant, an AI that helps with your money. {CAPABILITIES}")
    if _CAPABILITIES.search(t):
        return Fixed(CAPABILITIES, OFF_TOPIC_SUGGESTIONS)
    if _PERSONAL.search(t):
        return Fixed(
            f"I'm an AI assistant, so no family or birthdays for me! {CAPABILITIES}", OFF_TOPIC_SUGGESTIONS
        )
    if _HOW_ARE_YOU.search(t):
        return Fixed(
            "I'm doing well, thanks! What would you like to know about your money?", OFF_TOPIC_SUGGESTIONS
        )
    if _THANKS.match(t):
        return Fixed("You're welcome!")
    if _GREETING.match(t):
        return Fixed(
            "Hi! Ask me about your spending, budgeting and saving, or how to use the app. "
            'For example: "How much did I spend on food last month?"',
            OFF_TOPIC_SUGGESTIONS,
        )
    return None


def profile_field(message: str) -> str | None:
    """ "name" or "email" if the question asks for the user's own profile."""
    t = " ".join(message.lower().split())
    if _NAME.search(t):
        return "name"
    if _EMAIL.search(t):
        return "email"
    return None
