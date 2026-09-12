"""Pure, versioned research rules. Scores are not calibrated probabilities."""
from __future__ import annotations
import hashlib
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = '4.0.0'
RULES = [
 ('unemployment rate',-1,3,'LABOR'),('initial jobless claims',-1,2,'LABOR'),
 ('continuing jobless claims',-1,1,'LABOR'),('nonfarm',1,3.5,'LABOR'),('non-farm',1,3.5,'LABOR'),
 ('average hourly earnings',1,2.5,'LABOR'),('adp',1,2,'LABOR'),('employment change',1,2,'LABOR'),
 ('job openings',1,1.5,'LABOR'),('core cpi',1,3,'INFLATION'),('cpi',1,2.8,'INFLATION'),
 ('consumer price index',1,2.8,'INFLATION'),('core pce',1,3,'INFLATION'),('pce',1,2.5,'INFLATION'),
 ('ppi',1,1.8,'INFLATION'),('producer price index',1,1.8,'INFLATION'),
 ('gross domestic product',1,2.4,'GROWTH'),('gdp',1,2.4,'GROWTH'),('retail sales',1,2,'GROWTH'),
 ('ism',1,1.7,'GROWTH'),('pmi',1,1.3,'GROWTH'),('consumer confidence',1,1.2,'GROWTH'),
 ('interest rate',1,3.5,'RATES'),('federal funds',1,3.5,'RATES'),('fed funds',1,3.5,'RATES'),
 ('fomc',0,3,'RATES'),('fed chair',0,2.5,'RATES'),('powell',0,2.5,'RATES')]

def utcnow(): return datetime.now(timezone.utc)
def iso(dt=None): return (dt or utcnow()).isoformat()
def dt(value):
    if value is None: return None
    try:
        if isinstance(value,(int,float)):
            return datetime.fromtimestamp(value/1000 if value>1e11 else value,timezone.utc)
        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed).astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError,OSError): return None

def number(value):
    if value is None or isinstance(value,bool): return None
    if isinstance(value,(float,int)): return float(value) if math.isfinite(value) else None
    raw=str(value).strip().replace(',','').replace('−','-')
    match=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([KMBkmb%]?)',raw)
    if not match: return None
    n=float(match[1])*{'K':1e3,'M':1e6,'B':1e9}.get(match[2].upper(),1)
    return n if math.isfinite(n) else None

def url(value):
    value=str(value or '')[:2000]
    try:
        p=urlparse(value)
        return value if p.scheme in ('https','http') and p.hostname and not p.username else ''
    except ValueError: return ''

def rule_for(name):
    text=(name or '').lower()
    for token,sign,weight,category in RULES:
        if token in text: return {'sign':sign,'weight':weight,'category':category}
    return {'sign':0,'weight':0,'category':'OTHER'}

def label_for(events):
    names=' '.join(e.get('name','') for e in events).lower()
    for tokens,label in [(['nonfarm','non-farm'],'NFP'),(['cpi','consumer price'],'CPI'),(['ppi','producer price'],'PPI'),(['fomc','interest rate','fed funds','federal funds'],'FOMC'),(['pce'],'PCE')]:
        if any(t in names for t in tokens): return label
    return events[0].get('name','USD News') if events else 'USD News'

def normalize_event(row,provider='BiQuote'):
    te=provider=='Trading Economics'
    timestamp=dt(row.get('Date') if te else row.get('time'))
    if not timestamp: return None
    name=str(row.get('Event') if te else row.get('name') or 'USD Event')[:200]
    raw_importance=row.get('Importance') if te else row.get('importance','low')
    importance={1:'low',2:'medium',3:'high'}.get(raw_importance,str(raw_importance).lower())
    previous=(row.get('Revised') if row.get('Revised') not in (None,'') else row.get('Previous')) if te else row.get('previous')
    revised=row.get('Previous') if te and row.get('Revised') not in (None,'') else row.get('revisedPrevious')
    event_id=str(row.get('CalendarId') if te else row.get('id') or row.get('eventId') or '')
    event_id=hashlib.sha256((provider+'|'+event_id+'|'+iso(timestamp)+'|'+name).encode()).hexdigest()[:24]
    return {'id':event_id,'series_id':str(row.get('Ticker') if te else row.get('eventId') or ''),
      'time':iso(timestamp),'name':name,'importance':importance,'country':'US','currency':'USD',
      'actual':number(row.get('Actual') if te else row.get('actual')),
      'forecast':number(row.get('Forecast') if te else row.get('forecast')),
      'previous':number(previous),'revised_previous':number(revised),
      'unit':str(row.get('Unit') if te else row.get('unit') or ''),
      'time_exact':str(row.get('DateSpan','0'))=='0' if te else row.get('timeMode','exact')=='exact',
      'source':str(row.get('Source') if te else row.get('source') or provider),
      'source_url':url(row.get('SourceURL') if te else row.get('sourceUrl')),
      'provider':provider,'updated_at':row.get('LastUpdate') if te else row.get('updatedAt'),
      'category':rule_for(name)['category']}

def group_events(events):
    groups={}
    for e in events:
        if e.get('time_exact') and rule_for(e['name'])['weight']:
            groups.setdefault(e['time'],[]).append(e)
    return [groups[t] for t in sorted(groups)]

def research_context(events,news=None,now=None):
    """Prior released data only; headline clues are deliberately not trading signals."""
    now=now or utcnow(); categories={}; evidence=[]
    for e in events:
        stamp=dt(e.get('time'))
        if not stamp or not 0<(now-stamp).total_seconds()<=14*86400 or e.get('actual') is None:continue
        r=rule_for(e['name']);forecast=e.get('forecast')
        if not r['sign'] or forecast is None:continue
        diff=e['actual']-forecast
        weight=r['weight']/(1+(now-stamp).total_seconds()/86400/7)
        score=-(1 if diff>0 else -1 if diff<0 else 0)*r['sign']*weight
        bucket=categories.setdefault(r['category'],{'score':0,'weight':0,'count':0})
        bucket['score']+=score;bucket['weight']+=weight;bucket['count']+=1
        evidence.append({'name':e['name'],'time':e['time'],'actual':e['actual'],'forecast':forecast,'gold_score':round(score,3),'source':e.get('provider'),'source_url':e.get('source_url')})
    normalized=[v['score']/v['weight'] for v in categories.values() if v['weight']]
    score=round(sum(normalized)/len(normalized)*2,3) if normalized else 0
    for v in categories.values():v['score']=round(v['score'],3)
    return {'lookback_days':14,'count':len(evidence),'gold_score':score,'bias':'BUY' if score>.4 else 'SELL' if score<-.4 else 'NEUTRAL' if evidence else 'UNAVAILABLE',
      'categories':categories,'evidence':sorted(evidence,key=lambda e:e['time'],reverse=True)[:8],
      'global':{'status':(news or {}).get('status','unavailable'),'retrieved_at':(news or {}).get('retrieved_at'),
        'topics':{k:sum(a.get('category')==k for a in (news or {}).get('articles',[])) for k in ('Geopolitik','Kadar faedah','Inflasi','Makroekonomi')},
        'note':'Konteks tajuk 12 jam. Kategori kata kunci, bukan sentimen yang disahkan atau ramalan arah.'}}

def analyze(events,phase='before',now=None,context=None):
    now=now or utcnow()
    components=[]
    for e in events:
        rule=rule_for(e['name']); actual=e.get('actual'); forecast=e.get('forecast')
        previous=e.get('revised_previous') if e.get('revised_previous') is not None else e.get('previous')
        left=actual if phase in ('after','simulation') else forecast
        right=forecast if phase in ('after','simulation') else previous
        available=left is not None and right is not None and rule['sign']!=0
        direction=0 if not available or math.isclose(left,right,abs_tol=1e-9) else (1 if left>right else -1)
        # Unit-invariant capped relative magnitude; explicit heuristic, not a fitted model.
        magnitude=min(1.5,.75+abs(left-right)/max(abs(right),1)*1.5) if direction else 0
        contribution=round(-direction*rule['sign']*rule['weight']*magnitude,3)
        revised=e.get('revised_previous'); original=e.get('previous')
        revision=0.0
        if phase in ('after','simulation') and revised is not None and original is not None and revised!=original:
            revision=round(-(1 if revised>original else -1)*rule['sign']*rule['weight']*.25,3)
        components.append({**e,'gold_score':contribution+revision,'surprise_score':contribution,'revision_score':revision,
          'available':available,'comparison':'Actual vs forecast' if phase!='before' else 'Forecast vs previous',
          'direction':'BUY' if contribution+revision>.001 else 'SELL' if contribution+revision<-.001 else 'NEUTRAL'})
    available=[c for c in components if c['available']]
    pos=sum(c['gold_score'] for c in available if c['gold_score']>0)
    neg=abs(sum(c['gold_score'] for c in available if c['gold_score']<0))
    mixed=pos>0 and neg>0
    event_score=round(pos-neg,3)
    macro_score=context.get('gold_score',0)*.5 if context and phase=='before' else 0
    score=round(event_score+macro_score,3); coverage=len(available)/len(events) if events else 0
    # No guess when most scheduled components have yet to report.
    bias='UNAVAILABLE' if not available and not macro_score else 'NEUTRAL' if abs(score)<.6 or (mixed and abs(event_score)/max(pos+neg,1)<.25) or (available and coverage<.5) else 'BUY' if score>0 else 'SELL'
    max_weight=max([rule_for(e['name'])['weight'] for e in events] or [0])
    impact=max([{'high':3,'medium':2,'low':1}.get(e.get('importance'),1) for e in events] or [0])
    vol=round(min(100,30+impact*10+max_weight*7+min(10,abs(score)))) if events else None
    reasons=[]
    for c in available:
        if c['gold_score']:
            reasons.append(f"{c['name']}: {c['comparison']} memberi kecenderungan {c['direction']} dalam model asas"+(' (termasuk revisi).' if c['revision_score'] else '.'))
    if mixed: reasons.append('Komponen menyokong arah yang berbeza. Reaksi dua hala masih mungkin.')
    if coverage<1: reasons.append(f'{len(available)} daripada {len(events)} komponen boleh dinilai; yang lain belum ada data lengkap atau tiada aturan angka.')
    if phase=='before': reasons.append('Ini konteks jangkaan sebelum keluaran. Forecast vs previous tidak meramal kejutan actual.')
    if context and context['count'] and phase=='before':reasons.append(f"Konteks 14 hari: {context['count']} keluaran boleh dinilai, bias {context['bias']}; sumbangan tambahan {macro_score:+.2f} skor.")
    reasons.append('Harga sebenar boleh bergerak berbeza daripada hubungan asas USD dan emas.')
    return {'id':hashlib.sha256(('v4|'+phase+'|'+'|'.join(sorted(e['id'] for e in events))).encode()).hexdigest()[:32],
      'version':VERSION,'phase':phase,'generated_at':iso(now),'event_time':events[0]['time'] if events else None,
      'label':label_for(events),'bias':bias,'gold_score':score,'volatility_score':vol,
      'volatility_label':'Tinggi' if vol and vol>=75 else 'Sederhana' if vol and vol>=50 else 'Rendah',
      'mixed':mixed,'coverage':round(coverage*100),'agreement_score':round(abs(event_score)/(pos+neg)*100) if pos+neg else None,
      'context':context,'event_score':event_score,'macro_contribution':round(macro_score,3),
      'components':components,'reasons':reasons,'note':'Skor heuristik / 100, bukan kebarangkalian atau jaminan pulangan.'}

def trade_cost(data):
    def n(key,default=None,min_value=None):
        val=number(data.get(key,default))
        if val is None or (min_value is not None and val<min_value): raise ValueError(f'{key}: masukkan nombor yang sah')
        return val
    lots=n('lots',.02,0.000001); contract=n('contract_size',100,.000001)
    entry=n('entry',None,.000001); target=n('target',None,.000001)
    spread=n('spread',0,0); commission=n('commission',0,0); slippage=n('slippage',0,0)
    fx=n('usd_to_account',1,.000001); fixed=n('other_cost',0,0)
    side=data.get('side','BUY')
    if side not in ('BUY','SELL'): raise ValueError('side: BUY atau SELL sahaja')
    if max(lots,contract,entry,target,spread,commission,slippage,fx,fixed)>1e9: raise ValueError('Nilai terlalu besar')
    mode=data.get('price_mode','mid')
    if mode not in ('mid','execution'): raise ValueError('Mod harga tidak sah')
    units=lots*contract; gross=(target-entry)*(1 if side=='BUY' else -1)*units*fx
    # Commission is round-trip, USD / lot. Actual execution prices already embed spread.
    spread_cost=spread*units*fx if mode=='mid' else 0
    costs=spread_cost+slippage*units*fx+commission*lots*fx+fixed
    break_distance=costs/(units*fx)
    return {'gross':round(gross,2),'spread_cost':round(spread_cost,2),'commission_cost':round(commission*lots*fx,2),
      'slippage_cost':round(slippage*units*fx,2),'other_cost':fixed,'total_cost':round(costs,2),
      'net':round(gross-costs,2),'breakeven_distance':round(break_distance,4),
      'breakeven_price':round(entry+(break_distance if side=='BUY' else -break_distance),4),
      'currency':str(data.get('currency','USD'))[:10],'mode':mode}

def evaluate_reaction(snapshot,bars,now=None):
    """Use exact closed M1 boundaries only. Missing bars never become zero returns."""
    from datetime import timedelta
    now=now or utcnow(); release=dt(snapshot['event_time'])
    if not release: return {}
    closed={dt(b.get('time'))+timedelta(minutes=1):b for b in bars if dt(b.get('time')) and not b.get('is_open')}
    baseline=closed.get(release)
    if not baseline or number(baseline.get('close')) is None: return {'status':'missing_baseline','outcomes':{}}
    ref=baseline['close']; outcomes={}
    for minute in (1,5,15):
        end=release+timedelta(minutes=minute)
        if now<end: continue
        b=closed.get(end)
        if not b: outcomes[str(minute)]={'status':'missing_data'};continue
        delta=round(b['close']-ref,4); bias=snapshot['bias']
        result='context' if snapshot.get('phase')!='before' or dt(snapshot.get('generated_at')) is None or dt(snapshot['generated_at'])>=release else 'neutral' if bias not in ('BUY','SELL') else 'flat' if abs(delta)<.00001 else 'correct' if (delta>0)==(bias=='BUY') else 'incorrect'
        window=[v for t,v in closed.items() if release<t<=end]
        outcomes[str(minute)]={'status':'measured','result':result,'price':b['close'],'delta_usd':delta,
          'high_delta':round(max(v['high'] for v in window)-ref,4),'low_delta':round(min(v['low'] for v in window)-ref,4),
          'measured_time':iso(end),'bars_available':len(window),'bars_expected':minute}
    return {'status':'measured','baseline':ref,'baseline_time':iso(release),'outcomes':outcomes,'source':'BiQuote closed M1 OHLC','updated_at':iso(now)}
