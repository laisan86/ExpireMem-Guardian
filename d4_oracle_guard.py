"""Guarded, independently calibrated D4 task-oracle proposals.

A model may propose a *pure, bounded predicate*, never arbitrary Python.  An
offline reference predicate is provided solely for transport-free testing.
No HTTP calls, no provider attribution and no general-purpose sandbox.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from gap_index_cases import EXPECTED_ORIGINAL, EXPECTED_APPEND, EXPECTED_ALL

REFERENCE_ORACLE = '''def verify_postcondition(before_rows, after_rows, task_row):
    return (
        len(after_rows) == len(before_rows) + 1
        and after_rows[:-1] == before_rows
        and after_rows[-1] == task_row
    )'''

TASK_CONTRACT = (
    'Append exactly the user-specified row. Preserve every original row, '
    'its field values and its relative order. Add exactly one row at the end.'
)

class OracleRejected(ValueError):
    pass


@dataclass(frozen=True)
class FrozenWitness:
    witness_id: str
    before_rows: list[dict]
    after_rows: list[dict]
    target_row: dict
    expected: bool


def frozen_witnesses() -> tuple[FrozenWitness, ...]:
    """Fixtures fixed independently of the candidate oracle and its generation."""
    original = deepcopy(EXPECTED_ORIGINAL)
    target = deepcopy(EXPECTED_APPEND)
    good = deepcopy(EXPECTED_ALL)
    bad_overwrite = deepcopy(original)
    bad_overwrite[-1] = deepcopy(target)
    bad_mutated = deepcopy(good)
    bad_mutated[1] = {'id': 2, 'name': 'tampered'}
    # Separate mutations at every original-row position stop positional overfitting.
    bad_mutated_first = deepcopy(good)
    bad_mutated_first[0] = {**bad_mutated_first[0], 'name': 'tampered_head'}
    bad_mutated_last = deepcopy(good)
    bad_mutated_last[-2] = {**bad_mutated_last[-2], 'name': 'tampered_tail'}
    bad_dropped_head = deepcopy(original[1:]) + [deepcopy(target)]
    bad_prepended = [deepcopy(target)] + deepcopy(original)
    bad_middle_insert = [deepcopy(original[0]), deepcopy(target)] + deepcopy(original[1:])
    bad_wrong_tail = deepcopy(original) + [{'id': 999, 'name': 'sample'}]
    bad_reordered = [deepcopy(original[1]), deepcopy(original[0]), deepcopy(original[2]), deepcopy(target)]
    before2 = [{'id': 11, 'name': 'oak'}, {'id': 21, 'name': 'pine'}]
    task2 = {'id': 31, 'name': 'birch'}
    before3 = [{'key': 'alpha', 'enabled': True}, {'key': 'beta', 'enabled': False}]
    task3 = {'key': 'gamma', 'enabled': True}
    return (
        FrozenWitness('positive_gap_rows', original, good, target, True),
        FrozenWitness('negative_silent_overwrite', original, bad_overwrite, target, False),
        FrozenWitness('negative_mutated_existing_row', original, bad_mutated, target, False),
        FrozenWitness('negative_mutated_first_row', original, bad_mutated_first, target, False),
        FrozenWitness('negative_mutated_last_original_row', original, bad_mutated_last, target, False),
        FrozenWitness('negative_dropped_head_shifted', original, bad_dropped_head, target, False),
        FrozenWitness('negative_prepended_task_row', original, bad_prepended, target, False),
        FrozenWitness('negative_middle_inserted_task_row', original, bad_middle_insert, target, False),
        FrozenWitness('negative_wrong_task_value', original, bad_wrong_tail, target, False),
        FrozenWitness('negative_reordered_existing_rows', original, bad_reordered, target, False),
        FrozenWitness('negative_extra_row', original, good + [target], target, False),
        FrozenWitness('negative_missing_row', original, original, target, False),
        FrozenWitness('positive_different_values', before2, before2 + [task2], task2, True),
        FrozenWitness('negative_other_data_copy', before2, before2 + [{'id': 31, 'name': 'maple'}], task2, False),
        FrozenWitness('positive_other_schema', before3, before3 + [task3], task3, True),
        FrozenWitness('negative_other_schema_overwrite', before3, [before3[0], task3], task3, False),
    )


def _validate_ast(source: str) -> ast.expr:
    if not isinstance(source, str) or len(source.encode('utf-8')) > 1600:
        raise OracleRejected('Source must be bounded UTF-8 text (max 1600 bytes)')
    try:
        tree = ast.parse(source, mode='exec')
    except SyntaxError as exc:
        raise OracleRejected('Oracle syntax error') from exc
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise OracleRejected('Exactly one function is required')
    fn = tree.body[0]
    if fn.name != 'verify_postcondition' or fn.decorator_list or fn.returns is not None:
        raise OracleRejected('Only undecorated verify_postcondition is allowed')
    args = fn.args
    if (len(args.args) != 3 or [x.arg for x in args.args] !=
        ['before_rows', 'after_rows', 'task_row'] or
        args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or args.defaults or
        args.kw_defaults or any(x.annotation for x in args.args)):
        raise OracleRejected('Oracle signature must match task contract')
    if len(fn.body) != 1 or not isinstance(fn.body[0], ast.Return) or fn.body[0].value is None:
        raise OracleRejected('Only a single return expression is permitted')
    expr = fn.body[0].value
    nodes = list(ast.walk(expr))
    if len(nodes) > 78:
        raise OracleRejected('Expression complexity bound exceeded')
    # Only conjunction, not disjunction/negation. This is NOT a proof of semantics.
    allowed = (ast.BoolOp, ast.And, ast.UnaryOp, ast.Compare,
               ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
               ast.BinOp, ast.Add, ast.Sub, ast.USub, ast.Name, ast.Load, ast.Constant,
               ast.Subscript, ast.Slice, ast.Call, ast.List, ast.Tuple)
    seen = set()
    addition_count = 0
    for node in nodes:
        if not isinstance(node, allowed):
            raise OracleRejected('Forbidden AST node: ' + type(node).__name__)
        if isinstance(node, ast.Name):
            if node.id not in ('before_rows', 'after_rows', 'task_row', 'len'):
                raise OracleRejected('Unknown name in predicate')
            seen.add(node.id)
        if isinstance(node, ast.Call):
            if (not isinstance(node.func, ast.Name) or node.func.id != 'len' or
                    len(node.args) != 1 or node.keywords):
                raise OracleRejected('Only len(x) is allowed')
        if isinstance(node, ast.Constant):
            if node.value is not None and type(node.value) not in (bool, int):
                raise OracleRejected('String literals and other constants are forbidden')
            if type(node.value) is int and not (-1 <= node.value <= 1):
                raise OracleRejected('Large numeric or witness-specific constants denied')
        if isinstance(node, ast.BinOp):
            addition_count += 1
            if addition_count > 2:
                raise OracleRejected('Arithmetic/list concatenation complexity exceeded')
        if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) > 1:
            raise OracleRejected('Only empty or singleton literals are allowed')
    # A blanket ban on `or` / `not` is insufficient: Boolean comparisons
    # such as `(A and B) == False` reconstruct disjunction via De Morgan.
    # Require conjunctions whose leaves are atomic comparisons over data
    # expressions; no Boolean expression or comparison may be an operand
    # of another comparison. This is a syntactic restriction, not an
    # equivalence proof for all possible inputs.
    def require_conjunction_of_comparisons(node: ast.AST) -> None:
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            for clause in node.values:
                require_conjunction_of_comparisons(clause)
            return
        if isinstance(node, ast.Compare):
            for operand in (node.left, *node.comparators):
                if any(isinstance(sub, (ast.BoolOp, ast.Compare))
                       for sub in ast.walk(operand)):
                    raise OracleRejected('Boolean result cannot be compared or negated')
            return
        raise OracleRejected('Only AND-connected comparisons are allowed')
    require_conjunction_of_comparisons(expr)
    if not {'before_rows', 'after_rows', 'task_row'} <= seen:
        raise OracleRejected('Predicate must use all three contract inputs')
    return expr


def guarded_predicate(source: str):
    expr = _validate_ast(source)
    compiled = compile(ast.Expression(body=expr), '<bounded-oracle-expression>', 'eval')

    def run(before_rows, after_rows, task_row):
        # The model never receives objects with attributes or callables.
        for value in (before_rows, after_rows):
            if not isinstance(value, list) or len(value) > 32 or not all(isinstance(row,dict) for row in value):
                raise OracleRejected('Unsafe/oversized witness')
        if not isinstance(task_row,dict):
            raise OracleRejected('Task row must be a record')
        scope={'before_rows':deepcopy(before_rows), 'after_rows':deepcopy(after_rows),
               'task_row':deepcopy(task_row)}
        result=eval(compiled, {'__builtins__':{}, 'len':len}, scope)
        if type(result) is not bool:
            raise OracleRejected('Predicate must return an actual bool')
        return result

    return run


def review_oracle(source: str, provenance: str='UNTRUSTED_PROPOSAL_OFFLINE') -> dict[str, Any]:
    """Never validates against a not-yet-evaluated candidate for oracle acceptance."""
    sha = hashlib.sha256(source.encode('utf-8')).hexdigest() if isinstance(source,str) else None
    result={'schema':'guardian_d4_oracle_review_v1', 'status':'REJECTED',
            'provenance':provenance, 'oracle_sha256':sha,
            'model_requests':0, 'calibration_witnesses_frozen':True,
            'eligible_as_general_purpose_sandbox':False,
            'evaluations':[]}
    try:
        fn=guarded_predicate(source)
        for case in frozen_witnesses():
            actual=fn(case.before_rows,case.after_rows,case.target_row)
            result['evaluations'].append({'witness_id':case.witness_id,
                'expected':case.expected, 'actual':actual, 'pass':actual is case.expected})
        if all(r['pass'] for r in result['evaluations']):
            result['status']='VALIDATED_ON_FROZEN_WITNESSES'
        else:
            result['reason']='Could not separate independently frozen correct/bad examples'
    except (OracleRejected,ValueError,TypeError,IndexError,ArithmeticError,RecursionError,MemoryError) as exc:
        result['reason']=f'{type(exc).__name__}: {str(exc)[:180]}'
    return result


def review_reference() -> dict[str, Any]:
    return review_oracle(REFERENCE_ORACLE,'HANDWRITTEN_REFERENCE_NO_MODEL')


def prompt_for_model() -> str:
    """The provider is not shown labeled evaluation witnesses."""
    return ("You are proposing a pure Python task postcondition for a coding agent.\n"
      "Task: " + TASK_CONTRACT + "\n"
      "Return ONLY one Python function, named exactly\n"
      "def verify_postcondition(before_rows, after_rows, task_row):\n"
      "with one return expression. The inputs are JSON-like list-of-dict records, "
      "target row is a dict. Use only conjunctions of comparisons, list equality, "
      "slices, indexing, len(), bounded + or - arithmetic; no imports, loops, "
      "attributes, comprehensions, string literals, or other functions. "
      "Use 'and' to combine conditions; NEVER use 'or' or 'not'. "
      "Do not compare a Boolean expression or comparison result to anything "
      "(including True, False, 0, or 1). Each 'and' term must be an atomic "
      "comparison of data, lengths, or slices. "
      "Do not assume contiguous DataFrame indices. "
      "Do not use hardcoded field names or data values. "
      "You MUST check preservation of all prior records and order, exactly one "
      "additional row, and equality to the task's requested row.\n")



# MODEL TEXT TRANSPORT DECODING; never broadens the predicate AST allowlist.
# The full raw provider JSON is persisted by the caller BEFORE invoking review.
_FENCED_CODE = re.compile(r'```(?P<lang>[A-Za-z0-9_+\-]*)[ \t]*\r?\n(?P<body>.*?)```', re.S)
_DEF_LINE = re.compile(r'(?m)^def[ \t]+verify_postcondition[ \t]*\(')
_OTHER_CODE = re.compile(
    r'^(?:def\s|class\s|import\s|from\s|@|async\s|if\s|for\s|while\s|'
    r'try\s*:|with\s|return\s|raise\s|assert\s|print\s*\(|'
    r'[A-Za-z_][A-Za-z_0-9]*\s*(?:=|\())'
)


def _looks_executable_text(line: str) -> bool:
    """Conservatively deny syntax-like top-level code in apparent prose."""
    stripped=line.strip()
    if not stripped or stripped.startswith('#'):
        return False
    if _OTHER_CODE.match(stripped):
        return True
    try:
        tree=ast.parse(stripped, mode='exec')
    except SyntaxError:
        return False
    return bool(tree.body)


def _extract_function_region(text: str, *, permit_explanation: bool) -> tuple[str, str]:
    """Extract one top-level function, deny another executable top-level block."""
    starts=list(_DEF_LINE.finditer(text))
    if len(starts) != 1:
        raise OracleRejected('Exactly one verify_postcondition definition required')
    start=starts[0].start()
    leading=text[:start]
    if leading.strip() and not permit_explanation:
        raise OracleRejected('Code fence must contain only the function')
    # A prefix can be natural language, but never executable Python statements.
    if leading.strip() and any(_looks_executable_text(line) for line in leading.splitlines()):
        raise OracleRejected('Executable preamble denied')
    lines=text[start:].splitlines()
    kept=[lines[0]]
    rest=[]
    in_rest=False
    for line in lines[1:]:
        if not in_rest and (not line.strip() or line[:1].isspace()):
            kept.append(line)
        else:
            in_rest=True
            rest.append(line)
    trailing='\n'.join(rest).strip()
    if trailing:
        if not permit_explanation:
            raise OracleRejected('Unexpected trailing text inside code block')
        if any(_looks_executable_text(line) or line[:1].isspace() for line in rest if line.strip()):
            raise OracleRejected('Executable or indented trailing content denied')
    candidate='\n'.join(kept).rstrip()
    if not candidate:
        raise OracleRejected('Empty oracle body')
    return candidate, ('TRIMMED' if leading.strip() or trailing else 'VERBATIM')


def extract_oracle_source(raw_text: str) -> tuple[str, str]:
    """Normalize common provider presentation wrappers, not executable meaning.

    Any second code fence, unclosed fence, top-level executable preamble/suffix,
    or multiple definitions is rejected rather than silently discarded.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise OracleRejected('Empty or non-text response')
    if len(raw_text.encode('utf-8')) > 16000:
        raise OracleRejected('Raw response exceeds transport size limit')
    text=raw_text.strip()
    if '```' in text:
        fences=list(_FENCED_CODE.finditer(text))
        if len(fences) != 1 or text.count('```') != 2:
            raise OracleRejected('Require one complete code fence, not multiple or broken fences')
        fence=fences[0]
        if fence.group('lang').lower() not in ('', 'python', 'py'):
            raise OracleRejected('Only Python code fences are allowed')
        outside=text[:fence.start()]+'\n'+text[fence.end():]
        if any(_OTHER_CODE.match(line.strip()) for line in outside.splitlines()):
            raise OracleRejected('Executable code outside fence denied')
        code, _ = _extract_function_region(fence.group('body').strip(), permit_explanation=False)
        return code, 'UNFENCED'
    code, note = _extract_function_region(text, permit_explanation=True)
    return code, note


def review_response_baseten(raw: dict) -> dict[str, Any]:
    """Decode supplied response only; not a live attestation."""
    from d4_model_adapters import BASETEN_MODEL, _usage_baseten, canon_hash
    if not isinstance(raw,dict) or raw.get('model')!=BASETEN_MODEL:
        raise OracleRejected('Model mismatch')
    choices=raw.get('choices')
    if not isinstance(choices,list) or len(choices)!=1 or choices[0].get('finish_reason')!='stop':
        raise OracleRejected('Incomplete response')
    content=choices[0].get('message',{}).get('content')
    if not isinstance(content,str) or not content.strip():
        raise OracleRejected('Missing oracle proposal')
    usage=_usage_baseten(raw)
    raw_content_sha=hashlib.sha256(content.encode('utf-8')).hexdigest()
    # Do not drop receipt metadata even if extraction/AST validation fails.
    report={'schema':'guardian_d4_oracle_review_v1','status':'REJECTED',
            'provenance':'SUPPLIED_BASETEN_RESPONSE_UNVERIFIED',
            'model_requests':0,'calibration_witnesses_frozen':True,
            'eligible_as_general_purpose_sandbox':False,'evaluations':[]}
    extraction='REJECTED'
    try:
        candidate,extraction=extract_oracle_source(content)
        report=review_oracle(candidate, 'SUPPLIED_BASETEN_RESPONSE_UNVERIFIED')
    except OracleRejected as exc:
        report['reason']='OracleRejected: '+str(exc)[:180]
        report['oracle_sha256']=None
    report.update({'response_sha256':canon_hash(raw), 'response_id':raw.get('id'),
                   'raw_content_sha256':raw_content_sha,
                   'extraction':extraction,
                   'model':raw['model'],'usage':usage})
    return report


if __name__ == '__main__':
    print(json.dumps(review_reference(),indent=2))
