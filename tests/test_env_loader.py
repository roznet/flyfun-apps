"""shared.env_loader: the chosen env file, then its `.secrets` sibling."""
from __future__ import annotations

import os

import pytest

from shared import env_loader

KEYS = ("FA_TEST_CONFIG", "FA_TEST_SECRET", "FA_TEST_PRESET", "ENV_FILE")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    for key in KEYS:
        os.environ.pop(key, None)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_secrets_path():
    from pathlib import Path
    assert env_loader.secrets_path(Path("/x/.env")) == Path("/x/.env.secrets")
    assert env_loader.secrets_path(Path("/x/prod.env")) == Path("/x/prod.env.secrets")


def test_component_env_then_its_secrets(tmp_path):
    write(tmp_path / ".env", "FA_TEST_CONFIG=plain\n")
    write(tmp_path / ".env.secrets", "FA_TEST_SECRET=hidden\n")
    env_loader.load_component_env(tmp_path)
    assert os.environ["FA_TEST_CONFIG"] == "plain"
    assert os.environ["FA_TEST_SECRET"] == "hidden"


def test_missing_secrets_file_is_fine(tmp_path):
    write(tmp_path / ".env", "FA_TEST_CONFIG=plain\n")
    env_loader.load_component_env(tmp_path)
    assert os.environ["FA_TEST_CONFIG"] == "plain"
    assert "FA_TEST_SECRET" not in os.environ


def test_explicit_path_and_env_file_var_get_their_own_sibling(tmp_path, monkeypatch):
    write(tmp_path / "custom" / "prod.env", "FA_TEST_CONFIG=custom\n")
    write(tmp_path / "custom" / "prod.env.secrets", "FA_TEST_SECRET=custom-secret\n")
    write(tmp_path / ".env.secrets", "FA_TEST_SECRET=wrong-file\n")  # not the chosen file's sibling
    env_loader.load_component_env(tmp_path, explicit_path=tmp_path / "custom" / "prod.env")
    assert os.environ["FA_TEST_SECRET"] == "custom-secret"

    os.environ.pop("FA_TEST_SECRET")
    monkeypatch.setenv("ENV_FILE", str(tmp_path / "custom" / "prod.env"))
    env_loader.load_component_env(tmp_path)
    assert os.environ["FA_TEST_SECRET"] == "custom-secret"


def test_override_behaviour_unchanged(tmp_path, monkeypatch):
    # the loader has always used override=True; the secrets file follows the same rule
    monkeypatch.setenv("FA_TEST_PRESET", "from-environment")
    write(tmp_path / ".env", "FA_TEST_CONFIG=plain\n")
    write(tmp_path / ".env.secrets", "FA_TEST_PRESET=from-secrets\n")
    env_loader.load_component_env(tmp_path)
    assert os.environ["FA_TEST_PRESET"] == "from-secrets"


def test_pydantic_settings_read_both_files(tmp_path, monkeypatch):
    # settings classes that read env files directly (not through the loader)
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class S(BaseSettings):
        model_config = SettingsConfigDict(env_file=(".env", ".env.secrets"), extra="ignore")
        fa_test_config: str = ""
        fa_test_secret: str = ""

    write(tmp_path / ".env", "FA_TEST_CONFIG=plain\n")
    write(tmp_path / ".env.secrets", "FA_TEST_SECRET=hidden\n")
    monkeypatch.chdir(tmp_path)
    s = S()
    assert (s.fa_test_config, s.fa_test_secret) == ("plain", "hidden")
    (tmp_path / ".env.secrets").unlink()
    assert S().fa_test_secret == ""  # missing secrets file is fine


def test_shared_settings_classes_list_the_secrets_file():
    from shared.aviation_agent.config import AviationAgentSettings
    from shared.ga_friendliness.config import GAFriendlinessSettings
    from shared.tool_context import ToolContextSettings

    for cls in (AviationAgentSettings, GAFriendlinessSettings, ToolContextSettings):
        assert tuple(cls.model_config["env_file"]) == (".env", ".env.secrets"), cls.__name__
