"""Unit tests for configuration in cloudguard.core.config."""

from cloudguard.core.config import Settings, get_settings


class TestConfig:
    def test_default_settings(self):
        settings = Settings()
        assert settings.app_env in ["development", "staging", "production", "testing"]
        assert settings.zscore_threshold >= 1.0
        assert settings.iqr_multiplier >= 0.5
        assert settings.idle_cpu_threshold_pct == 5.0
        assert settings.idle_period_days == 7

    def test_settings_credential_helpers(self):
        s_no_creds = Settings(
            azure_subscription_id=None,
            aws_access_key_id=None,
            aws_secret_access_key=None,
        )
        assert s_no_creds.has_azure_credentials is False
        assert s_no_creds.has_aws_credentials is False

        s_with_creds = Settings(
            azure_subscription_id="sub-12345",
            aws_access_key_id="akid-test",
            aws_secret_access_key="secret-test",
        )
        assert s_with_creds.has_azure_credentials is True
        assert s_with_creds.has_aws_credentials is True

    def test_get_settings_caching(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
