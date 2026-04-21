"""`dotfile ids` — print registered entry IDs, one per line."""

from dotgarden import config
from dotgarden import registry as reg


def cmd_ids(args):
    """Print registered entry IDs, one per line."""
    cfg = config.defaults()
    registry = reg.load(cfg['registry_path'])
    for entry in registry['registered_files']:
        print(entry['id'])
