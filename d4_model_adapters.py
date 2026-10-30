"""D4: strict *offline* serializers/parsers for two distinct Muse API protocols.

No transport or HTTP code lives in this module. Passing a raw JSON response to
these decoders never proves a real provider call; provenance is REPLAY_UNTRUSTED.
The Meta D2 ledger has unsettled entries: do not bypass its existing guard.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
import json

from document_judge import judge_prompt, validate_judge_reply, judge_gate

META_MODEL='muse-wonder-1.0'
BASETEN_MODEL='meta-models/muse-spark-open-1026'
SYSTEM_INSTRUCTION='Return exactly one JSON object containing verdict, quote and explanation.'
PROVENANCE='REPLAY_UNTRUSTED'

class DecodeFailure(ValueError):
    pass


def canon_hash(raw: dict) -> str:
    return hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def _output_json(message: str, excerpt: str) -> dict:
    try:
        return validate_judge_reply(message, excerpt)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as ex:
        raise DecodeFailure('Invalid bounded judge result') from ex


def _int_ge_zero(value):
    if type(value) is not int or value < 0:
        raise DecodeFailure('Usage token must be nonnegative integer')
    return value


def _usage_meta(raw):
    u=raw.get('usage')
    if not isinstance(u,dict): raise DecodeFailure('Missing Meta usage')
    inp=_int_ge_zero(u.get('input_tokens'))
    out=_int_ge_zero(u.get('output_tokens'))
    details=u.get('output_tokens_details') or {}
    if not isinstance(details,dict):raise DecodeFailure('Invalid Meta token details')
    reasoning=_int_ge_zero(details.get('reasoning_tokens',0))
    if reasoning>out:raise DecodeFailure('Reasoning tokens exceed output')
    return {'input_tokens':inp,'output_tokens':out,'reasoning_tokens':reasoning,
            'cached_input_tokens':u.get('input_tokens_details',{}).get('cached_tokens') if isinstance(u.get('input_tokens_details',{}),dict) else None}


def _usage_baseten(raw):
    u=raw.get('usage')
    if not isinstance(u,dict):raise DecodeFailure('Missing Baseten usage')
    inp=_int_ge_zero(u.get('prompt_tokens'))
    out=_int_ge_zero(u.get('completion_tokens'))
    details=u.get('completion_tokens_details') or {}
    if not isinstance(details,dict):raise DecodeFailure('Invalid Baseten token details')
    reasoning=_int_ge_zero(details.get('reasoning_tokens',0))
    if reasoning>out:raise DecodeFailure('Reasoning tokens exceed output')
    if 'total_tokens' in u and _int_ge_zero(u['total_tokens'])!=inp+out:
        raise DecodeFailure('Inconsistent total token count')
    # Prediction token counters are diagnostic, NOT added to billed output.
    return {'input_tokens':inp,'output_tokens':out,'reasoning_tokens':reasoning,
            'cached_input_tokens':(u.get('prompt_tokens_details') or {}).get('cached_tokens'),
            'prediction_details_not_additive':True}


@dataclass(frozen=True)
class ParsedJudge:
    provider: str
    model: str
    response_id: str
    verdict: str
    quote: str
    explanation: str
    usage: dict
    response_sha256: str
    provenance: str = PROVENANCE

    def as_dict(self):return asdict(self)


class MetaResponsesAdapter:
    provider='meta_responses'
    model=META_MODEL

    @staticmethod
    def request_payload(claim, excerpt, max_output_tokens=2048):
        if type(max_output_tokens) is not int or not (256<=max_output_tokens<=4096):
            raise ValueError('Bounded output budget required')
        return {'model':META_MODEL,'instructions':SYSTEM_INSTRUCTION,
                'input':judge_prompt(claim,excerpt),'max_output_tokens':max_output_tokens,
                'stream':False,'store':False}

    @staticmethod
    def parse(raw, excerpt):
        if not isinstance(raw,dict):raise DecodeFailure('Not a JSON object')
        if raw.get('model')!=META_MODEL:raise DecodeFailure('Model mismatch')
        if raw.get('status')!='completed' or raw.get('incomplete_details'):
            raise DecodeFailure('Meta response not complete')
        if not isinstance(raw.get('id'),str) or not raw['id']:
            raise DecodeFailure('Missing response ID')
        messages=[x for x in raw.get('output',[]) if isinstance(x,dict) and x.get('type')=='message']
        if len(messages)!=1:raise DecodeFailure('Require exactly one output message')
        msg=messages[0]
        if msg.get('status') not in (None,'completed'):raise DecodeFailure('Message incomplete')
        content=msg.get('content')
        if not isinstance(content,list):raise DecodeFailure('Invalid message content')
        outputs=[c.get('text') for c in content if isinstance(c,dict) and c.get('type')=='output_text']
        if len(outputs)!=1 or not isinstance(outputs[0],str):
            raise DecodeFailure('Require exactly one visible output text')
        parsed=_output_json(outputs[0],excerpt)
        return ParsedJudge('meta_responses',META_MODEL,raw['id'],parsed['verdict'],
                           parsed['quote'],parsed['explanation'],_usage_meta(raw),canon_hash(raw))


class BasetenChatAdapter:
    provider='baseten_chat'
    model=BASETEN_MODEL

    @staticmethod
    def request_payload(claim, excerpt, max_tokens=2048):
        if type(max_tokens) is not int or not (256<=max_tokens<=4096):
            raise ValueError('Bounded output budget required')
        return {'model':BASETEN_MODEL,'messages':[
            {'role':'system','content':SYSTEM_INSTRUCTION},
            {'role':'user','content':judge_prompt(claim,excerpt)}],
            'max_tokens':max_tokens}

    @staticmethod
    def parse(raw, excerpt):
        if not isinstance(raw,dict):raise DecodeFailure('Not a JSON object')
        if raw.get('model')!=BASETEN_MODEL:raise DecodeFailure('Model mismatch')
        if not isinstance(raw.get('id'),str) or not raw['id']:
            raise DecodeFailure('Missing response ID')
        choices=raw.get('choices')
        if not isinstance(choices,list) or len(choices)!=1:
            raise DecodeFailure('Require exactly one choice')
        ch=choices[0]
        if ch.get('finish_reason')!='stop':raise DecodeFailure('Incomplete generation')
        msg=ch.get('message') or {}
        text=msg.get('content')
        if not isinstance(text,str):raise DecodeFailure('Missing text')
        parsed=_output_json(text,excerpt)
        return ParsedJudge('baseten_chat',BASETEN_MODEL,raw['id'],parsed['verdict'],
                           parsed['quote'],parsed['explanation'],_usage_baseten(raw),canon_hash(raw))


def evidence_decision(parsed:ParsedJudge, rule_decision:str):
    """Provider output can never rewrite a deterministic WARN/ABSTAIN."""
    gate=judge_gate(parsed.verdict,rule_decision)
    return {'rule_decision':rule_decision,'model_verdict':parsed.verdict,
            'decision':gate['decision'],'override':False,'model_provenance':PROVENANCE,
            'reason':gate['reason']}
