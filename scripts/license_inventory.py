"""Record installed dependency versions and license declarations for release review."""
import argparse
import importlib.metadata as metadata
import json
from pathlib import Path


def inventory():
    rows = []
    for distribution in metadata.distributions():
        info = distribution.metadata
        declarations = info.get_all('Classifier') or []
        rows.append({
            'name': info.get('Name'), 'version': distribution.version,
            'license': info.get('License-Expression') or info.get('License') or 'review required',
            'license_classifiers': [c for c in declarations if c.startswith('License ::')],
            'declared_license_files': info.get_all('License-File') or [],
        })
    return {'commercial_distribution_cleared': False,
            'note': 'Metadata is inventory evidence only; it does not establish commercial license entitlement.',
            'dependencies': sorted(rows, key=lambda row: (row['name'] or '').lower())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path, nargs='?')
    parser.add_argument('--output', type=Path)
    arguments = parser.parse_args()
    output = arguments.output or arguments.destination
    if output is None:
        parser.error('provide a destination or --output path')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory(), ensure_ascii=False, indent=2), encoding='utf-8')
