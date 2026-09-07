"""Where the decryption keys come from — deliberately not from this file.

OMORI's map and image files are encrypted, and the two keys that open them are
the game's, not this project's. Publishing them alongside a public repository
would be handing out the means to unpack a commercial game, so they are read at
run time instead of written down here:

    OMORI_AUBREY_KEY / OMORI_RPGMVP_KEY   environment variables, or
    scripts/omori_keys.json               a local file, gitignored

Anyone with the game already has both keys inside their own copy — the AES one
is the Steam launch argument, the XOR one is `encryptionKey` in System.json —
so this is a speed bump for the curious, not a lock.

    {"aubrey": "<32 ASCII chars>", "rpgmvp": "<32 hex chars>"}
"""
import json
import os
import sys
from pathlib import Path

_LOCAL = Path(__file__).resolve().parent / 'omori_keys.json'
_HELP = (f'Put them in {_LOCAL.name} next to the scripts, or set OMORI_AUBREY_KEY '
         'and OMORI_RPGMVP_KEY. See the docstring in scripts/_keys.py.')


def _load():
    if _LOCAL.exists():
        try:
            return json.loads(_LOCAL.read_text())
        except Exception as exc:                        # noqa: BLE001
            sys.exit(f'{_LOCAL.name} is not readable JSON: {exc}')
    return {}


def aubrey_key():
    """The AES-256-CTR key for .AUBREY / .KEL / .HERO, as 32 ASCII bytes."""
    v = os.environ.get('OMORI_AUBREY_KEY') or _load().get('aubrey')
    if not v:
        sys.exit('No OMORI AES key. ' + _HELP)
    return v.encode() if isinstance(v, str) else v


def rpgmvp_key():
    """The XOR key for .rpgmvp image headers, as 16 bytes."""
    v = os.environ.get('OMORI_RPGMVP_KEY') or _load().get('rpgmvp')
    if not v:
        sys.exit('No OMORI rpgmvp key. ' + _HELP)
    return bytes.fromhex(v)
