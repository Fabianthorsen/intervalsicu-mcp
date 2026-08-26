"""Unit tests for chat shaping and the group-send guard."""

from chats import is_private, shape_chat, shape_message

PRIVATE_CHAT = {
    "id": 4021,
    "type": "PRIVATE",
    "name": "Ada Lovelace",
    "other_athlete_id": "i98765",
    "new_message_count": 2,
    "role": "COACH",
    "updated": "2026-08-25T18:04:11.000+00:00",
    # Branding and layout noise:
    "sidebar_color": "#112233",
    "sidebar_logo": "https://example.invalid/logo.svg",
    "picture": "https://example.invalid/p.png",
    "slug": "ada",
    "coins": 0,
}

GROUP_CHAT = {
    "id": 5150,
    "type": "GROUP",
    "name": "Winter Base Squad",
    "members": [{"athlete_id": f"i{n}"} for n in range(14)],
    "join_policy": "INVITE_ONLY",
}

ACTIVITY_CHAT = {"id": 77, "type": "ACTIVITY", "activity_id": "i129230824"}


class TestPrivacyGuard:
    def test_private_chat_is_sendable(self) -> None:
        assert is_private(PRIVATE_CHAT)

    def test_group_chat_is_not(self) -> None:
        assert not is_private(GROUP_CHAT)

    def test_activity_chat_is_not(self) -> None:
        assert not is_private(ACTIVITY_CHAT)

    def test_unknown_type_defaults_to_refusing(self) -> None:
        """An unrecognised or missing type must not be treated as one-to-one."""
        assert not is_private({"id": 1})
        assert not is_private({"id": 1, "type": "SOMETHING_NEW"})

    def test_type_match_is_exact(self) -> None:
        assert not is_private({"type": "private"})


class TestShapeChat:
    def test_keeps_what_identifies_the_conversation(self) -> None:
        shaped = shape_chat(PRIVATE_CHAT)
        assert shaped["name"] == "Ada Lovelace"
        assert shaped["other_athlete_id"] == "i98765"
        assert shaped["new_message_count"] == 2
        assert shaped["type"] == "PRIVATE"

    def test_drops_branding_and_layout(self) -> None:
        shaped = shape_chat(PRIVATE_CHAT)
        for field in ("sidebar_color", "sidebar_logo", "picture", "slug", "coins"):
            assert field not in shaped

    def test_summarises_group_size_rather_than_listing_members(self) -> None:
        shaped = shape_chat(GROUP_CHAT)
        assert shaped["member_count"] == 14
        assert "members" not in shaped

    def test_no_member_count_for_a_two_person_chat(self) -> None:
        shaped = shape_chat({"id": 1, "type": "PRIVATE", "members": [{}, {}]})
        assert "member_count" not in shaped


class TestShapeMessage:
    MESSAGE = {
        "id": 900123,
        "content": "Legs felt heavy today, backed off the last two.",
        "athlete_id": "i98765",
        "name": "Ada Lovelace",
        "created": "2026-08-25T18:04:11.000+00:00",
        "type": "TEXT",
        "seen": True,
        "attachment_url": "https://example.invalid/x.jpg",
        "attachment_mime_type": "image/jpeg",
        "join_group_id": None,
        "deleted_by_id": None,
    }

    def test_keeps_the_conversation(self) -> None:
        shaped = shape_message(self.MESSAGE)
        assert shaped["content"].startswith("Legs felt heavy")
        assert shaped["name"] == "Ada Lovelace"
        assert shaped["seen"] is True

    def test_drops_attachments_and_plumbing(self) -> None:
        shaped = shape_message(self.MESSAGE)
        for field in ("attachment_url", "attachment_mime_type", "join_group_id", "deleted_by_id"):
            assert field not in shaped

    def test_empty_message_shapes_to_empty(self) -> None:
        assert shape_message({}) == {}
