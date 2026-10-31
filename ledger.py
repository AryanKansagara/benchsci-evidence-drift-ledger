"""Declared synthetic claims, immutable source bytes, deterministic dependency rules."""
import argparse
from dataclasses import dataclass, replace
import hashlib
import json
import re

ALIASES={'ERK2':'MAPK1','MAPK1':'MAPK1','TP53':'TP53','p53':'TP53'}
def canonical(entity): return ALIASES.get(entity,entity)
def normalized(text): return ' '.join(re.sub(r'\b(?:ERK2|p53)\b', lambda m: canonical(m.group()), text).split())

@dataclass(frozen=True)
class Claim:
    id: str
    entity: str
    condition: str
    predicate: str
    supports: bool
    start: int
    end: int
    quote: str
    def __post_init__(self):
        if any(type(v) is not str or not v for v in (self.id,self.entity,self.predicate,self.quote)) or type(self.condition) is not str:
            raise ValueError('claim IDs, entity, condition, predicate and quote must be immutable strings')
        if type(self.supports) is not bool or type(self.start) is not int or type(self.end) is not int:
            raise ValueError('claim polarity and span must have strict primitive types')

@dataclass(frozen=True)
class Document:
    id: str
    version: int
    text: str
    claims: tuple
    @property
    def sha256(self): return hashlib.sha256(self.text.encode('utf-8')).hexdigest()
    def __post_init__(self):
        if type(self.id) is not str or not self.id or type(self.text) is not str or type(self.version) is not int or self.version < 1 or type(self.claims) is not tuple:
            raise ValueError('invalid immutable document version')
        try:self.text.encode('utf-8')
        except UnicodeEncodeError:raise ValueError('document text must be valid UTF-8') from None
        seen=set()
        for c in self.claims:
            if not isinstance(c,Claim) or not c.id or c.id in seen:raise ValueError('duplicate or invalid claim')
            seen.add(c.id)
            if type(c.supports) is not bool or not all(isinstance(v,str) and v for v in (c.entity,c.predicate,c.quote)):
                raise ValueError('claim fields invalid')
            if type(c.start) is not int or type(c.end) is not int or not 0<=c.start<c.end<=len(self.text):
                raise ValueError('source span out of bounds')
            if self.text[c.start:c.end]!=c.quote:raise ValueError('source span does not match quote')

@dataclass(frozen=True)
class Decision:
    id: str
    dependencies: tuple
    def __post_init__(self):
        if type(self.id) is not str or not self.id or type(self.dependencies) is not tuple or not self.dependencies or any(type(v) is not str or not v for v in self.dependencies):
            raise ValueError('decision requires an immutable ID and nonempty tuple of claim ID strings')

class Ledger:
    def __init__(self): self._versions={}
    def add(self,doc):
        if not isinstance(doc,Document):raise ValueError('only immutable documents may be stored')
        key=(doc.id,doc.version)
        if key in self._versions:raise ValueError('version already exists; immutable append only')
        prior=[v for d,v in self._versions if d==doc.id]
        if doc.version != (max(prior)+1 if prior else 1):raise ValueError('versions must be contiguous from one')
        self._versions[key]=doc
    def get(self,id,version):return self._versions[(id,version)]

def compare(before,after,decisions):
    if before.id!=after.id or after.version!=before.version+1:raise ValueError('expected adjacent versions of one document')
    old={c.id:c for c in before.claims};new={c.id:c for c in after.claims}
    changes={}
    for id,c in old.items():
        n=new.get(id)
        if n is None: state,reason='stale','cited claim removed'
        elif (canonical(c.entity),c.condition,c.predicate)!=(canonical(n.entity),n.condition,n.predicate) or not n.condition:
            state,reason='review-required','entity, condition or predicate changed/missing'
        elif c.supports!=n.supports:state,reason='contradicted','declared polarity reversed in the same context'
        elif normalized(c.quote)!=normalized(n.quote):state,reason='review-required','source wording changed; semantic equivalence not inferred'
        else:state,reason='unchanged','same declared claim/context and normalized cited span'
        changes[id]={'status':state,'reason':reason,
                     'before':{'sha256':before.sha256,'span':[c.start,c.end],'quote':c.quote},
                     'after':None if n is None else {'sha256':after.sha256,'span':[n.start,n.end],'quote':n.quote}}
    priority={'unchanged':0,'stale':1,'review-required':2,'contradicted':3}
    packets=[]
    for d in decisions:
        if not d.dependencies or any(id not in old for id in d.dependencies):raise ValueError('decision must cite existing old claim IDs')
        evidence=[dict(claim=id,**changes[id]) for id in d.dependencies]
        status=max((v['status'] for v in evidence),key=priority.get)
        packets.append({'decision':d.id,'status':status,'dependencies':evidence})
    return {'document':before.id,'from_version':before.version,'to_version':after.version,
            'classification':'authored structured claims; no biological truth inference','decisions':packets}

def fixture(mode='contradiction'):
    lines=['MAPK1 supports growth in cell-A.','TP53 supports arrest in cell-B.']
    text='\n'.join(lines)
    claims=(Claim('c1','MAPK1','cell-A','growth',True,0,len(lines[0]),lines[0]),
            Claim('c2','TP53','cell-B','arrest',True,len(lines[0])+1,len(text),lines[1]))
    before=Document('synthetic-study',1,text,claims)
    if mode=='formatting':
        text=text.replace('supports',' supports ')
        lines=text.split('\n'); updated=tuple(replace(c,start=0 if i==0 else len(lines[0])+1,
             end=len(lines[0]) if i==0 else len(text),quote=lines[i]) for i,c in enumerate(claims))
    elif mode=='removed':updated=claims[1:]
    elif mode=='condition':updated=(replace(claims[0],condition='cell-C'),claims[1])
    elif mode=='missing-context':updated=(replace(claims[0],condition=''),claims[1])
    elif mode=='synonym':updated=(replace(claims[0],entity='ERK2'),claims[1])
    elif mode=='wording':updated=(replace(claims[0],predicate='growth-rate'),claims[1])
    elif mode=='contradiction':updated=(replace(claims[0],supports=False),claims[1])
    elif mode=='unchanged':updated=claims
    else:raise ValueError('unsupported fixture')
    if mode in ('contradiction','condition','missing-context','synonym'):
        first=lines[0]
        if mode=='contradiction':first=first.replace('supports','inhibits')
        if mode=='condition':first=first.replace('cell-A','cell-C')
        if mode=='missing-context':first=first.replace(' in cell-A','')
        if mode=='synonym':first=first.replace('MAPK1','ERK2')
        text=first+'\n'+lines[1]
        updated=(replace(updated[0],start=0,end=len(first),quote=first),
                 replace(updated[1],start=len(first)+1,end=len(text),quote=lines[1]))
    after=Document(before.id,2,text,updated)
    decisions=(Decision('experiment-A',('c1',)),Decision('experiment-B',('c2',)),Decision('combined',('c1','c2')))
    return before,after,decisions

def demo():
    result={}
    for mode in ('contradiction','removed','condition','missing-context','synonym','formatting','unchanged'):
        before,after,decisions=fixture(mode);store=Ledger();store.add(before);store.add(after)
        result[mode]=compare(store.get(before.id,1),store.get(before.id,2),decisions)
    return {'schema_version':1,'data':'authored synthetic; no patient/experimental measurements','cases':result}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    payload=json.dumps(demo(),indent=2)
    if args.output:
        with open(args.output,'w') as file:file.write(payload+'\n')
    print(payload)
