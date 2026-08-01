#!/usr/bin/env python3

"""
ForeFlight content pack scaffolding, shared by the tools that emit packs.

A content pack is a directory (ForeFlight also accepts it zipped) holding an
optional ``manifest.json`` plus up to three well-known subdirectories:

  layers/   georeferenced charts (mbtiles) and KML map layers
  navdata/  user waypoint CSVs and the PDFs they link to
  byop/     "bring your own plates" PDFs

Every KML file in ``layers/`` becomes its own independently toggleable entry in
ForeFlight's map layer list — which is why a tool that wants "boundary line"
and "shaded area" as separate switches ships them as two files rather than two
placemarks in one file.

Manifest fields are all optional as far as ForeFlight is concerned; the version
is what the app uses to notice that a reinstalled pack is newer, so the usual
workflow is to keep the number monotonic via ``adopt_version(next_version=True)``.
"""

import datetime
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ContentPack:
    """A ForeFlight content pack directory being created or refreshed."""

    LAYERS = 'layers'
    NAVDATA = 'navdata'
    BYOP = 'byop'

    def __init__(
        self,
        path,
        name: str,
        abbreviation: str,
        organization: str = 'flyfun.aero',
        version: int = 1,
    ):
        """
        Args:
            path: Directory for the pack (created if missing)
            name: Human readable pack name shown in ForeFlight
            abbreviation: Short tag ForeFlight shows against pack content
            organization: Publisher name
            version: Version to use when the pack does not exist yet
        """
        self.path = Path(path)
        self.name = name
        self.abbreviation = abbreviation
        self.organization = organization
        self.version = version
        self.path.mkdir(parents=True, exist_ok=True)

    @property
    def manifest_path(self) -> Path:
        return self.path / 'manifest.json'

    def subdir(self, which: str) -> Path:
        """Return one of the well-known subdirectories, creating it on demand."""
        if which not in (self.LAYERS, self.NAVDATA, self.BYOP):
            raise ValueError(f'Not a ForeFlight content pack subdirectory: {which}')
        directory = self.path / which
        directory.mkdir(exist_ok=True)
        return directory

    def existing_version(self) -> Optional[int]:
        """Version recorded in an already-present manifest, if any."""
        if not self.manifest_path.exists():
            return None
        with open(self.manifest_path, 'r') as f:
            return json.load(f).get('version')

    def adopt_version(self, next_version: bool = False) -> bool:
        """
        Take the version from an existing manifest, optionally incrementing it.

        Returns True when the version was incremented, so callers that encode
        the version into the abbreviation can update it.
        """
        existing = self.existing_version()
        if existing is None:
            return False
        self.version = existing
        if not next_version:
            return False
        self.version += 1
        logger.info(f'Incrementing version to {self.version}')
        return True

    def write_manifest(self, expiration_days: int = 365) -> dict:
        """Write manifest.json, dated from now, and return what was written."""
        now = datetime.datetime.now()
        manifest = {
            'name': self.name,
            'abbreviation': self.abbreviation,
            'version': self.version,
            'organizationName': self.organization,
            'effectiveDate': now.isoformat(),
            'expirationDate': (now + datetime.timedelta(days=int(expiration_days))).isoformat(),
        }
        with open(self.manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        logger.info(f'Writing {self.manifest_path}')
        return manifest
