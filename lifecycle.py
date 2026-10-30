"""Conservative, public NumPy np.bool lifecycle demonstration.

A policy state (available/deprecated/removed) and a task-level semantic
contract are separate outputs. No network, models, eval, or target import.
This is a narrow fixture-level AST scanner, not a whole-program analysis.
"""
from __future__ import annotations
import ast
from dataclasses import dataclass, asdict
from typing import Literal
from benchmark.guardian_d2 import version_tuple, cmp_version

@dataclass(frozen=True)
class Segment:
    from_version: str
    before_version: str | None
    state: str
    semantic: str

NP_BOOL = (
    Segment('1.20.0', '1.24.0', 'DEPRECATED_AVAILABLE', 'python_builtin_bool_alias'),
    Segment('1.24.0', '2.0.0', 'REMOVED', 'unavailable'),
    # Explicitly bounded: avoid asserting that future, unreviewed major/minor versions are known.
    Segment('2.0.0', '2.6.0', 'ACTIVE', 'numpy_boolean_scalar'),
)
OFFICIAL_SOURCES = (
    'https://numpy.org/doc/2.0/release/1.24.0-notes.html',
    'https://numpy.org/doc/2.0/release/2.0.0-notes.html',
)


def find_segment(version: str) -> Segment | None:
    v = version_tuple(version)
    if v is None:
        return None
    for segment in NP_BOOL:
        lower = version_tuple(segment.from_version)
        upper = version_tuple(segment.before_version) if segment.before_version else None
        if cmp_version(v, lower) and (upper is None or not cmp_version(v, upper)):
            return segment
    return None


def scan_np_bool(code: str) -> str:
    """MATCH, NO_MATCH, AMBIGUOUS, INVALID_SYNTAX.

    Only direct imported NumPy aliases without assignment/rebinding count.
    Ambiguous use conservatively abstains; cannot certify arbitrary aliases.
    """
    if not isinstance(code, str):
        return 'INVALID_SYNTAX'
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 'INVALID_SYNTAX'
    aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'numpy':
                    aliases.add(alias.asname or 'numpy')
    matches = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute)
               and n.attr == 'bool' and isinstance(n.value, ast.Name)]
    if not matches:
        return 'NO_MATCH'
    if not aliases or any(n.value.id not in aliases for n in matches):
        return 'AMBIGUOUS'
    # Any rebinding or star import makes this narrow scanner unsafe to certify.
    rebound = any((isinstance(n, ast.Name) and n.id in aliases and isinstance(n.ctx, (ast.Store, ast.Del)))
                  or (isinstance(n, ast.arg) and n.arg in aliases) for n in ast.walk(tree))
    return 'AMBIGUOUS' if rebound else 'MATCH'


def assess_np_bool(code: str, version: str,
                   semantic_contract: Literal['existence_only', 'json_builtin_bool'] = 'existence_only') -> dict:
    scan = scan_np_bool(code)
    segment = find_segment(version)
    base = {'symbol': 'numpy.bool', 'target_version': version,
            'scan': scan, 'source_urls': list(OFFICIAL_SOURCES),
            'evidence_kind': 'OFFICIAL_RELEASE_NOTE_VERSION_RULE',
            'semantic_contract': semantic_contract,
            'decision': 'ABSTAIN', 'availability': 'UNKNOWN',
            'semantic_compatibility': 'UNKNOWN', 'reason': 'unknown_or_ambiguous'}
    if scan == 'NO_MATCH':
        base.update(decision='PASS', reason='no_target_symbol_seen')
        return base
    if scan != 'MATCH':
        base['reason'] = 'ambiguous_or_invalid_AST'
        return base
    if segment is None:
        base['reason'] = 'version_uncovered_by_policy'
        return base
    base.update(availability=segment.state, version_segment=asdict(segment))
    if segment.state == 'REMOVED':
        base.update(decision='ABSTAIN', semantic_compatibility='NOT_APPLICABLE', reason='removed_in_target_version')
        return base
    if semantic_contract == 'json_builtin_bool':
        compatible = segment.semantic == 'python_builtin_bool_alias'
        base['semantic_compatibility'] = 'COMPATIBLE' if compatible else 'INCOMPATIBLE'
        if not compatible:
            base.update(decision='ABSTAIN', reason='numpy_scalar_not_directly_json_serializable')
            return base
    elif semantic_contract == 'existence_only':
        base['semantic_compatibility'] = 'NOT_ASSESSED'
    else:
        base['reason'] = 'unsupported_semantic_contract'
        return base
    base['decision'] = 'WARN' if segment.state == 'DEPRECATED_AVAILABLE' else 'PASS'
    base['reason'] = 'known_segment_and_contract'
    return base
