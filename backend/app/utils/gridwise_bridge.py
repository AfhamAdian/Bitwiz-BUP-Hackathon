"""Makes the top-level `gridwise` package importable from the backend service.

`gridwise` (optimizer + validator + directive resolution) lives as a sibling
package at the repo root, next to `backend/`, and is already tested by the
root-level pytest suite. Import this module before importing `gridwise`.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
