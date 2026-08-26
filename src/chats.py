"""Direct messages between a coach and an athlete.

Distinct from activity messages (see activities.post_activity_message), which
are comments attached to one recorded session. These are the standing
conversation.

Sending is deliberately restricted to one-to-one chats. intervals.icu chats
also cover coaching groups, where a mistaken chat id would broadcast to
everyone in the group rather than message one person.
"""

from fastmcp import Context, FastMCP

from client import get_client
from shaping import prune

chats = FastMCP("chats")

PRIVATE = "PRIVATE"

_CHAT_FIELDS = (
    "id",
    "type",
    "name",
    "other_athlete_id",
    "new_message_count",
    "role",
    "description",
    "updated",
)

_MESSAGE_FIELDS = (
    "id",
    "content",
    "athlete_id",
    "name",
    "created",
    "type",
    "seen",
    "activity_id",
)


def shape_chat(chat: dict) -> dict:
    """Project a chat to what identifies it, dropping branding and layout fields."""
    shaped = prune({f: chat.get(f) for f in _CHAT_FIELDS})
    members = chat.get("members")
    if isinstance(members, list) and len(members) > 2:
        shaped["member_count"] = len(members)
    return shaped


def shape_message(message: dict) -> dict:
    """Project a message, dropping attachments and request-plumbing fields."""
    return prune({f: message.get(f) for f in _MESSAGE_FIELDS})


def is_private(chat: dict) -> bool:
    """True only for a one-to-one chat between two athletes."""
    return chat.get("type") == PRIVATE


@chats.tool(tags={"Chats"}, annotations={"readOnlyHint": True})
async def list_chats(ctx: Context, athlete_id: str = "0") -> list:
    """List an athlete's chats, most recently active first.

    `new_message_count` shows unread messages. `type` is PRIVATE for a
    one-to-one conversation, GROUP for a coaching group, or ACTIVITY for a
    thread attached to a session.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    client = await get_client(ctx)
    resp = await client.get(f"/athlete/{athlete_id}/chats")
    return [shape_chat(c) for c in resp.json()]


@chats.tool(tags={"Chats"}, annotations={"readOnlyHint": True})
async def get_chat_messages(
    ctx: Context,
    chat_id: int,
    limit: int = 30,
    before_id: int | None = None,
) -> list:
    """Read messages in a chat, most recent first.

    Args:
        chat_id: The chat ID, from list_chats.
        limit: How many messages to return (default 30, maximum 100).
        before_id: Return only messages older than this message ID, for paging
                   back through a long conversation.
    """
    params: dict = {"limit": min(limit, 100)}
    if before_id is not None:
        params["beforeId"] = before_id

    client = await get_client(ctx)
    resp = await client.get(f"/chats/{chat_id}/messages", params=params)

    messages = resp.json()
    return [shape_message(m) for m in messages if not m.get("deleted")]


@chats.tool(tags={"Chats"})
async def send_chat_message(ctx: Context, chat_id: int, content: str) -> dict:
    """Send a message in a one-to-one chat.

    This is seen by a real person, so send only what the coach has asked to be
    sent. Group chats are refused: a wrong id there would message everyone in
    a coaching group rather than one athlete.

    To comment on a specific session, use post_activity_message instead — that
    keeps the feedback attached to the activity it is about.

    Args:
        chat_id: The chat ID, from list_chats. Must be a PRIVATE chat.
        content: The message text.
    """
    if not content.strip():
        return {"error": "Message content is empty; nothing was sent."}

    client = await get_client(ctx)

    # Confirm the destination before sending rather than trusting the id: the
    # cost of being wrong is a message delivered to the wrong audience.
    chat_resp = await client.get(f"/chats/{chat_id}")
    chat = chat_resp.json()

    if not is_private(chat):
        return {
            "error": (
                f"Chat {chat_id} is a {chat.get('type', 'non-private')} chat, not a "
                "one-to-one conversation. Sending here would message every member. "
                "Pick a chat with type PRIVATE from list_chats."
            ),
            "chat": shape_chat(chat),
            "sent": False,
        }

    resp = await client.post(
        "/chats/send-message",
        json={"chat_id": chat_id, "content": content, "type": "TEXT"},
    )

    return {
        "sent": True,
        "chat_id": chat_id,
        "to": chat.get("name") or chat.get("other_athlete_id"),
        "message": shape_message(resp.json() if resp.content else {"content": content}),
    }
