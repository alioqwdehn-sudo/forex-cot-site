"""Public review policy: immutable source revisions and pinned original API rows."""
import hashlib
import json
import math
import struct

# Intentionally empty until a separately reviewed activation commit is known.
# Never resolve a branch/tag or accept a workflow input as approval.
APPROVED_SOURCE_COMMITS = frozenset()
BASELINE_ROWS = 91
BASELINE_FINGERPRINTS = {
    'AUD':'bc96e63b943158796d2ec49c9fcf873949cf9941cffaaf77bd6e3be33c82015a',
    'GBP':'b10caf9363c72629f66659a4e511c05be1fba8861f8e61e01aa23854e30c0260',
    'CAD':'e81a7624b02aa6215b64a41fca5b40a4d2cb8abf0a2e0a459f45a6bb5f1fb1b4',
    'EUR':'31af9d8a5a5db3869554ca2f310410731f4b68e803f49b8f0a2e3f97a327443b',
    'JPY':'a65554ff1b041e33e14f4ca62a36da671611f79f138d266ab63988e655265435',
    'NZD':'8ad6d1672e20c8ff0c54f9dc2a15de6d2d114675a7c80c977cccf23dd1f8ea31',
    'CHF':'a05160da4b4a1054527a97a67c67fcd69c3ee2ebb379a78478c1778c73ae3ecf',
    'BRL':'83d89940eeda1ef3af0e683f1191fc7fa7f84d3c22d95c35224dd08cb1d36326',
    'MXN':'c444d80ab11c5ba9e0ec4c67356121270a09fa859be393533ae2de112fdb9033',
    'ZAR':'1b0a44abeef252a3000750920d6508d78c895eb9cc1fae5073358b49528b33ac',
}


def fingerprint(value):
    # Canonical IEEE-754 encoding treats JSON 1 and 1.0 identically without
    # rounding financial fields. Keys sorted; nulls preserved; no private schema.
    def canonical(v):
        if type(v) in (int,float):
            if not math.isfinite(v): raise ValueError('Non-finite baseline number')
            return ['number',struct.pack('>d',float(v)).hex()]
        if isinstance(v,dict): return {k:canonical(v[k]) for k in sorted(v)}
        if isinstance(v,list): return [canonical(x) for x in v]
        if v is None or isinstance(v,str): return v
        raise ValueError('Unexpected baseline type')
    return hashlib.sha256(json.dumps(canonical(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def verify_baseline(site,read_json,currencies):
    if set(BASELINE_FINGERPRINTS)!=set(currencies): raise ValueError('Incomplete baseline policy')
    for currency in currencies:
        rows=read_json(site/f'data/cot/{currency}.json')['data']
        if len(rows)<BASELINE_ROWS or fingerprint(rows[-BASELINE_ROWS:])!=BASELINE_FINGERPRINTS[currency]:
            raise ValueError('Pinned original history fingerprint mismatch')
