"""Fixed, offline, dependency-specific probe invoked only by verify_corpus.
No user-authored target source execution. Prints exactly one JSON object to stdout.
"""
import json
import platform
import sys
import traceback
import warnings

KINDS = {'numpy.bool', 'numpy.float_', 'pandas.DataFrame.append', 'django.utils.encoding.force_text'}

def run(kind):
    if kind not in KINDS:
        raise ValueError('unapproved probe kind')
    package = kind.split('.', 1)[0]
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter('always')
        module = __import__(package)
        result = {'probe_kind': kind, 'package': package, 'actual_version': module.__version__,
                  'python_version': platform.python_version(), 'executable': sys.executable,
                  'implementation': platform.python_implementation(),
                  'platform': platform.platform(), 'existence': False,
                  'semantic_checked': False, 'semantic_passed': None,
                  'semantic_contract': None, 'observations': {}}
        try:
            if kind == 'numpy.bool':
                # The critical non-monotonic public symbol. json.dumps is a
                # useful semantic distinction: builtin bool vs NumPy scalar.
                val_type = getattr(module, 'bool')
                result['existence'] = True
                value = val_type(True)
                result['semantic_contract'] = 'json_builtin_bool'
                result['semantic_checked'] = True
                result['observations'] = {
                    'type_module': val_type.__module__, 'type_name': val_type.__name__,
                    'is_builtin_bool_type': val_type is bool,
                    'is_numpy_bool_scalar_type': val_type is module.bool_,
                    'scalar_is_builtin_bool': isinstance(value, bool),
                }
                try:
                    encoded = json.dumps(value)
                    result['observations']['json_dumps'] = {'succeeded': True, 'value': encoded}
                    result['semantic_passed'] = encoded == 'true'
                except (TypeError, ValueError) as exc:
                    result['observations']['json_dumps'] = {'succeeded': False, 'exception_class': type(exc).__name__}
                    result['semantic_passed'] = False
            elif kind == 'numpy.float_':
                result['existence'] = getattr(module, 'float_', None) is not None
                # Existence-only probe: exact version, class semantics not asserted.
            elif kind == 'pandas.DataFrame.append':
                result['existence'] = getattr(module.DataFrame, 'append', None) is not None
                if result['existence']:
                    result['semantic_contract'] = 'append_preserves_and_adds_row'
                    result['semantic_checked'] = True
                    frame = module.DataFrame([{'id': 1}])
                    after = frame.append({'id': 2}, ignore_index=True)
                    result['semantic_passed'] = after.to_dict(orient='records') == [{'id': 1}, {'id': 2}]
                    result['observations']['result_rows'] = after.to_dict(orient='records')
            elif kind == 'django.utils.encoding.force_text':
                from django.utils import encoding
                fn = getattr(encoding, 'force_text', None)
                result['existence'] = fn is not None
                if result['existence']:
                    result['semantic_contract'] = 'returns_expected_text'
                    result['semantic_checked'] = True
                    result['semantic_passed'] = fn('hello') == 'hello'
        except (AttributeError, ImportError) as exc:
            # A removed symbol is observable as an exception, not a crash.
            result['observations']['access_exception'] = type(exc).__name__
        result['warnings'] = [str(w.message)[:400] for w in record][:10]
    return result

if __name__ == '__main__':
    try:
        if len(sys.argv) != 2: raise ValueError('required exactly one fixed probe kind')
        print(json.dumps({'ok': True, 'result': run(sys.argv[1])}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__,
                          'error': str(exc)[:300]}, sort_keys=True))
        raise SystemExit(2)
