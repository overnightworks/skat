import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from skat.web.constants import DEFAULT_HOST, DEFAULT_PORT, OIDC_CLIENT_ID
from skat.web.settings import ServerSettings

REQUIRED_SIGN_IN_SETTINGS = ["oidc_issuer", "oidc_client_secret_file", "public_origin", "session_secret_file"]


class TestServerSettings:
    def test_defaults(self, sign_in_settings):
        settings = sign_in_settings().settings
        assert settings.host == DEFAULT_HOST
        assert settings.port == DEFAULT_PORT
        assert settings.oidc_client_id == OIDC_CLIENT_ID
        assert settings.trusted_proxies == ""

    def test_override_via_environment(self, sign_in_settings):
        sign_in = sign_in_settings()
        env = {
            **sign_in.environment,
            "SKAT_HOST": "127.0.0.1",
            "SKAT_PORT": "9090",
            "SKAT_OIDC_CLIENT_ID": "other-client",
            "SKAT_TRUSTED_PROXIES": "10.0.0.0/8,127.0.0.1",
        }
        with patch.dict(os.environ, env):
            settings = ServerSettings()
            assert settings.host == "127.0.0.1"
            assert settings.port == 9090
            assert settings.oidc_client_id == "other-client"
            assert settings.trusted_proxies == "10.0.0.0/8,127.0.0.1"
            assert settings.oidc_issuer == sign_in.settings.oidc_issuer
            assert settings.public_origin == sign_in.settings.public_origin
            assert settings.oidc_client_secret_file == sign_in.settings.oidc_client_secret_file
            assert settings.session_secret_file == sign_in.settings.session_secret_file

    @pytest.mark.parametrize("setting", REQUIRED_SIGN_IN_SETTINGS)
    def test_missing_required_sign_in_setting_is_refused_by_name(self, sign_in_settings, setting):
        with pytest.raises(ValidationError, match=setting):
            sign_in_settings(**{setting: None})

    @pytest.mark.parametrize(
        ("setting", "value"),
        [
            ("oidc_issuer", "https://issuer.test.invalid/realms/test/"),
            ("public_origin", "https://skat.test.invalid/"),
            ("public_origin", "https://skat.test.invalid/apps/skat"),
            ("oidc_client_secret_file", "relative/client-secret"),
            ("session_secret_file", "relative/session-secret"),
        ],
    )
    def test_malformed_sign_in_setting_is_refused_by_name_and_never_by_value(self, sign_in_settings, setting, value):
        with pytest.raises(ValidationError, match=setting) as refusal:
            sign_in_settings(**{setting: value})
        assert value not in str(refusal.value)
