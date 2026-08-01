#!/usr/bin/env python3

"""
Review Military Aerodrome Candidates
====================================

Produces an artifact for MANUAL promotion into euro_aip's curated military list
(``euro_aip/utils/military_aerodromes.py``). This tool never edits that list.

Why a review step instead of a runtime rule
-------------------------------------------
Aerodrome naming is the only broad signal available for military fields, and it
is good at *generating candidates* but bad at *deciding*: a published name is not
revoked when a base closes. Five Belgian Air Force bases deactivated in the
1990s are still called "X Air Base" upstream while operating as civil gliding
sites. A runtime regex would flag them forever, and would silently re-flag any
field that upstream renames. So the regex lives here, offline, and its output is
cross-checked against the AIP before a human promotes it.

What counts as AIP confirmation
-------------------------------
There is no "military" field in the AIP. The usable evidence is indirect and
concentrated in the fuel fields:

  strong   a defence ministry or armed service named in AD Administration
           (AD 2.2 item 6, "AD Administration, address, telephone…"). That field
           names who OPERATES the aerodrome, so it is the most direct statement
           the AIP makes -- and it catches fields whose name gives nothing away:
           LFMC Le Luc and LFBY Dax read "MINISTRY OF DEFENCE (ALAT)", LFTH
           Toulon-Hyeres reads "MINISTRY OF DEFENCE" behind an "Airport" name.
  strong   NATO oil/hydraulic codes (O-133, O-150, H-515) — civil aerodromes
           never publish these
  strong   military-only fuels: F-18 (military avgas), F-44 (JP-5, naval)
  strong   military/militaire wording, but ONLY in a field that describes the
           aerodrome (AD Administration, Remarks, Type of Traffic, Conditions of
           use, Fuelling, Handling, Fuel and oil types). In Hotels or
           Transportation it is incidental.
  weak     an explicit MIL: / CIV: split. Looks decisive, is not: French and
           Spanish AIPs use it as a routine presentational convention, so it
           fires on Le Touquet, Bordeaux, Limoges, Malaga and Palma.
  weak     F-34 / F-35 alone. F-34 is just Jet A-1 with FSII and civil UK fields
           advertise it (Sleap, Cumbernauld, Dunkeswell, Brighton City).

Verdicts
--------
  CONFIRMED     name says military AND the AIP carries a strong military marker.
                Ready to promote after a sanity read.
  INCONCLUSIVE  name says military; the AIP has no usable marker. Absence proves
                nothing — most national AIPs never use NATO fuel codes or the
                word "military", so unambiguously active bases (Buechel,
                Wittmundhafen, Papa, Amari, Vidsel, Satenaes) land here too.
                Needs manual research per aerodrome.

Deliberately absent is any "looks civil" verdict. Absence of a marker cannot
distinguish a decommissioned base from a country whose AIP simply does not use
military vocabulary, so the tool does not pretend otherwise.

The tool also reports FOUND_BY_AIP_ONLY: fields with strong military AIP evidence
whose name gives no hint. These are candidates the name rule could never find
(Eindhoven, León, Pau) and are often the most valuable additions.

Usage:
    python tools/review_military_candidates.py \\
        --nav-db data/nav.db \\
        --aip-db data/airports.db \\
        -o scratch/military-review.md
"""

import argparse
import logging
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from euro_aip.utils.military_aerodromes import (
    FORMER_MILITARY,
    KNOWN_MILITARY_ICAOS,
)
from euro_aip.utils.military_classifier import ICAO_PREFIX_RULES

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Candidate generation: aerodrome-name patterns
# ---------------------------------------------------------------------------

# Review-time only. Matched against the aerodrome NAME; never against the
# OurAirports `keywords` column, which retains wartime identities and would
# propose scores of civil GA fields (EGSU Duxford -> "RAF Duxford", EDDF
# Frankfurt -> "Rhein-Main Air Base").
NAME_PATTERNS = (
    (r'\bair\s*base\b', 'air base'),
    (r'\bair\s+force\b', 'air force'),
    (r'\bair\s+station\b', 'air station'),
    (r'\bmilit[aä]r', 'military'),
    (r'\bnaval\s+(air|station|base)\b', 'naval'),
    (r'\bRNAS\b', 'RNAS'),
    (r'\bRAF\b', 'RAF'),
    (r'\bMOD\b', 'MoD'),
    (r'\barmy\s+air\s*(field|base)\b', 'army airfield'),
    (r'\bfliegerhorst\b', 'Fliegerhorst'),
    (r'\bbase\s+a[eé]rienne\b', 'base aérienne'),
    # French air bases publish a squadron number: "Cazaux (BA 120) Air Base"
    (r'\(\s*BA\s*\d{2,3}\s*\)', 'BA number'),
    (r'\broyal\s+marines\s+base\b', 'Royal Marines base'),
)

_COMPILED_NAMES = [(re.compile(p, re.IGNORECASE), label) for p, label in NAME_PATTERNS]


def prefix_covered(ident: str) -> bool:
    """True if an ICAO prefix rule in euro_aip already classifies this ident.

    Mirrors MilitaryClassifier's guard: a well-formed 4-letter alphabetic ident,
    so local codes sharing a prefix (ETT1, EG74) are not treated as covered.
    """
    return (
        len(ident) == 4
        and ident.isalpha()
        and any(rule.matches(ident.upper()) for rule in ICAO_PREFIX_RULES)
    )


def name_signal(name: Optional[str]) -> Optional[str]:
    """Return the label of the first name pattern that matches, else None."""
    if not name:
        return None
    for pattern, label in _COMPILED_NAMES:
        if pattern.search(name):
            return label
    return None


# ---------------------------------------------------------------------------
# AIP cross-check
# ---------------------------------------------------------------------------

# Strong markers: evidence a civil aerodrome would not publish. Each of these
# was validated against the actual AIP corpus; the rejected candidates are
# recorded in WEAK_AIP_MARKERS below, because the obvious-looking ones fail.
STRONG_AIP_MARKERS = (
    # NATO oil / hydraulic codes, e.g. O-133, O-150, H-515. Civil aerodromes
    # publish trade names ("W80, W100, 15W50"), not NATO codes.
    (re.compile(r'\b[OH]-?\d{3}\b'), 'NATO oil/hyd code'),
    # Military-only fuels: F-18 military avgas, F-44 JP-5 (naval).
    (re.compile(r'\bF-?(18|44)\b'), 'military-only fuel'),
)

# Fields where the word "military" actually says something about the aerodrome.
# Excluded: Hotels, Restaurants, Transportation, Medical facilities and the like,
# which mention military facilities incidentally — Chièvres matched only on
# "via National Military Representative" under Transportation.
WORDING_FIELDS = (
    'AD Administration',
    'Remarks',
    'Type of Traffic permitted (IFR/VFR)',
    'Conditions of use',
    'Fuelling',
    'Handling',
    'Fuel and oil types',
)

MILITARY_WORDING = re.compile(r'militar\w*|militaire', re.IGNORECASE)

# AD 2.2 item 6 ("AD Administration, address, telephone…") names the authority
# that operates the aerodrome, so a defence ministry or armed service appearing
# here is about as direct a statement as the AIP ever makes. Stronger than the
# fuel-code proxies, and it catches fields whose name gives nothing away:
# LFMC Le Luc and LFBY Dax read "MINISTRY OF DEFENCE (ALAT)", LFTH Toulon-Hyères
# reads "MINISTRY OF DEFENCE" behind an ordinary "Airport" name.
#
# Scoped to this one field on purpose — "Air Force" in Hotels or Transportation
# is incidental, and only here does it identify the operator.
ADMIN_FIELD = 'AD Administration'

ADMIN_MILITARY_AUTHORITY = re.compile(
    r'\bdefen[cs]e\b'                       # MINISTRY OF DEFENCE / DEFENSE
    r'|\bd[eé]fense\b'                      # MINISTÈRE DE LA DÉFENSE
    r'|\bair\s+force\b'                     # incl. Royal Norwegian Air Force
    r'|\bluftwaffe\b|\bbundeswehr\b'
    r'|\bluftforsvaret\b|\bflygvapnet\b'
    r'|\baeronautica\s+militare\b'
    r'|\barm[eé]e\s+de\s+l[\'’]air\b'
    r'|\bmarine\s+nationale\b'
    r'|\bALAT\b|\bFAF\b|\bFNF\b'            # French army / air force / navy air arms
    r'|\bnavy\b|\bnaval\b|\barmy\b'
    r'|\bmilit[aä]r',
    re.IGNORECASE,
)

# Markers that LOOK strong but are not. Kept, reported, and never used to
# promote — documenting the traps is the point:
#
#   MIL/CIV split — French and Spanish AIPs use "MIL: … CIV: …" as a routine
#   presentational convention at ordinary civil airports. It fires on Le Touquet,
#   Bordeaux, Limoges, Málaga and Palma, so it says nothing about the field.
#
#   F-34 / F-35 — F-34 is merely Jet A-1 with FSII. Civil UK fields advertise it
#   (Sleap, Cumbernauld, Dunkeswell, Brighton City).
WEAK_AIP_MARKERS = (
    (re.compile(r'\bMIL\b\s*[:/-]|\bCIV[\s/-]*MIL\b|\bMIL[\s/-]*CIV\b'),
     'MIL/CIV split (weak: routine AIP convention at civil airports)'),
    (re.compile(r'\bF-?(34|35)\b'),
     'F-34/F-35 (weak: civil fields list it too)'),
)


@dataclass
class AipEvidence:
    """What the AIP says about one aerodrome."""

    entry_count: int = 0
    procedure_count: int = 0
    strong: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    weak: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))

    @property
    def has_aip_data(self) -> bool:
        return self.entry_count > 0

    @property
    def is_confirmed(self) -> bool:
        return bool(self.strong)

    @property
    def strong_labels(self) -> List[str]:
        return sorted(self.strong)

    @property
    def weak_labels(self) -> List[str]:
        return sorted(self.weak)


def load_aip_evidence(aip_db: Path) -> Dict[str, AipEvidence]:
    """Scan every AIP entry once, collecting military markers per aerodrome."""
    conn = sqlite3.connect(aip_db)
    conn.row_factory = sqlite3.Row
    evidence: Dict[str, AipEvidence] = defaultdict(AipEvidence)

    rows = conn.execute(
        'SELECT airport_icao, std_field, field, value FROM aip_entries '
        'WHERE value IS NOT NULL'
    ).fetchall()
    for row in rows:
        icao = row['airport_icao']
        if not icao:
            continue
        ev = evidence[icao]
        ev.entry_count += 1
        value = row['value']
        label_field = row['std_field'] or row['field'] or '?'

        for pattern, label in STRONG_AIP_MARKERS:
            m = pattern.search(value)
            if m:
                ev.strong[label].append(f'{label_field}: …{_excerpt(value, m)}…')

        # The operating authority named in AD 2.2 item 6.
        if label_field == ADMIN_FIELD:
            m = ADMIN_MILITARY_AUTHORITY.search(value)
            if m:
                ev.strong['defence authority (AD Administration)'].append(
                    f'{label_field}: …{_excerpt(value, m)}…')

        # "military" only counts in a field that describes the aerodrome.
        if label_field in WORDING_FIELDS:
            m = MILITARY_WORDING.search(value)
            if m:
                ev.strong['military wording'].append(
                    f'{label_field}: …{_excerpt(value, m)}…')

        for pattern, label in WEAK_AIP_MARKERS:
            m = pattern.search(value)
            if m:
                ev.weak[label].append(f'{label_field}: …{_excerpt(value, m)}…')

    for row in conn.execute(
        'SELECT airport_icao, COUNT(*) n FROM procedures GROUP BY airport_icao'
    ):
        if row['airport_icao']:
            evidence[row['airport_icao']].procedure_count = row['n']

    conn.close()
    logger.info(f'AIP evidence loaded for {len(evidence)} aerodromes from {aip_db}')
    return evidence


def _excerpt(value: str, match: re.Match, width: int = 26) -> str:
    """A short one-line window around a regex match, for the report."""
    flat = ' '.join(value.split())
    start = max(0, match.start() - width // 2)
    return flat[start:start + width]


def aip_covered_countries(aip_db: Path) -> Set[str]:
    """Countries for which any AIP airport data exists.

    Used to tell "published as civil" apart from "we simply have no data".
    """
    conn = sqlite3.connect(aip_db)
    try:
        rows = conn.execute(
            'SELECT DISTINCT a.iso_country FROM airports a '
            'JOIN aip_entries e ON e.airport_icao = a.icao_code '
            'WHERE a.iso_country IS NOT NULL'
        ).fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows if r[0]}


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    icao: str
    name: str
    country: str
    name_match: Optional[str]
    evidence: AipEvidence
    verdict: str


def build_candidates(nav_db: Path, evidence: Dict[str, AipEvidence],
                     covered: Set[str]) -> List[Candidate]:
    """Generate name candidates and AIP-only finds, and assign each a verdict."""
    conn = sqlite3.connect(nav_db)
    conn.row_factory = sqlite3.Row
    airports = conn.execute(
        'SELECT icao_code, name, iso_country FROM airports ORDER BY icao_code'
    ).fetchall()
    conn.close()

    candidates: List[Candidate] = []
    for row in airports:
        icao = row['icao_code']
        name = row['name'] or ''
        country = row['iso_country'] or '??'

        # Already decided — nothing to review.
        if icao in KNOWN_MILITARY_ICAOS or icao in FORMER_MILITARY:
            continue

        # Already covered by an ICAO prefix rule, so a curated entry would be
        # redundant — and listing a handful of German ET fields would wrongly
        # imply the unlisted ones are civil.
        if prefix_covered(icao):
            continue

        matched = name_signal(name)
        ev = evidence.get(icao, AipEvidence())

        if matched:
            # Only a positive marker decides anything. Absence is NOT evidence of
            # civil status: most national AIPs never use NATO fuel codes or the
            # word "military" at all, so Buechel, Wittmundhafen, Papa, Amari,
            # Vidsel and Satenaes all read "no marker" while being unambiguously
            # active. An earlier version of this tool bucketed those as
            # contradicted, which was simply wrong.
            verdict = 'CONFIRMED' if ev.is_confirmed else 'INCONCLUSIVE'
        elif ev.is_confirmed:
            verdict = 'FOUND_BY_AIP_ONLY'
        else:
            continue

        candidates.append(Candidate(icao, name, country, matched, ev, verdict))

    return candidates


VERDICT_ORDER = ['CONFIRMED', 'FOUND_BY_AIP_ONLY', 'INCONCLUSIVE']

VERDICT_NOTES = {
    'CONFIRMED': 'Name says military AND the AIP carries strong military '
                 'evidence. Promote into KNOWN_MILITARY_ICAOS after a sanity read.',
    'FOUND_BY_AIP_ONLY': 'Strong military AIP evidence but the name gives no '
                         'hint — the name rule could never find these. Often the '
                         'most valuable additions. Verify joint-use status.',
    'INCONCLUSIVE': 'Name says military; the AIP carries no usable marker. This '
                    'is NOT evidence of civil status — most national AIPs never '
                    'use NATO fuel codes or the word "military", and plenty of '
                    'unambiguously active bases land here. Needs manual research '
                    'per aerodrome. The `AIP entries` and `Procs` columns are '
                    'hints only. Fields already researched and rejected belong in '
                    'FORMER_MILITARY so they stop reappearing.',
}


def render(candidates: List[Candidate], nav_db: Path, aip_db: Path) -> str:
    by_verdict: Dict[str, List[Candidate]] = defaultdict(list)
    for c in candidates:
        by_verdict[c.verdict].append(c)

    out: List[str] = []
    out.append('# Military aerodrome candidates — review artifact')
    out.append('')
    out.append(f'- Candidates from: `{nav_db}`')
    out.append(f'- Cross-checked against: `{aip_db}`')
    out.append(f'- Already curated (skipped): {len(KNOWN_MILITARY_ICAOS)} military, '
               f'{len(FORMER_MILITARY)} former-military')
    out.append('')
    out.append('Counts by verdict:')
    out.append('')
    for v in VERDICT_ORDER:
        out.append(f'- **{v}**: {len(by_verdict[v])}')
    out.append('')
    out.append('> Nothing here is applied automatically. Promote entries by hand into')
    out.append('> `euro_aip/utils/military_aerodromes.py`.')
    out.append('')

    for v in VERDICT_ORDER:
        group = by_verdict[v]
        out.append('---')
        out.append('')
        out.append(f'## {v} ({len(group)})')
        out.append('')
        out.append(VERDICT_NOTES[v])
        out.append('')
        if not group:
            out.append('_None._')
            out.append('')
            continue

        out.append('| ICAO | Cc | Name | Name match | AIP entries | Procs | Evidence |')
        out.append('|---|---|---|---|---|---|---|')
        for c in sorted(group, key=lambda x: (x.country, x.icao)):
            ev = c.evidence
            if v == 'INCONCLUSIVE':
                detail = '; '.join(ev.weak_labels) or 'no usable marker'
            else:
                detail = '; '.join(ev.strong_labels) or '—'
            out.append(
                f'| `{c.icao}` | {c.country} | {_md(c.name)} | {c.name_match or "—"} '
                f'| {ev.entry_count} | {ev.procedure_count} | {_md(detail)} |'
            )
        out.append('')

        # Paste-ready block for the buckets a reviewer promotes from.
        if v in ('CONFIRMED', 'FOUND_BY_AIP_ONLY'):
            out.append('<details><summary>Paste-ready entries (review each line first)</summary>')
            out.append('')
            out.append('```python')
            current = None
            for c in sorted(group, key=lambda x: (x.country, x.icao)):
                if c.country != current:
                    out.append(f'    # {c.country}')
                    current = c.country
                why = '; '.join(c.evidence.strong_labels) or 'AIP evidence'
                out.append(f"    '{c.icao}': '{_py(c.name)} — {why}',")
            out.append('```')
            out.append('')
            out.append('</details>')
            out.append('')

        # Show the raw AIP excerpts that justified each CONFIRMED verdict, so the
        # reviewer can judge without opening the database.
        if v == 'CONFIRMED' and group:
            out.append('<details><summary>Supporting AIP excerpts</summary>')
            out.append('')
            for c in sorted(group, key=lambda x: (x.country, x.icao)):
                out.append(f'**`{c.icao}` {c.name}**')
                out.append('')
                for label in c.evidence.strong_labels:
                    for excerpt in c.evidence.strong[label][:2]:
                        out.append(f'- _{label}_ — `{_md(excerpt)}`')
                out.append('')
            out.append('</details>')
            out.append('')

    return '\n'.join(out) + '\n'


def _md(text: str) -> str:
    """Escape a value for a markdown table cell."""
    return (text or '').replace('|', '\\|').replace('\n', ' ')


def _py(text: str) -> str:
    return (text or '').replace('\\', '').replace("'", "\\'")


def main():
    parser = argparse.ArgumentParser(
        description='Generate a review artifact of military aerodrome candidates, '
                    'cross-checked against AIP evidence.')
    parser.add_argument('--nav-db', default='data/nav.db',
                        help='Aerodrome source for candidate generation (default: data/nav.db)')
    parser.add_argument('--aip-db', default='data/airports.db',
                        help='AIP database used for cross-checking (default: data/airports.db)')
    parser.add_argument('-o', '--output', default='scratch/military-review.md',
                        help='Artifact path (default: scratch/military-review.md)')
    args = parser.parse_args()

    nav_db, aip_db = Path(args.nav_db), Path(args.aip_db)
    for path in (nav_db, aip_db):
        if not path.exists():
            parser.error(f'{path} not found')

    evidence = load_aip_evidence(aip_db)
    covered = aip_covered_countries(aip_db)
    logger.info(f'AIP airport coverage spans {len(covered)} countries')

    candidates = build_candidates(nav_db, evidence, covered)
    counts = defaultdict(int)
    for c in candidates:
        counts[c.verdict] += 1
    for v in VERDICT_ORDER:
        logger.info(f'  {v}: {counts[v]}')

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(candidates, nav_db, aip_db))
    logger.info(f'Wrote {output} ({len(candidates)} candidates to review)')


if __name__ == '__main__':
    main()
