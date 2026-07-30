"""Tests for sandbox_app.masking — AC-8."""

from sandbox_app.masking import mask_dict, mask_sensitive, mask_value


class TestMaskValue:
    def test_basic_masking(self) -> None:
        """AC-8.1: mask_value masks characters beyond keep_chars."""
        # "my-password-here" = 16 chars, keep 4 → "my-p" + 12 *
        assert mask_value("my-password-here", 4) == "my-p************"

    def test_short_value_not_masked(self) -> None:
        """AC-8.2: value not longer than keep_chars is returned as-is."""
        assert mask_value("abc", 4) == "abc"

    def test_exact_length_keep_chars(self) -> None:
        assert mask_value("abcd", 4) == "abcd"

    def test_small_keep_chars(self) -> None:
        """AC-8.3: keep_chars smaller than length masks the rest."""
        assert mask_value("abc", 2) == "ab*"

    def test_keep_chars_zero(self) -> None:
        assert mask_value("secret", 0) == "******"

    def test_empty_string(self) -> None:
        assert mask_value("", 4) == ""


class TestMaskDict:
    def test_masks_password_and_token(self) -> None:
        """AC-8.4: mask_dict redacts password and token fields."""
        data = {
            "username": "alice",
            "password": "supersecret123",
            "token": "bearer-abcdefg",
        }
        result = mask_dict(data)
        assert result["username"] == "alice"
        # "supersecret123" = 14 chars, keep 4 → 10 *
        assert result["password"] == "supe**********"
        # "bearer-abcdefg" = 14 chars, keep 4 → 10 *
        assert result["token"] == "bear**********"

    def test_nested_dict(self) -> None:
        """mask_dict recursively processes nested dicts."""
        data = {
            "user": {
                "name": "bob",
                "credentials": {"password": "nested-secret", "token": "tok-12345"},
            }
        }
        result = mask_dict(data)
        # "nested-secret" = 13 chars, keep 4 → 9 *
        assert result["user"]["credentials"]["password"] == "nest*********"
        # "tok-12345" = 9 chars, keep 4 → 5 *
        assert result["user"]["credentials"]["token"] == "tok-*****"

    def test_list_of_dicts(self) -> None:
        """AC-8.5: mask_dict recurses into lists of dicts."""
        data = {
            "users": [
                {"name": "a", "password": "pw1"},
                {"name": "b", "token": "tok2"},
            ]
        }
        result = mask_dict(data)
        # "pw1" = 3 chars, keep_chars=4, 3 <= 4 → not masked
        assert result["users"][0]["password"] == "pw1"
        # "tok2" = 4 chars, keep_chars=4, 4 <= 4 → not masked
        assert result["users"][1]["token"] == "tok2"

    def test_case_insensitive_key_match(self) -> None:
        """Sensitive key matching is case-insensitive."""
        data = {"Password": "MySecret", "TOKEN": "abc12345"}
        result = mask_dict(data)
        # "MySecret" = 8 chars, keep 4 → 4 *
        assert result["Password"] == "MySe****"
        # "abc12345" = 8 chars, keep 4 → 4 *
        assert result["TOKEN"] == "abc1****"

    def test_non_string_sensitive_value(self) -> None:
        """Non-string sensitive fields are left as-is."""
        data = {"password": 12345}
        result = mask_dict(data)
        assert result["password"] == 12345

    def test_original_unchanged(self) -> None:
        """mask_dict never mutates the original dict."""
        original = {"password": "secret123"}
        result = mask_dict(original)
        assert original["password"] == "secret123"
        # "secret123" = 9 chars, keep 4 → 5 *
        assert result["password"] == "secr*****"


class TestMaskSensitive:
    def test_default_fields(self) -> None:
        """AC-8.6: mask_sensitive uses the default field list."""
        data = {"api_key": "sk-abc123", "authorization": "Bearer xyz"}
        result = mask_sensitive(data)
        # "sk-abc123" = 9 chars, keep 4 → 5 *
        assert result["api_key"] == "sk-a*****"
        # "Bearer xyz" = 10 chars, keep 4 → 6 *
        assert result["authorization"] == "Bear******"

    def test_custom_fields(self) -> None:
        """AC-8.7: custom sensitive_fields override the default."""
        data = {"foo": "bar123", "baz": "qux456"}
        result = mask_dict(data, sensitive_fields=["foo"])
        # "bar123" = 6 chars, keep 4 → 2 *
        assert result["foo"] == "bar1**"
        assert result["baz"] == "qux456"  # untouched
