#!/usr/bin/env python3
"""
ToolContext provides access to shared resources for tool execution.

This module contains the ToolContext class which is used throughout the codebase
to provide access to airports database, rules manager, notification service, and
GA friendliness service.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from euro_aip.models.euro_aip_model import EuroAipModel
from euro_aip.storage.database_storage import DatabaseStorage
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .rules_manager import RulesManager


class ToolContextSettings(BaseSettings):
    """
    Settings for ToolContext database paths.

    Uses Pydantic BaseSettings to read from environment variables and .env files.
    All paths can be configured via environment variables with fallback defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    airports_db: Path = Field(
        default=Path("airports.db"),
        description="Path to airports.db SQLite database",
        alias="AIRPORTS_DB",
    )
    rules_json: Path = Field(
        default=Path("rules.json"),
        description="Path to rules.json for query answering",
        alias="RULES_JSON",
    )
    ga_notifications_db: Path = Field(
        default=Path("ga_notifications.db"),
        description="Path to GA notifications database",
        alias="GA_NOTIFICATIONS_DB",
    )
    ga_meta_db: Optional[Path] = Field(
        default=None,
        description="Path to GA meta database (optional)",
        alias="GA_PERSONA_DB",
    )


@lru_cache(maxsize=1)
def get_tool_context_settings() -> ToolContextSettings:
    """Get cached ToolContextSettings instance."""
    return ToolContextSettings()


@dataclass
class ToolContext:
    """
    Context providing access to shared resources for tool execution.

    Note: ToolContext is NOT stateful - do not store user-specific state here.
    Pass user preferences (like persona) via tool function parameters or context dicts.
    """

    model: EuroAipModel
    notification_service: Optional[Any] = None  # NotificationService (lazy import to avoid circular deps)
    ga_friendliness_service: Optional[Any] = None  # GAFriendlinessService (lazy import)
    rules_manager: Optional[RulesManager] = None

    @classmethod
    def create(
        cls,
        settings: Optional[ToolContextSettings] = None,
        load_airports: bool = True,
        load_rules: bool = True,
        load_notifications: bool = True,
        load_ga_friendliness: bool = True,
    ) -> "ToolContext":
        """
        Create ToolContext with all paths resolved from settings.

        Args:
            settings: ToolContextSettings instance. If None, uses cached default.
            load_airports: Load airports database (default: True)
            load_rules: Load rules manager (default: True)
            load_notifications: Load notification service (default: True)
            load_ga_friendliness: Load GA friendliness service (default: True)

        Returns:
            ToolContext instance with requested services loaded
        """
        # Use provided settings or get cached default
        settings = settings or get_tool_context_settings()

        # Load core model (required if load_airports is True)
        model = None
        if load_airports:
            storage = DatabaseStorage(str(settings.airports_db))
            model = storage.load_model()
        else:
            raise ValueError("load_airports must be True - airports database is required")

        # Initialize NotificationService (optional)
        notification_service = None
        if load_notifications:
            try:
                from shared.ga_notification_agent.service import NotificationService
                notification_service = NotificationService()
            except Exception:
                pass  # Service is optional

        # Initialize GAFriendlinessService (optional)
        ga_friendliness_service = None
        if load_ga_friendliness:
            try:
                from shared.ga_friendliness.service import GAFriendlinessService
                ga_meta_db = settings.ga_meta_db
                if ga_meta_db and ga_meta_db.exists():
                    ga_friendliness_service = GAFriendlinessService(str(ga_meta_db), readonly=True)
            except Exception:
                pass  # Service is optional

        # Initialize RulesManager (optional)
        rules_manager = None
        if load_rules:
            rules_manager = RulesManager(str(settings.rules_json))
            rules_manager.load_rules()

        return cls(
            model=model,
            notification_service=notification_service,
            ga_friendliness_service=ga_friendliness_service,
            rules_manager=rules_manager,
        )

    def ensure_rules_manager(self) -> RulesManager:
        if not self.rules_manager:
            self.rules_manager = RulesManager()
            self.rules_manager.load_rules()
        elif not self.rules_manager.loaded:
            self.rules_manager.load_rules()
        return self.rules_manager

