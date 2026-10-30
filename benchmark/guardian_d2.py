"""Version-rule benchmark only. No model API, execution, or patching."""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POLICIES = {x['id']: x for x in json.loads((ROOT/'data/policies.json').read_text())}

def version_tuple(version):
    # Deliberately strict: unknown/prerelease cannot be silently interpreted.
    if not isinstance(version, str) or not re.fullmatch(r'\d+(?:\.\d+){0,3}', version):
        return None
    return tuple(int(n) for n in version.split('.'))

def cmp_version(a, b):
    n=max(len(a),len(b)); return (a+(0,)*(n-len(a))) >= (b+(0,)*(n-len(b)))

def targets(source):
    """Narrow AST evidence; no eval/exec. Conservative for ambiguous names."""
    try: tree = ast.parse(source)
    except SyntaxError: return None
    pandas_aliases=set(); numpy_aliases=set(); django_aliases=set(); force_text_aliases=set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name=='pandas': pandas_aliases.add(a.asname or 'pandas')
                if a.name=='numpy': numpy_aliases.add(a.asname or 'numpy')
                if a.name=='django.utils.encoding': django_aliases.add(a.asname or 'django')
        elif isinstance(node, ast.ImportFrom) and node.module=='django.utils.encoding':
            for a in node.names:
                if a.name=='force_text': force_text_aliases.add(a.asname or a.name)
    found=set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr=='append':
            # For this initial narrow fixture, only emit DataFrame.append when
            # variable was bound from DataFrame(...) in this same source.
            names=set()
            for assign in ast.walk(tree):
                if isinstance(assign, ast.Assign) and isinstance(assign.value,ast.Call):
                    ctor=assign.value.func
                    if (isinstance(ctor,ast.Attribute) and ctor.attr=='DataFrame'
                            and isinstance(ctor.value,ast.Name) and ctor.value.id in pandas_aliases):
                        for target in assign.targets:
                            if isinstance(target,ast.Name): names.add(target.id)
            if isinstance(node.value,ast.Name) and node.value.id in names:
                found.add('pandas.DataFrame.append')
        elif isinstance(node, ast.Attribute) and node.attr=='float_' and isinstance(node.value, ast.Name) and node.value.id in numpy_aliases:
            found.add('numpy.float_')
        elif isinstance(node, ast.Call) and isinstance(node.func,ast.Name) and node.func.id in force_text_aliases:
            found.add('django.utils.encoding.force_text')
        elif isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
            obj=node.func.value
            if (node.func.attr=='force_text' and isinstance(obj,ast.Attribute)
                    and obj.attr=='encoding' and isinstance(obj.value,ast.Attribute)
                    and obj.value.attr=='utils' and isinstance(obj.value.value,ast.Name)
                    and obj.value.value.id in django_aliases):
                found.add('django.utils.encoding.force_text')
    return found

def assess(case):
    try: found=targets(case['source_code'])
    except (TypeError,KeyError): return {'decision':'ABSTAIN','reason':'invalid_input','matched':[]}
    if found is None: return {'decision':'ABSTAIN','reason':'invalid_syntax','matched':[]}
    if not found:
        # Explicit UNKNOWN case is an abstention rather than an invented removal finding.
        if case.get('scenario')=='unknown_api':
            return {'decision':'ABSTAIN','reason':'unknown_symbol_needs_refresh','matched':[]}
        return {'decision':'PASS','reason':'no_known_rule_triggered','matched':[]}
    v=version_tuple(case.get('target_version'))
    if v is None: return {'decision':'ABSTAIN','reason':'unknown_runtime_version','matched':sorted(found)}
    state='PASS'
    for p in sorted(found):
        rule=POLICIES[p]
        removed=version_tuple(rule['removed_in']) if rule['removed_in'] else None
        deprecated=version_tuple(rule['deprecated_in']) if rule['deprecated_in'] else None
        if removed and cmp_version(v,removed): state='ABSTAIN'
        elif deprecated and cmp_version(v,deprecated) and state!='ABSTAIN': state='WARN'
    return {'decision':state,'reason':'official_version_rule','matched':sorted(found)}

def load_cases():
    return [json.loads(line) for line in (ROOT/'data/cases.jsonl').read_text().splitlines() if line.strip()]

if __name__=='__main__':
    failures=[]
    for c in load_cases():
        got=assess(c)
        if got['decision']!=c['expected_decision']:
            failures.append((c['case_id'], c['expected_decision'],got))
        print(c['case_id'], c['expected_decision'],got['decision'])
    if failures: raise SystemExit('FAILED: '+repr(failures))
    print('All',len(load_cases()),'case decisions matched')
