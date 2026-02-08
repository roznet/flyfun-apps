"""
Priority evaluator for NOTAMs using JSON profile configs.

Evaluates NOTAM priority based on Q-code matching rules defined in
JSON profile files (e.g., configs/priority_profiles/ifr.json).

Rules are evaluated in order; the first match wins.
Unmatched NOTAMs receive the profile's max_level.
"""

import json
from pathlib import Path
from typing import Optional, Tuple

from euro_aip.briefing.models.notam import Notam

# Conditions indicating unavailable/closed/canceled
UNAVAILABLE_CONDITIONS = {"AS", "AU", "LC", "LI", "LV", "CN"}


class PriorityEvaluator:
    """Evaluate NOTAM priority from a JSON profile config."""

    def __init__(self, profile_path: str):
        with open(profile_path) as f:
            self.profile = json.load(f)
        self.max_level = self.profile["max_level"]
        self.rules = self.profile["rules"]
        self.profile_id = self.profile["id"]
        self.display_name = self.profile["display_name"]

    def evaluate(
        self,
        notam: Notam,
        distance_nm: Optional[float],
        dep_icao: Optional[str],
        dest_icao: Optional[str],
        cruise_altitude_ft: Optional[int],
    ) -> Tuple[int, str]:
        """
        Evaluate priority for a single NOTAM.

        Returns:
            (level, matched_rule_id) where level is 1-max_level
            and matched_rule_id is the rule that matched (or "default").
        """
        for rule in self.rules:
            if rule["type"] != "q_code_match":
                continue
            matched = self._match_q_code_rule(
                rule, notam, distance_nm, dep_icao, dest_icao, cruise_altitude_ft
            )
            if matched:
                return rule["level"], rule["id"]

        return self.max_level, "default"

    def _match_q_code_rule(
        self,
        rule: dict,
        notam: Notam,
        distance_nm: Optional[float],
        dep_icao: Optional[str],
        dest_icao: Optional[str],
        cruise_altitude_ft: Optional[int],
    ) -> bool:
        """Check if a NOTAM matches a q_code_match rule. All present fields must match."""
        q_code = notam.q_code
        subject = q_code[1:3] if q_code and len(q_code) >= 3 else None
        condition = q_code[3:5] if q_code and len(q_code) >= 5 else None

        # Subject filter
        if "subjects" in rule:
            if subject is None:
                return False
            if subject not in rule["subjects"]:
                return False
        else:
            # Rules without subjects still require a Q-code
            if subject is None:
                return False

        # Condition filter
        if "conditions" in rule:
            if condition is None or condition not in rule["conditions"]:
                return False

        if "condition_filter" in rule:
            if rule["condition_filter"] == "unavailable":
                if not self._is_unavailable(condition, notam):
                    return False
            elif rule["condition_filter"] == "limitation":
                if not self._is_limitation(condition, notam):
                    return False

        # Location filter
        if "location" in rule:
            at_dep_dest = self._is_at_dep_dest(notam, dep_icao, dest_icao)
            if rule["location"] == "dep_dest" and not at_dep_dest:
                return False
            if rule["location"] == "not_dep_dest" and at_dep_dest:
                return False

        # Distance filter
        if "max_distance_nm" in rule:
            if distance_nm is None:
                return False
            if distance_nm > rule["max_distance_nm"]:
                return False

        # Altitude check
        if "altitude_check" in rule:
            if not self._check_altitude(
                rule, notam, distance_nm, cruise_altitude_ft
            ):
                return False

        return True

    def _check_altitude(
        self,
        rule: dict,
        notam: Notam,
        distance_nm: Optional[float],
        cruise_altitude_ft: Optional[int],
    ) -> bool:
        """Handle altitude_check: 'if_available' or 'required'."""
        check = rule["altitude_check"]

        if check == "if_available":
            # Pass if no cruise altitude is set
            if cruise_altitude_ft is None:
                return True
            return self._is_altitude_relevant(notam, cruise_altitude_ft)

        if check == "required":
            if cruise_altitude_ft is not None:
                return self._is_altitude_relevant(notam, cruise_altitude_ft)
            # No cruise altitude: use fallback distance if configured
            fallback = rule.get("no_altitude_fallback_distance_nm")
            if fallback is not None and distance_nm is not None:
                return distance_nm <= fallback
            return False

        return True

    @staticmethod
    def _is_altitude_relevant(notam: Notam, cruise_altitude_ft: int) -> bool:
        """Check if NOTAM altitude range overlaps cruise altitude +/- 2000ft."""
        notam_lower = notam.lower_limit if notam.lower_limit is not None else 0
        notam_upper = notam.upper_limit if notam.upper_limit is not None else 99999

        # Skip surface-to-unlimited NOTAMs (not altitude-relevant)
        if notam_lower == 0 and notam_upper >= 99900:
            return False

        cruise_low = cruise_altitude_ft - 2000
        cruise_high = cruise_altitude_ft + 2000
        return cruise_low <= notam_upper and cruise_high >= notam_lower

    @staticmethod
    def _is_at_dep_dest(
        notam: Notam,
        dep_icao: Optional[str],
        dest_icao: Optional[str],
    ) -> bool:
        """Check if NOTAM location matches departure or destination."""
        loc = notam.location
        if not loc:
            return False
        return loc == dep_icao or loc == dest_icao

    @staticmethod
    def _is_unavailable(condition: Optional[str], notam: Notam) -> bool:
        """Check if condition indicates unavailable/closed/canceled."""
        if condition and condition in UNAVAILABLE_CONDITIONS:
            return True
        if hasattr(notam, "custom_tags") and "closed" in notam.custom_tags:
            return True
        return False

    @staticmethod
    def _is_limitation(condition: Optional[str], notam: Notam) -> bool:
        """Check if condition indicates a limitation (L* conditions or closed tag)."""
        if condition and condition.startswith("L"):
            return True
        if hasattr(notam, "custom_tags") and "closed" in notam.custom_tags:
            return True
        return False


def resolve_profile_path(profile: str) -> str:
    """
    Resolve profile name or path to an actual file path.

    Built-in names (ifr, vfr) resolve to configs/priority_profiles/<name>.json.
    Paths ending in .json are returned as-is.
    """
    if profile.endswith(".json") and Path(profile).exists():
        return profile

    # Try built-in profiles relative to repo root
    repo_root = Path(__file__).parent.parent
    builtin = repo_root / "configs" / "priority_profiles" / f"{profile}.json"
    if builtin.exists():
        return str(builtin)

    # Try as direct path
    if Path(profile).exists():
        return profile

    raise FileNotFoundError(
        f"Priority profile not found: {profile}\n"
        f"  Tried: configs/priority_profiles/{profile}.json and {profile}"
    )
