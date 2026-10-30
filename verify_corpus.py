"""Version-isolated, auditable public API ground-truth verifier.

No model/network access by default. --install explicitly authorizes pip wheel
installation in dedicated .venv directories. Only fixed allowlisted probe
kinds are executed. Never execute untrusted benchmark source_code.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PROBES = {
    'numpy.bool', 'numpy.float_', 'pandas.DataFrame.append',
    'django.utils.encoding.force_text'
}
SAFE_VERSION = re.compile(r'^\d+(?:\.\d+){1,3}$')
SAFE_PACKAGES = {'numpy', 'pandas', 'django'}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(data: bytes):
    return hashlib.sha256(data).hexdigest()


def load_manifest(path: Path):
    cases = []
    for i, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip(): continue
        c = json.loads(line)
        if not isinstance(c, dict) or not isinstance(c.get('case_id'), str):
            raise ValueError(f'bad case at line {i}')
        if c.get('probe_kind') is not None and c['probe_kind'] not in PROBES:
            raise ValueError(f'unapproved probe at line {i}')
        pkg = c.get('package')
        if pkg is not None and pkg not in SAFE_PACKAGES:
            raise ValueError(f'unapproved package at line {i}')
        version = c.get('target_version')
        if version is not None and not SAFE_VERSION.fullmatch(version):
            # Version strings unknown or unavailable are always NOT_RUN.
            c['unsupported_version'] = True
        cases.append(c)
    if len({c['case_id'] for c in cases}) != len(cases):
        raise ValueError('duplicate case_id')
    return cases


def invoke(command, *, timeout=45):
    # No shell, no user-provided source code, and no implicit model request.
    try:
        p = subprocess.run([str(v) for v in command], capture_output=True,
                           text=True, timeout=timeout, check=False,
                           env={**os.environ, 'PYTHONNOUSERSITE': '1', 'PIP_NO_INPUT': '1'})
        return {'returncode': p.returncode, 'stdout': p.stdout[:15000],
                'stderr': p.stderr[-3500:], 'timed_out': False}
    except subprocess.TimeoutExpired:
        return {'returncode': None, 'stdout': '', 'stderr': 'subprocess timed out', 'timed_out': True}


def environment_python(cache: Path, pkg: str, version: str):
    base = cache / f'{pkg}-{version}'
    return base / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def ensure_environment(python: str, cache: Path, pkg: str, version: str, allow_install: bool):
    exe = environment_python(cache, pkg, version)
    if exe.exists():
        return str(exe), {'status': 'CACHED_ENV'}
    if not allow_install:
        return None, {'status': 'NOT_INSTALLED', 'reason': 'pass --install to create a pinned environment'}
    base = exe.parent.parent
    base.parent.mkdir(parents=True, exist_ok=True)
    make = invoke([python, '-m', 'venv', str(base)], timeout=90)
    if make['returncode'] != 0:
        return None, {'status': 'ENV_SETUP_FAILED', 'detail': make}
    # --only-binary rejects unsupported Python / source builds rather than attempting to compile.
    install = invoke([str(exe), '-m', 'pip', 'install', '--only-binary=:all:',
                      '--disable-pip-version-check', '--no-input', f'{pkg}=={version}'], timeout=210)
    if install['returncode'] != 0:
        return None, {'status': 'PACKAGE_INSTALL_FAILED', 'detail': install}
    return str(exe), {'status': 'FRESH_ENV'}


def evaluate_case(case, observation, env_status):
    record = {'case_id': case['case_id'], 'package': case.get('package'),
              'target_version': case.get('target_version'),
              'probe_kind': case.get('probe_kind'),
              'expected_existence': case.get('expected_existence'),
              'expected_semantic_pass': case.get('expected_semantic_pass'),
              'evidence_urls': case.get('evidence_urls', []),
              'environment_status': env_status['status'],
              'verification_status': 'NOT_RUN', 'observation': None,
              'matches_expected': None}
    if case.get('probe_kind') is None:
        record['verification_status'] = 'STATIC_ONLY'
        return record
    if observation is None:
        record['reason'] = env_status.get('reason', env_status.get('status'))
        return record
    record['observation'] = observation
    if observation.get('actual_version') != case.get('target_version'):
        record.update(verification_status='VERSION_MISMATCH', reason='installed version differs from pinned target')
        return record
    expected_exists = case.get('expected_existence')
    exists = observation.get('existence')
    if not isinstance(expected_exists, bool) or not isinstance(exists, bool):
        record['verification_status'] = 'NOT_VERIFIABLE'
        return record
    existence_match = (exists == expected_exists)
    record['matches_expected'] = existence_match
    record['verification_status'] = 'VERIFIED_EXISTENCE' if existence_match else 'OBSERVED_CONTRADICTION'
    exp_semantic = case.get('expected_semantic_pass')
    if exp_semantic is not None:
        # This has meaning even when existence=False: the semantic contract
        # cannot pass if the symbol does not exist.
        if not exists:
            observed_semantics = False
            supported = True
        else:
            observed_semantics = observation.get('semantic_passed')
            supported = observation.get('semantic_checked') is True and isinstance(observed_semantics, bool)
        if not supported:
            record['semantic_reason'] = 'semantic probe not executed'
            return record
        sem_match = observed_semantics == exp_semantic
        record['semantic_match'] = sem_match
        record['matches_expected'] = existence_match and sem_match
        record['verification_status'] = ('VERIFIED_SEMANTICS' if existence_match and sem_match
                                         else 'OBSERVED_CONTRADICTION')
    return record


def run_verification(cases, python, cache, *, allow_install=False, use_current=False):
    runs = []
    actual_current = None
    if use_current:
        actual_current = invoke([python, '-c',
                                  'import importlib.metadata,json; print(json.dumps({' +
                                  'k:importlib.metadata.version(k) for k in ["numpy","pandas"] ' +
                                  'if importlib.metadata.packages_distributions().get(k)}))'])
        try:
            installed = json.loads(actual_current['stdout']) if actual_current['returncode'] == 0 else {}
        except (ValueError, KeyError):
            installed = {}
    else:
        installed = {}
    observations = {}
    for case in cases:
        kind, version, pkg = (case.get('probe_kind'), case.get('target_version'), case.get('package'))
        if not kind:
            runs.append(evaluate_case(case, None, {'status': 'STATIC_ONLY'})); continue
        if case.get('unsupported_version') or pkg not in SAFE_PACKAGES or not SAFE_VERSION.fullmatch(str(version)):
            runs.append(evaluate_case(case, None, {'status':'UNSUPPORTED_VERSION'})); continue
        if use_current:
            exe = python if installed.get(pkg) == version else None
            status = {'status': 'CURRENT_ENV' if exe else 'VERSION_NOT_INSTALLED',
                      'reason':'current python version must match target exactly'}
        else:
            exe, status = ensure_environment(python, cache, pkg, version, allow_install)
        if exe is None:
            runs.append(evaluate_case(case, None, status)); continue
        key = (str(exe), kind)
        if key not in observations:
            raw = invoke([exe, '-I', str(ROOT / 'runtime_probe.py'), kind], timeout=40)
            try:
                parsed = json.loads(raw['stdout'])
                observation = parsed.get('result') if raw['returncode'] == 0 and parsed.get('ok') else None
            except (ValueError, TypeError):
                observation = None
            observations[key] = (observation, raw)
        observation, raw = observations[key]
        if observation is None:
            row = evaluate_case(case, None, {'status':'PROBE_ERROR'})
            row['subprocess'] = raw
        else:
            row = evaluate_case(case, observation, status)
            row['subprocess'] = {'returncode': raw['returncode'],
                                 'stdout_sha256': digest(raw['stdout'].encode()),
                                 'stderr_sha256': digest(raw['stderr'].encode()),
                                 'stderr_excerpt': raw['stderr'][-500:]}
        runs.append(row)
    return runs


def main(argv=None):
    ap=argparse.ArgumentParser(description='Fixed allowlisted version-specific public API checks')
    ap.add_argument('--manifest', type=Path, default=ROOT/'data/d3_verification_manifest.jsonl')
    ap.add_argument('--python', default=sys.executable, help='Python executable used to create isolated envs (use Python 3.12 for NumPy 1.26.4)')
    ap.add_argument('--cache-dir',type=Path, default=ROOT/'.local_verify_envs')
    ap.add_argument('--output',type=Path,default=ROOT/'d3_verification_report.local.json')
    choice=ap.add_mutually_exclusive_group()
    choice.add_argument('--install',action='store_true',help='EXPLICIT consent to pip install binary wheels into isolated environments')
    choice.add_argument('--current-only',action='store_true',help='verify only exact versions already installed in selected interpreter')
    ap.add_argument('--package', choices=sorted(SAFE_PACKAGES), help='restrict to one package')
    ap.add_argument('--probe-kind', choices=sorted(PROBES), help='restrict to one fixed probe kind')
    ap.add_argument('--versions', nargs='+', help='restrict target versions (exact match)')
    a=ap.parse_args(argv)
    cases=load_manifest(a.manifest)
    if a.package:
        cases=[c for c in cases if c.get('package')==a.package]
    if a.probe_kind:
        cases=[c for c in cases if c.get('probe_kind')==a.probe_kind]
    if a.versions:
        if any(not SAFE_VERSION.fullmatch(x) for x in a.versions):
            ap.error('--versions requires numeric release versions only')
        cases=[c for c in cases if c.get('target_version') in set(a.versions)]
    if not cases:
        ap.error('no cases match the requested filters')
    rows=run_verification(cases,a.python,a.cache_dir,allow_install=a.install,use_current=a.current_only)
    header={'schema_version':'1.0', 'generated_at':utc_now(), 'mode': 'PINNED_ENV_INSTALL' if a.install else ('CURRENT_ONLY' if a.current_only else 'CACHED_ONLY'),
            'model_calls':0,'manifest_sha256':digest(a.manifest.read_bytes()),
            'probe_sha256':digest((ROOT/'runtime_probe.py').read_bytes()),
            'source':'fixed allowlisted subprocess probes; other cases STATIC_ONLY'}
    summary={s:sum(x['verification_status']==s for x in rows) for s in sorted({x['verification_status'] for x in rows})}
    report={'header':header,'counts':summary,'results':rows}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'report':str(a.output),'counts':summary,'cases':len(rows)},ensure_ascii=False))
    return 1 if summary.get('OBSERVED_CONTRADICTION',0) or summary.get('PROBE_ERROR',0) else 0

if __name__=='__main__':
    raise SystemExit(main())
