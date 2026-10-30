"""Offline contract review of Muse thin adapters + frozen D2 version gate.

All in-memory model responses are generated TEST_FIXTURES. No network, no
provider request, no audit claim of a real Muse invocation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from benchmark.guardian_d2 import load_cases, assess
from d4_model_adapters import MetaResponsesAdapter, BasetenChatAdapter, evidence_decision
from document_judge import validate_official_url

CLAIM='The public DataFrame.append API was removed in pandas version 2.0.'
EXCERPT='The DataFrame.append() method was removed in pandas version 2.0. Please use concat.'
QUOTE='The DataFrame.append() method was removed in pandas version 2.0.'


def synthetic_responses():
    """Not from Muse or official online retrieval; only a wire-contract test."""
    text=json.dumps({'verdict':'SUPPORTED','quote':QUOTE,'explanation':'Exact offline test fixture quote'})
    meta={'id':'TEST_FIXTURE_META','model':MetaResponsesAdapter.model,'status':'completed',
          'output':[{'type':'message','status':'completed',
                     'content':[{'type':'output_text','text':text}]}],
          'usage':{'input_tokens':1,'output_tokens':1,'output_tokens_details':{'reasoning_tokens':0}}}
    baseten={'id':'TEST_FIXTURE_BASETEN','model':BasetenChatAdapter.model,
             'choices':[{'finish_reason':'stop','message':{'content':text}}],
             'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2,
                      'completion_tokens_details':{'reasoning_tokens':0}}}
    return meta,baseten


def review():
    cases=load_cases();wrong=[];distribution={}
    for c in cases:
        decision=assess(c)['decision']
        distribution[decision]=distribution.get(decision,0)+1
        if decision!=c['expected_decision']:
            wrong.append(c['case_id'])
    meta,baseten=synthetic_responses()
    parsed=[MetaResponsesAdapter.parse(meta,EXCERPT),BasetenChatAdapter.parse(baseten,EXCERPT)]
    for a in (MetaResponsesAdapter,BasetenChatAdapter):
        request=a.request_payload(CLAIM,EXCERPT)
        assert request['model']==a.model
        assert len(json.dumps(request)) < 5000
    rule_decision=assess(next(c for c in cases if c['case_id']=='pandas_append_2_2_3'))['decision']
    gates=[evidence_decision(p,rule_decision) for p in parsed]
    assert rule_decision=='ABSTAIN'
    assert all(g['decision']=='ABSTAIN' and g['override'] is False for g in gates)
    url='https://pandas.pydata.org/docs/whatsnew/v2.0.0.html'
    validate_official_url(url)
    return {'schema':'D4_OFFLINE_CONTRACT_REVIEW_v1',
            'review_mode':'OFFLINE_SYNTHETIC_PROTOCOL_FIXTURES',
            'network_requests':0,'model_requests':0,'live_doc_refresh':'NOT_PERFORMED',
            'synthetic_model_outputs_not_science':True,
            'frozen_d2_cases':len(cases),'frozen_d2_agreement':len(cases)-len(wrong),
            'frozen_d2_disagreement_ids':wrong,'decisions':distribution,
            'adapters':['meta_responses','baseten_chat'],
            'wire_shapes_parse_pass':len(parsed),
            'reported_provenance':'REPLAY_UNTRUSTED',
            'removed_rule_dominates_model_verdict':all(g['decision']=='ABSTAIN' for g in gates),
            'claim_and_excerpt_sha256':{
                'claim':hashlib.sha256(CLAIM.encode()).hexdigest(),
                'excerpt':hashlib.sha256(EXCERPT.encode()).hexdigest()},
            'official_url_allowlisted_but_not_fetched':url}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',help='Write new JSON; refuses overwrite')
    args=p.parse_args()
    result=review()
    if args.output:
        target=Path(args.output)
        with target.open('x',encoding='utf-8') as fp:
            json.dump(result,fp,indent=2,ensure_ascii=False)
            fp.write('\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if result['frozen_d2_disagreement_ids']:raise SystemExit(1)

if __name__=='__main__':main()
