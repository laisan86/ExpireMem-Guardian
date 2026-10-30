"""ExpireMem Guardian Studio | public data only, no automatic provider calls.

Launch: streamlit run studio_app.py
This is a read-only/replay-focused presentation surface, NOT a code sandbox.
"""
from __future__ import annotations
import json
import html
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'core'),str(ROOT)]

import streamlit as st
import pandas as pd
from benchmark_suite import evaluate_cases,evaluate_summary
from evidence_vault import parse_json_bytes,inspect_guardian_report,public_receipt_summary
from document_judge import fetch_official_excerpt,ALLOWED_URLS
from replay import run_offline
from lifecycle import assess_np_bool, NP_BOOL, OFFICIAL_SOURCES
import subprocess
import sys as runtime_sys
from core.guardian_core import BUGGY_CODE,deterministic_expression
from gap_index_cases import run_case_a_gapped, run_case_c, FROZEN_CANDIDATES
from d4_offline_review import review as d4_offline_review
from d5_evaluation import fixed_evaluation as d5_fixed_evaluation
from d4_oracle_guard import REFERENCE_ORACLE, review_reference, review_oracle, prompt_for_model

st.set_page_config(page_title='ExpireMem Guardian | Verifiable API Memory',page_icon='🛡️',layout='wide')
st.markdown('''<style>
.block-container {padding-top: 1.9rem; max-width: 1280px}
.hero {background: linear-gradient(120deg,#122A34,#101A31 70%);border:1px solid #264D5D;border-radius:20px;padding:24px 28px}
.eyebrow {color:#72E9B9;font-size:.76rem;letter-spacing:.15em;font-weight:700;text-transform:uppercase}
.bigtitle {font-size:2.5rem;font-weight:800;line-height:1.1;letter-spacing:-0.04em;margin-top:8px}
.desc {color:#ACBCD3;margin-top:12px;max-width:790px}
.foot {font-size:.78rem;color:#879CB2}
.smallstatus {font-size:.83rem; padding:.5rem .75rem; border-radius:.6rem; border:1px solid #314764;display:inline-block;margin-bottom:.5rem}
/* UI-only: wrap Streamlit syntax-highlighted code visually without editing execution strings. */
div[data-testid="stCode"] pre,
div[data-testid="stCode"] pre code,
.stCode pre,
.stCode pre code,
div[data-testid="stCodeBlock"] pre,
div[data-testid="stCodeBlock"] pre code {
  white-space: pre-wrap !important;
  overflow-wrap: anywhere !important;
  word-break: break-word !important;
  max-width: 100%;
}
/* P8 observed candidate: single line, exact source bytes; tighter, deliberately nonwrapping display. */
pre.p8-exact-candidate {
  background:#10152b;color:#d3dfed;
  white-space:pre !important;overflow-x:hidden;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace !important;
  font-size:10.5px !important;line-height:1.7 !important;
  padding:13px 2px 13px 8px;border-radius:8px;margin:0;
  letter-spacing:-.16px;box-sizing:border-box;width:100%;
}
pre.p8-exact-candidate code {
  font-family:inherit !important;font-size:inherit !important;
  line-height:inherit !important;white-space:pre !important;
  letter-spacing:inherit !important;
}
</style>''',unsafe_allow_html=True)
st.markdown('''<div class="hero"><div class="eyebrow">ExpireMem Guardian / Hackathon Engineering Demo</div>
<div class="bigtitle">Know when an API memory is no longer safe to use.</div>
<div class="desc">A coding-agent safety layer: detect removed APIs → abstain → refresh official evidence → propose a constrained repair → execute in the same environment. Evidence first; model claims never self-certify.</div>
</div>''',unsafe_allow_html=True)
st.caption('PUBLIC API DEPRECATION ONLY · No confidential research material · No automatic LLM calls')

with st.sidebar:
    st.markdown('### Guardian control center')
    st.info('**Default: no paid model calls.** This Studio can replay the safe fixture, inspect benchmark cases, fetch allowlisted public documentation, and validate uploaded receipts.')
    st.markdown('**Model policy**')
    st.markdown('Rules decide version status. Muse may propose repairs or judge documentary evidence. Execution remains the acceptance gate.')
    st.markdown('**Evidence discipline**')
    st.warning('Never upload keys, private ledgers, or unpublished research to a public hosted Streamlit app. Run locally for private audit readback.')
    st.caption('v0.8 · preserved v0.3 core + D4 oracle verification (offline by default)')

st.markdown('**ASSESS　→　ABSTAIN　→　REFRESH　→　MUSE PATCH　→　VALIDATE　→　EXECUTE**')

run_tab,benchmark_tab,lifecycle_tab,semantic_tab,docs_tab,vault_tab=st.tabs([
    '🧪 Red → Green', '📊 Cross-library Benchmark', '🧬 API Lifecycle', '🔎 Silent Data Loss', '📚 Official Document Evidence', '🔐 Evidence Vault'])

with run_tab:
    st.subheader('Same environment. Observable failure. Verifiable repair.')
    st.caption('Fixture: public pandas DataFrame.append removal. The rule-only baseline already detects this case; Muse is useful for generating a candidate patch, not for rediscovering this known version boundary.')
    l,r=st.columns(2,gap='large')
    with l:
        st.error('WITHOUT GUARDIAN · LEGACY API')
        st.code(BUGGY_CODE,language='python')
    with r:
        st.success('WITH GUARDIAN · PROPOSED FIX SHAPE')
        st.code(deterministic_expression(BUGGY_CODE),language='python')
        st.markdown('**Acceptance requirements**')
        st.markdown('AST whitelist → original row preserved → version-rule re-check → same Python executable → exit 0.')
    st.markdown('#### Local execution (deliberately offline)')
    st.caption('Runs only the frozen public fixture. Official fetch and Baseten are intentionally disabled; the result must be GREEN_OFFLINE_REPLAY, NEVER GREEN_VERIFIED_MUSE.')
    if st.button('▶ Execute local RED → GREEN replay',key='run_local',type='primary'):
        with st.spinner('Running the controlled public fixture in subprocesses…'):
            try: st.session_state['offline_report']=run_offline()
            except Exception as exc: st.session_state['offline_error']=f'{type(exc).__name__}: {exc}'
    if st.session_state.get('offline_error'):
        st.error(st.session_state['offline_error'])
    audit=st.session_state.get('offline_report')
    if audit:
        st.warning(f"Mode / result: {audit['outcome']} — no provider call; no live evidence")
        a,b,c=st.columns(3)
        a.metric('RED detected',str(audit.get('red_confirmed')))
        b.metric('Patched process exit',str((audit.get('green') or {}).get('returncode')))
        c.metric('Official evidence',str(audit.get('evidence',{}).get('status')))
        st.markdown('**Observed traceback**')
        st.code(audit['red']['stderr'][-2000:],language='text')
        st.markdown('**Observed Green output**')
        st.code((audit.get('green') or {}).get('stdout',''),language='text')
        if audit.get('audit_trace'):
            st.dataframe(pd.DataFrame(audit['audit_trace']),use_container_width=True,hide_index=True)
    else:
        st.caption('Run the local replay above, or upload your PRIVATE real-v0.3 report under Evidence Vault to inspect its provenance without issuing another request.')
    st.markdown('#### Stronger Case A fixture: filtered dataframe, non-contiguous index')
    st.caption('The historical v0.3 core remains unchanged. This NEW controlled offline variant exercises index [0, 1, 3]; it does not reuse or amend the old live Muse receipt.')
    if st.button('▶ Run gap-index RED → GREEN', key='run_gap_case_a'):
        with st.spinner('Running gapped public fixture, no network or provider requests...'):
            try:
                st.session_state['gap_a_report'] = run_case_a_gapped()
                st.session_state.pop('gap_a_error', None)
            except Exception as exc:
                st.session_state['gap_a_error'] = f'{type(exc).__name__}: {exc}'
    if st.session_state.get('gap_a_error'):
        st.error(st.session_state['gap_a_error'])
    if a_gap := st.session_state.get('gap_a_report'):
        st.success('GREEN_OFFLINE_GAPPED · executable postcondition passed' if a_gap['outcome'] == 'GREEN_OFFLINE_GAPPED' else a_gap['outcome'])
        x, y, z = st.columns(3)
        x.metric('Legacy code exit', a_gap.get('red', {}).get('exit_code', '?'))
        y.metric('Concat exit', a_gap.get('green', {}).get('exit_code', '?'))
        z.metric('Rows preserved + 1', str(a_gap.get('green', {}).get('postcondition_pass', False)))
        st.code(a_gap.get('candidate_shape', ''), language='python')
        st.json({'before_index': a_gap.get('before_index'),
                 'after_rows': a_gap.get('green', {}).get('verified_rows'),
                 'mode': a_gap.get('mode'), 'model_requests': a_gap.get('model_requests')})

with benchmark_tab:
    rows=evaluate_cases();summary=evaluate_summary(rows)
    st.subheader('D2 / Frozen, deterministic cross-library baseline')
    st.caption('14 controlled cases across pandas, NumPy and Django. These are narrow fixture-level AST rules, NOT a general static analyzer or observed LLM success rate.')
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Cases',summary['count'])
    c2.metric('Rule agreement',f"{summary['correct']}/{summary['count']}")
    c3.metric('Libraries',len(summary['libraries']))
    c4.metric('Model calls','0')
    st.bar_chart(pd.DataFrame([{'decision':k,'cases':v} for k,v in summary['distribution'].items()]).set_index('decision'))
    filt=st.multiselect('Library filter',summary['libraries'],default=summary['libraries'])
    table=[{k:r[k] for k in ('case_id','library','target_version','scenario','expected','actual','match','reason')} for r in rows if r['library'] in filt]
    st.dataframe(pd.DataFrame(table),use_container_width=True,hide_index=True)
    choices=[r for r in rows if r['library'] in filt]
    if choices:
        pick=st.selectbox('Inspect a concrete fixture',[r['case_id'] for r in choices])
        selected=next(r for r in choices if r['case_id']==pick)
        a,b=st.columns(2)
        with a:
            st.markdown('**Original code (AST analyzed, not executed)**')
            st.code(selected['source_code'],language='python')
        with b:
            st.markdown('**Fixed ground truth**')
            st.json({k:selected[k] for k in ('library','target_version','expected','actual','reason','matched_symbols')})
            for url in selected['evidence_urls']:
                st.markdown(f'[Official release note]({url})')
    st.download_button('Download benchmark summary JSON',data=json.dumps(summary,indent=2).encode(),
                      file_name='expiremem_d2_baseline_summary.json',mime='application/json')
    with st.expander('D4 / D5 · protocol and evaluation readiness (offline)', expanded=False):
        d4=d4_offline_review()
        d5=d5_fixed_evaluation()
        st.caption('This is a contract and rule-baseline review only. No real model calls, no live official-page refresh, and no claimed calibrated probability.')
        x,y,z=st.columns(3)
        x.metric('D4 adapter contracts',f"{d4['wire_shapes_parse_pass']}/2")
        y.metric('D2 rule matches',f"{summary['correct']}/{summary['count']}")
        z.metric('D5 calibration','NOT FITTED')
        st.json({'provider_protocols':d4['adapters'],
                 'model_outputs':'SYNTHETIC / OFFLINE ONLY',
                 'version_override_prevented':d4['removed_rule_dominates_model_verdict'],
                 'calibration':d5['calibration']['status'],
                 'rule_split':'UNKNOWN_RULE ONLY · grouped by lifecycle event',
                 'cross_version_numpy_matrix':'REQUIRES SEPARATE PINNED RUNTIMES'})
        st.download_button('Download D4/D5 offline status JSON',
                           data=json.dumps({'d4':d4,'d5':d5},indent=2).encode(),
                           file_name='expiremem_d4_d5_offline_status.json',mime='application/json')



with lifecycle_tab:
    st.subheader('Case B / Non-monotonic NumPy np.bool lifecycle')
    st.caption('The same symbol was deprecated, removed, then reintroduced with different meaning; unreviewed 2.6.0+ remains UNKNOWN. Version status and task semantics are separate gates. No model calls.')
    st.markdown('**Official release boundaries**')
    st.dataframe(pd.DataFrame([
        {'From':s.from_version,'Before':s.before_version or 'latest',
         'Availability':s.state,'Meaning':s.semantic} for s in NP_BOOL]),
         use_container_width=True,hide_index=True)
    version=st.selectbox('Target NumPy version',['1.23.5','1.26.4','2.0.0','2.5.3'],index=3)
    contract=st.radio('Task contract',['existence_only','json_builtin_bool'],index=1,horizontal=True)
    source='import numpy as np\nimport json\njson.dumps(np.bool(True))\n'
    status=assess_np_bool(source,version,contract)
    a,b,c=st.columns(3)
    a.metric('API state',status['availability'])
    b.metric('Task semantics',status['semantic_compatibility'])
    c.metric('Guardian decision',status['decision'])
    st.code(source,language='python')
    st.info('These boundary labels are DETERMINISTIC OFFICIAL-DOC RULES, not observed runtime proof for the selected version.')
    st.markdown('**Execution verification — installed version only**')
    st.caption('The button runs a bundled fixed NumPy probe in the currently active Python; it does NOT pip-install, change versions, or execute arbitrary uploaded code.')
    if st.button('▶ Verify currently installed NumPy',key='np_bool_local'):
        try:
            process=subprocess.run([runtime_sys.executable,'-I',str(ROOT/'runtime_probe.py'),'numpy.bool'],
                capture_output=True,text=True,timeout=30,check=False)
            raw=json.loads(process.stdout)
            st.session_state['np_bool_probe']=(raw.get('result') if process.returncode==0 and raw.get('ok') else
                {'error':raw.get('error','probe unavailable')})
        except Exception as exc:
            st.session_state['np_bool_probe']={'error':f'{type(exc).__name__}: {exc}'}
    observed=st.session_state.get('np_bool_probe')
    if observed:
        if 'error' in observed:
            st.error(observed['error'])
        else:
            st.success('OBSERVED IN THIS PYTHON RUNTIME · NumPy '+observed['actual_version'])
            if observed['actual_version'] != version:
                st.warning('Observed runtime version differs from selected hypothetical target version. Do not label the selected target VERIFIED.')
            st.json({k:observed.get(k) for k in ('actual_version','existence','semantic_contract','semantic_checked','semantic_passed','observations','warnings')})
    st.markdown('**To verify pinned historical versions**')
    st.code('python3.12 verify_corpus.py --python python3.12 --package numpy --probe-kind numpy.bool --versions 1.26.4 2.0.0 2.5.3 --install',language='bash')
    st.caption('Runs ONLY fixed allowlisted probes in isolated dependency environments. Installation requires explicit --install. NumPy 1.23.5 needs a compatible Python 3.11 environment.')
    for url in OFFICIAL_SOURCES:
        st.markdown(f'[Official NumPy release note]({url})')

with semantic_tab:
    st.subheader('Case C / Silent row overwrite from a valid pandas operation')
    st.caption('P8 C1 NO_DOC produced df.loc[len(df)] in 3/3 runs. This is an OFFLINE replay of fixed public candidate shapes, NOT a new model call. Narrow API-rule PASS ≠ program correctness.')
    st.markdown('**Independent task contract**: append exactly `{"id": 7, "name": "carol"}`, preserve the existing 3 rows and their order. Original DataFrame was filtered to index `[0, 1, 3]`.')
    left, right = st.columns(2, gap='large')
    with left:
        st.error('Silent bad candidate · legal API, data loss')
        st.markdown('<pre class="p8-exact-candidate"><code>' +
                    html.escape(FROZEN_CANDIDATES['silent_loc_dict']) +
                    '</code></pre>', unsafe_allow_html=True)
    with right:
        st.success('Correct candidate · full row preservation')
        st.code(FROZEN_CANDIDATES['correct_concat'], language='python')
    st.warning('Important: the original v0.3 FIXTURE-SPECIFIC patch AST whitelist would already reject df.loc. Case C instead demonstrates that syntactic validity + the weaker removed-API version gate + exit code 0 are insufficient. The external semantic oracle supplies the missing control.')
    if st.button('▶ Execute silent-loss vs concat comparison', key='run_case_c'):
        with st.spinner('Running three frozen candidate variants in subprocesses...'):
            try:
                st.session_state['gap_c_report'] = run_case_c()
                st.session_state.pop('gap_c_error', None)
            except Exception as exc:
                st.session_state['gap_c_error'] = f'{type(exc).__name__}: {exc}'
    if st.session_state.get('gap_c_error'):
        st.error(st.session_state['gap_c_error'])
    if c_gap := st.session_state.get('gap_c_report'):
        st.info(c_gap['outcome'] + ' · No provider request')
        rows = c_gap.get('tested_candidates', [])
        st.dataframe(pd.DataFrame([{k: r[k] for k in
            ('candidate','removed_api_version_gate','subprocess_exit_code',
             'row_count_after','task_oracle','guardian_candidate_accepted')}
            for r in rows]), hide_index=True, use_container_width=True)
        chosen = st.selectbox('Inspect exact observed post-execution rows',
            [r['candidate'] for r in rows], key='semantic_inspect')
        rr = next(r for r in rows if r['candidate'] == chosen)
        if rr['task_oracle'] == 'FAIL':
            st.error('REJECTED: subprocess exited 0, but an original row disappeared.')
        else:
            st.success('ACCEPTED: original rows + requested row are intact.')
        st.json({'index_before': rr['index_before'], 'index_after': rr['index_after'],
                 'rows_after': rr['rows_after'], 'task_oracle': rr['task_oracle'],
                 'source_sha256': rr['source_sha256'], 'model_requests': c_gap['model_requests']})


    with st.expander('D4 · Task oracle authored by Muse (guarded evaluation, offline by default)', expanded=False):
        st.caption('Second model role: Muse may propose a pure task postcondition. It must PASS on independent known-good fixtures and FAIL on frozen silent-overwrite, mutation and reorder fixtures BEFORE it is trusted with any new candidate. No automatic model calls.')
        st.markdown('**Frozen task contract**: Append exactly the requested row while preserving all prior rows, values and order.')
        st.markdown('**Offline reference — handwritten, not a Muse result**')
        st.code(REFERENCE_ORACLE, language='python')
        if st.button('▶ Validate handwritten reference against 16 frozen witnesses',key='oracle_reference'):
            st.session_state['oracle_reference_review'] = review_reference()
        if ref_report := st.session_state.get('oracle_reference_review'):
            if ref_report['status']=='VALIDATED_ON_FROZEN_WITNESSES':
                st.success('Handwritten reference separates all 16 fixed witnesses · NO Muse request')
            else: st.error(ref_report['status'])
            st.dataframe(pd.DataFrame(ref_report['evaluations']),hide_index=True,use_container_width=True)
        st.markdown('**Evaluate a supplied Muse proposal — without issuing a request**')
        st.caption('Paste only an existing Python function from your own private provider evidence. This limited AST evaluator is not a general-purpose Python sandbox. No file is uploaded to a server except by the Streamlit deployment itself: use localhost for private evidence.')
        proposal=st.text_area('Existing pure oracle function (optional)',value='',height=120,
                              placeholder='def verify_postcondition(before_rows, after_rows, task_row):\n    return ...',key='oracle_proposal_text')
        if st.button('▶ Validate proposed oracle offline',key='validate_oracle_proposal'):
            if proposal.strip():
                st.session_state['oracle_proposal_review']=review_oracle(proposal)
            else:
                st.warning('Paste a proposed function first. No model called.')
        if oracle_review := st.session_state.get('oracle_proposal_review'):
            if oracle_review['status']=='VALIDATED_ON_FROZEN_WITNESSES':
                st.success('Accepted for these frozen witnesses only; source remains unverified as to model origin.')
            else: st.error('REJECTED · '+str(oracle_review.get('reason','Did not pass fixed witnesses')))
            st.json({k:v for k,v in oracle_review.items() if k != 'evaluations'})
            if oracle_review['evaluations']:
                st.dataframe(pd.DataFrame(oracle_review['evaluations']),use_container_width=True,hide_index=True)
        st.caption('An optional one-shot Baseten script is included but NEVER called by this Studio. It persists a private attempt lock before network and keeps response receipts outside the repo. Meta Wonder access remains blocked until its unsettled ledger is resolved.')

with docs_tab:
    st.subheader('D3 / Evidence retrieval for future Muse document judging')
    st.caption('An official page being fetched proves only provenance, not that it supports the specific claim. This panel never calls a model.')
    labels={
       'pandas / DataFrame.append':('https://pandas.pydata.org/docs/whatsnew/v2.0.0.html',['DataFrame.append()']),
       'NumPy / np.float_':('https://numpy.org/doc/2.0/release/2.0.0-notes.html',['float_']),
       'Django / force_text':('https://docs.djangoproject.com/en/4.0/releases/4.0/',['force_text']),
    }
    selection=st.selectbox('Approved primary evidence page',list(labels))
    url,terms=labels[selection]
    st.code(url,language='text')
    st.markdown('**Evidence gate**: exact allowlisted HTTPS URL → redirect/content checks → bounded excerpt → SHA-256. No semantic validity claim until judged and externally checked.')
    if st.button('↻ FETCH live public official document (no model call)',key='fetch_official'):
        with st.spinner('Fetching public allowlisted page…'):
            try: st.session_state['fetched_doc']=fetch_official_excerpt(url,terms)
            except Exception as exc:
                # Preserve the selected URL in failure receipts. Otherwise an
                # exception is mistakenly reported as a changed page selection.
                st.session_state['fetched_doc']={
                    'status':'UNAVAILABLE',
                    'source_url':url,
                    'error_type':type(exc).__name__,
                    'reason':str(exc)[:240],
                }
    fetched=st.session_state.get('fetched_doc')
    if fetched:
        # Report actual fetch failures *before* checking for stale source data.
        # This avoids hiding network / SSL / redirect / HTML-parser exceptions.
        if fetched.get('status')!='FETCHED_OFFICIAL_PAGE':
            st.error(f"Official document fetch unavailable: {fetched.get('error_type','unknown')}: {fetched.get('reason','unknown error')}")
            st.caption('No model call was made. This is a public-document fetch only.')
        elif fetched.get('source_url')!=url:
            st.info('Selected a new source. Click fetch again to refresh this exact page.')
        else:
            st.success('FETCHED_OFFICIAL_PAGE (not yet a semantic judgment)')
            st.caption('SHA-256 '+fetched['source_sha256'])
            st.code(fetched['excerpt'],language='text')
            st.download_button('Download PUBLIC excerpt receipt',data=json.dumps(fetched,indent=2).encode(),
                file_name='public_evidence_receipt.json',mime='application/json')
    st.markdown('#### Muse document judgment: explicit CLI, not an automatic Studio action')
    st.code('''export BASETEN_API_KEY="<from private environment>"
python one_shot_judge.py --policy pandas.DataFrame.append \\
  --private-dir /private/unique_judge_run \\
  --accept 'I AUTHORIZE ONE BASETEN DOCUMENT JUDGE' ''',language='bash')
    st.caption('The optional CLI writes an exclusive pre-request lock and raw reply to a PRIVATE directory; no retries. Model judgment never overrides a removed-version rule. Do not publish private artifacts.')

with vault_tab:
    st.subheader('Read back your existing REAL Baseten run without another request')
    st.caption('Load PRIVATE v0.3 guardian_demo_report.json. Optional raw provider JSON can be checked against the recorded SHA-256. Files stay in this running Streamlit process; do not do this on a shared/hosted machine.')
    a,b=st.columns(2)
    with a: f_report=st.file_uploader('Private Guardian report',type=['json'],key='report_input')
    with b: f_raw=st.file_uploader('Optional private Baseten raw JSON',type=['json'],key='raw_input')
    if f_report is not None:
        try:
            report=parse_json_bytes(f_report.getvalue())
            raw=parse_json_bytes(f_raw.getvalue()) if f_raw is not None else None
            checked=inspect_guardian_report(report,raw)
            st.markdown('### Evidence consistency checks')
            if checked['structurally_consistent']:
                st.success('All supplied evidence fields are internally consistent. This is not independent provider attestation.')
            else:
                st.warning('Some evidence checks did NOT pass. Do not publicly claim GREEN_VERIFIED_MUSE on this artifact alone.')
            st.dataframe(pd.DataFrame([{'check':k,'passes':v} for k,v in checked['structural_checks'].items()]),
                         hide_index=True,use_container_width=True)
            m1,m2,m3=st.columns(3)
            m1.metric('Claimed outcome',checked['claimed_outcome'])
            m2.metric('Reported model latency',f"{checked['model_seconds']} s")
            m3.metric('Reported tokens',str(checked['total_tokens']))
            st.write('**Raw provider hash verification:**', checked['provider_raw_hash_check'])
            st.write('**Trace stages:**',' → '.join(checked['audit_stages']))
            pub=public_receipt_summary(report,raw)
            st.download_button('Download sanitized PUBLIC summary',data=json.dumps(pub,indent=2).encode(),
                               file_name='expiremem_guardian_public_evidence_summary.json',mime='application/json')
        except Exception as exc:
            st.error('Invalid supplied evidence; no public summary generated: '+str(exc)[:200])
    else:
        st.info('No private report uploaded. No live-success metrics are asserted by this Studio.')

st.divider()
st.markdown('''<span class="foot">ExpireMem Guardian · Public API evidence only. One verified repair case is not a demonstrated population success rate. No private ledgers, model secrets, or confidential research belong in the public repo.</span>''',unsafe_allow_html=True)
