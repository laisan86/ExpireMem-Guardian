"""Two controlled, offline pandas demos: legacy removal and silent row overwrite.

No user-provided code is executed and no provider is called.  The frozen
v0.3 core is imported but never modified.  Case A's *new* gapped-index fixture
is independent of the earlier real Baseten receipt.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any

import pandas as pd
from packaging.version import Version
from core.guardian_core import (deterministic_expression, inspect_source,
                                run_in_same_environment, validate_candidate_expression,
                                version_gate)

# Four original rows: filtering out index label 2 leaves labels [0, 1, 3].
# The row with id=4 at index 3 must never be silently replaced.
SHARED_SETUP = '''import json
import pandas as pd
df = pd.DataFrame([
    {"id": 1, "name": "a"},
    {"id": 2, "name": "b"},
    {"id": 3, "name": "c"},
    {"id": 4, "name": "d"},
])
df = df[df["id"] != 3].copy()
assert df.index.tolist() == [0, 1, 3]
before_records = df.to_dict(orient="records")
before_index = df.index.tolist()
'''
EXPECTED_ORIGINAL = [{'id': 1, 'name': 'a'}, {'id': 2, 'name': 'b'}, {'id': 4, 'name': 'd'}]
EXPECTED_APPEND = {'id': 7, 'name': 'carol'}
EXPECTED_ALL = EXPECTED_ORIGINAL + [EXPECTED_APPEND]

# Case A: existing public API-deprecation story, strengthened with a gapped index.
# Preserve v0.3's own fixture unchanged so its historical SHA256 remains valid.
CASE_A_GAPPED_SOURCE = SHARED_SETUP + '''df = df.append({"id": 7, "name": "carol"}, ignore_index=True)
print("CASE_A_ROWS=" + json.dumps(df.to_dict(orient="records")))
'''

# Case C: exact P8-observed pattern, replayed with a more adversarial dataframe.
# These are frozen expressions, not arbitrary code passed in from a model or UI.
FROZEN_CANDIDATES = {
    'silent_loc_dict': "df.loc[len(df)] = {'id': 7, 'name': 'carol'}",
    'silent_loc_list': "df.loc[len(df)] = [7, 'carol']",
    'correct_concat': (
        "df = pd.concat(\n"
        "    [df, pd.DataFrame([\n"
        "        {'id': 7, 'name': 'carol'}\n"
        "    ])],\n"
        "    ignore_index=True,\n"
        ")"
    ),
}


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def _case_a_patch(source: str) -> tuple[str, str]:
    """Offline AST replacement using frozen core's narrow candidate validator."""
    expression = deterministic_expression(source)
    candidate = validate_candidate_expression(source, expression)
    tree = ast.parse(source)
    targets = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute) and n.func.attr == 'append']
    if len(targets) != 1:
        raise ValueError('Case A requires exactly one append call')

    class Once(ast.NodeTransformer):
        count = 0

        def visit_Call(self, node):
            if node is targets[0]:
                self.count += 1
                return ast.copy_location(ast.parse(candidate['expression'], mode='eval').body, node)
            return self.generic_visit(node)

    transformer = Once()
    replacement = ast.unparse(ast.fix_missing_locations(transformer.visit(tree))) + '\n'
    if transformer.count != 1:
        raise ValueError('Expected exactly one AST rewrite')
    compile(replacement, '<controlled-gap-case-a>', 'exec')
    if version_gate(replacement, pd.__version__)['decision'] != 'PASS':
        raise ValueError('Patched source still blocked by removal version gate')
    return expression, replacement


def run_case_a_gapped() -> dict[str, Any]:
    """Genuine RED/Green under this interpreter, but explicitly OFFLINE replay."""
    if Version(pd.__version__) < Version('2.0.0'):
        return {'case': 'A_GAPPED', 'outcome': 'NOT_RUN', 'reason': 'Requires pandas >= 2.0',
                'model_requests': 0}
    gate = version_gate(CASE_A_GAPPED_SOURCE, pd.__version__)
    if gate['decision'] != 'ABSTAIN' or not inspect_source(CASE_A_GAPPED_SOURCE)['recognized']:
        raise AssertionError('Expected a recognized removed .append fixture')
    expr, replacement = _case_a_patch(CASE_A_GAPPED_SOURCE)
    with TemporaryDirectory(prefix='guardian_gap_case_a_') as td:
        root = Path(td)
        before, after = root/'case_a_removed.py', root/'case_a_concat.py'
        before.write_text(CASE_A_GAPPED_SOURCE, encoding='utf-8')
        after.write_text(replacement, encoding='utf-8')
        red = run_in_same_environment(before)
        green = run_in_same_environment(after)
    red_ok = red['returncode'] != 0 and 'AttributeError' in red['stderr'] and 'append' in red['stderr']
    green_rows = None
    for line in green['stdout'].splitlines():
        if line.startswith('CASE_A_ROWS='):
            green_rows = json.loads(line.split('=', 1)[1])
    green_ok = green['returncode'] == 0 and green_rows == EXPECTED_ALL
    return {'case': 'A_GAPPED', 'outcome': 'GREEN_OFFLINE_GAPPED' if red_ok and green_ok else 'ABSTAIN',
            'pandas_version': pd.__version__, 'python_executable': sys.executable,
            'mode': 'CONTROLLED_OFFLINE_FIXTURE', 'model_requests': 0,
            'prior_real_baseten_receipt_reused': False,
            'prior_v03_core_modified': False,
            'official_refresh': 'NOT_REQUESTED_OFFLINE',
            'before_index': [0, 1, 3], 'before_rows': EXPECTED_ORIGINAL,
            'version_gate_before': gate['decision'], 'candidate_shape': expr,
            'ast_whitelist': 'PASS', 'version_gate_after': 'PASS',
            'red': {'exit_code': red['returncode'], 'confirmed': red_ok,
                    'stderr_excerpt': red['stderr'][-1200:]},
            'green': {'exit_code': green['returncode'], 'verified_rows': green_rows,
                      'postcondition_pass': green_ok},
            'source_sha256': _sha(CASE_A_GAPPED_SOURCE),
            'patch_sha256': _sha(replacement)}


def _case_c_fixture(candidate: str) -> str:
    if candidate not in FROZEN_CANDIDATES:
        raise ValueError('Only fixed public-case variants are executable')
    return SHARED_SETUP + FROZEN_CANDIDATES[candidate] + '''\nprint("CASE_C_OBSERVATION=" + json.dumps({
    "index_before": before_index,
    "index_after": df.index.tolist(),
    "original_rows": before_records,
    "rows_after": df.to_dict(orient="records"),
}, ensure_ascii=False))
'''


def run_case_c() -> dict[str, Any]:
    """Show exit=0 + static PASS can still violate independent row preservation.

    The task-level oracle lives in the parent process; the executed fixture
    cannot define or self-attest its own success criteria.
    """
    if Version(pd.__version__) < Version('2.0.0'):
        return {'case': 'C_SILENT_OVERWRITE', 'outcome': 'NOT_RUN',
                'reason': 'Requires pandas >= 2.0', 'model_requests': 0}
    outcomes = []
    with TemporaryDirectory(prefix='guardian_gap_case_c_') as td:
        root = Path(td)
        for name in FROZEN_CANDIDATES:
            source = _case_c_fixture(name)
            # Static syntax and narrow removed-API check, NOT v0.3 patch whitelist.
            ast.parse(source)
            gate = version_gate(source, pd.__version__)
            file = root / f'{name}.py'
            file.write_text(source, encoding='utf-8')
            observed = run_in_same_environment(file)
            snapshot = None
            for line in observed['stdout'].splitlines():
                if line.startswith('CASE_C_OBSERVATION='):
                    snapshot = json.loads(line.split('=', 1)[1])
            original_preserved = (isinstance(snapshot, dict)
                                  and snapshot.get('original_rows') == EXPECTED_ORIGINAL
                                  and snapshot.get('rows_after', [])[:3] == EXPECTED_ORIGINAL)
            exactly_one_added = (isinstance(snapshot, dict)
                                 and snapshot.get('rows_after') == EXPECTED_ALL)
            semantics_ok = (observed['returncode'] == 0 and original_preserved and exactly_one_added)
            outcomes.append({
                'candidate': name,
                'p8_observed_candidate_shape': name.startswith('silent_loc'),
                'candidate_code': FROZEN_CANDIDATES[name],
                'candidate_sha256': _sha(FROZEN_CANDIDATES[name]),
                'syntax_check': 'PASS',
                'removed_api_version_gate': gate['decision'],
                'v03_repair_ast_whitelist': 'NOT_APPLICABLE (different task/contract)',
                'subprocess_exit_code': observed['returncode'],
                'would_pass_exit_code_only': observed['returncode'] == 0,
                'row_count_before': 3,
                'row_count_after': len(snapshot['rows_after']) if snapshot else None,
                'index_before': snapshot.get('index_before') if snapshot else None,
                'index_after': snapshot.get('index_after') if snapshot else None,
                'preserves_original_rows': bool(original_preserved),
                'appends_exact_task_row': bool(exactly_one_added),
                'task_oracle': 'PASS' if semantics_ok else 'FAIL',
                'guardian_candidate_accepted': bool(semantics_ok),
                'rows_after': snapshot.get('rows_after') if snapshot else None,
                'source_sha256': _sha(source),
                'stderr_excerpt': observed['stderr'][-500:]
            })
    return {'case': 'C_SILENT_OVERWRITE', 'outcome': 'OFFLINE_SEMANTIC_ORACLE_EVALUATED',
            'pandas_version': pd.__version__, 'python_executable': sys.executable,
            'model_requests': 0, 'official_refresh': 'NOT_REQUESTED_OFFLINE',
            'p8_behavior': 'Candidate shapes from P8 C1 NO_DOC; independently replayed on gapped-index fixture',
            'before_index': [0, 1, 3], 'before_rows': EXPECTED_ORIGINAL,
            'task_row': EXPECTED_APPEND,
            'contract': 'Preserve original rows and order; append one exact task row',
            'tested_candidates': outcomes,
            'caution': 'Narrow removed-API gate PASS is not general static safety; ' 
                       'a fixed external execution oracle, not exit code alone, detects data loss.'}


def run_both() -> dict[str, Any]:
    a = run_case_a_gapped()
    c = run_case_c()
    return {'schema': 'd3-gap-index-0.1', 'case_a': a, 'case_c': c}


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='Controlled offline gapped-index execution oracle')
    p.add_argument('--out', help='Optional LOCAL report JSON path; no network or model calls')
    args = p.parse_args()
    report = run_both()
    if args.out:
        out = Path(args.out)
        if out.exists():
            raise SystemExit('Refusing to overwrite an existing report')
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))
