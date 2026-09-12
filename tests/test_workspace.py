"""Deterministic regression checks. No live feeds, accounts or payment calls."""
import importlib
import sqlite3
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient
from domain import analyze,dt,evaluate_reaction,iso,normalize_event,number,research_context,trade_cost
from datastore import Store,StoreUnavailable
from providers import Feeds

NOW=datetime(2026,8,7,12,30,tzinfo=timezone.utc)
def event(name='CPI MoM',actual=.4,forecast=.3,previous=.2,**extra):
    return {'id':name,'name':name,'time':iso(NOW),'time_exact':True,'actual':actual,'forecast':forecast,'previous':previous,'revised_previous':None,'importance':'high','provider':'TEST FIXTURE',**extra}

@pytest.mark.parametrize('raw,expected',[('152K',152000),('0.3%',.3),('−1,234',-1234),(0,0),(None,None),('NaN',None),(float('inf'),None),(True,None),('garbage',None)])
def test_numeric_normalization(raw,expected):assert number(raw)==expected

def test_te_revision_zero_and_timestamp():
    e=normalize_event({'Date':iso(NOW),'CalendarId':'fixture','Event':'CPI MoM','Actual':'.2%','Forecast':'.3%','Previous':'.1%','Revised':0},'Trading Economics')
    assert e['previous']==0 and e['revised_previous']==.1 and dt(e['time'])==NOW

def test_phase_changes_bias_and_conflicts_are_visible():
    e=event(actual=.1)
    assert analyze([e],'before',NOW)['bias']=='SELL'
    assert analyze([e],'after',NOW)['bias']=='BUY'
    a=analyze([event('Nonfarm Payrolls',200000,150000,140000),event('Unemployment Rate',4.3,4.1,4.1)],'after',NOW)
    assert a['mixed'] and a['coverage']==100
    assert 0<=a['volatility_score']<=100 and 'confidence' not in a

def test_missing_actual_never_becomes_prediction():
    a=analyze([event(actual=None)],'after',NOW)
    assert a['bias']=='UNAVAILABLE' and a['coverage']==0

def test_macro_excludes_future_and_old_data():
    rows=[event(time=iso(NOW-timedelta(days=1))),event(time=iso(NOW+timedelta(minutes=1))),event(time=iso(NOW-timedelta(days=15)))]
    c=research_context(rows,now=NOW)
    assert c['count']==1 and c['gold_score']<0
    assert analyze([event()],phase='after',context=c)['macro_contribution']==0

def test_cost_roundtrip_and_no_double_spread():
    d={'lots':.02,'contract_size':100,'entry':3000,'target':3002,'spread':.2,'commission':7,'slippage':.1,'usd_to_account':4.5,'currency':'MYR'}
    a=trade_cost(d)
    assert a['gross']==18 and a['total_cost']==3.33 and a['net']==14.67
    assert a['breakeven_price']==3000.37
    assert trade_cost({**d,'price_mode':'execution'})['spread_cost']==0
    assert trade_cost({**d,'side':'SELL','target':2998})['gross']==18
    with pytest.raises(ValueError):trade_cost({**d,'lots':float('nan')})

def bars():
    return [{'time':iso(NOW+timedelta(minutes=i)),'open':3000+i,'high':3002+i,'low':2999+i,'close':3001+i,'is_open':False} for i in range(-1,15)]

def test_exact_reaction_boundaries_no_lookahead():
    a={**analyze([event(actual=.1)],'before',NOW-timedelta(minutes=10)),'bias':'BUY'}
    r=evaluate_reaction(a,bars(),NOW+timedelta(minutes=15))
    assert r['baseline']==3000
    assert r['outcomes']['1']['delta_usd']==1 and r['outcomes']['15']['delta_usd']==15
    assert r['outcomes']['15']['result']=='correct'
    assert evaluate_reaction(a,bars(),NOW+timedelta(seconds=59))['outcomes']=={}
    assert evaluate_reaction(a,bars()[1:],NOW+timedelta(minutes=15))['status']=='missing_baseline'
    assert evaluate_reaction(a,bars()[:-1],NOW+timedelta(minutes=15))['outcomes']['15']['status']=='missing_data'
    a['generated_at']=iso(NOW+timedelta(seconds=1))
    assert evaluate_reaction(a,bars(),NOW+timedelta(minutes=15))['outcomes']['15']['result']=='context'

@pytest.fixture
def store(tmp_path,monkeypatch):
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    return Store(SimpleNamespace(sb_ready=lambda:False,DEMO_MODE=True))

def test_snapshots_immutable_and_journal_private(store):
    a=analyze([event()],'before',NOW-timedelta(minutes=10));store.snapshot(a);store.snapshot({**a,'bias':'BUY'})
    assert len(store.history())==1 and store.history()[0]['bias']==a['bias']
    with store.db() as c:
        with pytest.raises(sqlite3.IntegrityError):c.execute('update snapshots set bias=? where id=?',('BUY',a['id']))
    store.journal_save('alice','one',{'notes':'private'})
    assert not store.journal_list('bob')
    assert not store.journal_delete('bob','one')
    assert store.journal_delete('alice','one') and not store.journal_list('alice')
    assert store.journal_delete('alice','one',False) and len(store.journal_list('alice'))==1
    store.preferences('alice',{'enabled':True});assert not store.preferences('bob')['enabled']

def test_provider_preserves_stale_timestamp_and_backoff(monkeypatch):
    feeds=Feeds();feeds.enabled=True
    first=feeds.cached('x',0,lambda:{'price':123},{});resp=requests.Response();resp.status_code=429;resp.headers['Retry-After']='120'
    def fail():raise requests.HTTPError(response=resp)
    stale=feeds.cached('x',0,fail,{})
    assert stale['price']==123 and stale['status']=='stale' and stale['retrieved_at']==first['retrieved_at']
    assert feeds.cache['x']['retry_at']>time.monotonic()+100
    assert feeds.cached('x',0,lambda:pytest.fail('must respect retry-after'),{})['status']=='stale'

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DEMO_MODE','true');monkeypatch.setenv('LIVE_DATA_ENABLED','false');monkeypatch.setenv('ENABLE_RECORDER','false');monkeypatch.setenv('DATA_DIR',str(tmp_path))
    monkeypatch.delenv('OPENAI_API_KEY',raising=False);monkeypatch.delenv('OPENAI_MODEL',raising=False)
    module=importlib.import_module('app');monkeypatch.setattr(module,'DEMO_MODE',True)
    module.workspace.feeds=Feeds();module.workspace.store=Store(module);module.workspace.rate_buckets.clear()
    with TestClient(module.app) as c:yield c,module

def login(client):
    c,_=client
    assert c.post('/api/auth/login',json={'email':'demo@thysmy.local','password':'demo12345'},headers={'X-THYSMY-Request':'1'}).status_code==200

def test_page_routes_and_asset_references(client):
    import re
    c,_=client
    for route in ('/','/dashboard','/login','/register','/pricing','/payment/return','/methodology'):
        r=c.get(route);assert r.status_code==200
        assert '<html lang="ms"' in r.text
        assert 'script-src \'self\'' in r.headers['content-security-policy']
        assert not re.search(r'\son\w+\s*=',r.text,re.I)
        for path in re.findall(r'(?:src|href)="(/static/[^"]+)"',r.text):assert c.get(path).status_code==200,path
    assert c.get('/api/workspace').json()['calendar']['status']=='unavailable'

def test_auth_access_csrf_and_invalid_payloads(client):
    c,_=client
    for route in ('/api/history','/api/journal','/api/alerts','/api/admin/system','/api/admin/migration'):assert c.get(route).status_code==401
    assert c.post('/api/calculator',json={}).status_code==403
    headers={'X-THYSMY-Request':'1','Content-Type':'application/json'}
    assert c.post('/api/calculator',content='[1,2]',headers=headers).status_code==400
    assert c.post('/api/calculator',content='{broken',headers=headers).status_code==400
    assert c.post('/api/journal',headers=headers).status_code==400
    assert c.post('/api/auth/login',json={},headers={**headers,'Origin':'https://evil.invalid'}).status_code==403

def test_full_authenticated_tools_flow(client):
    c,m=client;login(client);headers={'X-THYSMY-Request':'1'}
    assert c.get('/api/admin/system').status_code==403
    sim=c.post('/api/simulate',json={'events':[{'name':'CPI MoM','actual':.2,'forecast':.3}]},headers=headers).json()
    assert sim['bias']=='BUY' and sim['simulation'] and not sim['saved_to_track_record']
    assert c.get('/api/history').json()['count']==0
    prefs=c.post('/api/alerts',json={'enabled':True,'categories':['CPI','invalid'],'minutes':[5,15],'release':True},headers=headers).json()
    assert prefs['preferences']['categories']==['CPI']
    assert c.get('/api/alerts').json()['delivery']=='browser_open'
    trade={'side':'BUY','lots':.02,'entry':3000,'exit':3002,'contract_size':100,'notes':'=SUM(A1)','event':'TEST FIXTURE'}
    saved=c.post('/api/journal',json=trade,headers=headers)
    assert saved.status_code==200,saved.text
    entry=saved.json()['entry'];assert entry['net']==4
    assert "'=SUM(A1)" in c.get('/api/journal/export').text
    assert c.post('/api/journal/'+entry['id']+'/archive',json={},headers=headers).status_code==200
    assert c.get('/api/journal').json()['entries']==[]
    assert c.get('/api/journal?archived=true').json()['entries'][0]['id']==entry['id']
    assert c.post('/api/journal/'+entry['id']+'/archive',json={'restore':True},headers=headers).status_code==200
    guide=c.post('/api/assistant',json={'question':'Apa maksud CPI?'},headers=headers)
    assert guide.status_code==200 and guide.json()['mode']=='guide'
    assert c.post('/api/payment/create',json={},headers=headers).json()['demo']
    assert c.post('/api/auth/logout',json={},headers=headers).status_code==200
    assert c.get('/api/journal').status_code==401

def test_payment_amount_verification_and_retry(client,monkeypatch):
    _,m=client;calls=[]
    payment={'order_id':'TEST-ORDER','bill_code':'TEST-BILL','amount_sen':2900,'status':'pending','raw':{'pro_days':30}}
    def rest(method,table,**kw):
        if table=='payments':return [payment]
        calls.append((table,kw));return {'ok':True}
    monkeypatch.setattr(m,'sb_rest',rest)
    tx={'billpaymentStatus':'1','billExternalReferenceNo':'TEST-ORDER','billpaymentAmount':'29.00','billpaymentInvoiceNo':'TEST-REF'}
    monkeypatch.setattr(requests,'post',lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,json=lambda:[tx]))
    assert m.workspace.settle('TEST-ORDER','TEST-BILL','')['ok']
    assert calls[0][0]=='rpc/thysmy_settle_payment' and calls[0][1]['payload']['p_days']==30
    calls.clear();tx['billpaymentAmount']='28.99'
    with pytest.raises(HTTPException):m.workspace.settle('TEST-ORDER','TEST-BILL','')
    assert not calls
    tx['billpaymentAmount']='28.999'
    with pytest.raises(HTTPException):m.workspace.settle('TEST-ORDER','TEST-BILL','')
    payment['status']='success'
    assert m.workspace.settle('TEST-ORDER','TEST-BILL','')['already_settled'] and not calls

def test_payment_status_is_owned_and_url_not_authoritative(client,monkeypatch):
    c,m=client;login(client);filters=[]
    monkeypatch.setattr(m,'sb_ready',lambda:True)
    def rest(method,table,**kw):filters.append(kw['params']);return []
    monkeypatch.setattr(m,'sb_rest',rest)
    assert c.get('/api/payment/status?order_id=SOMEONE-ELSE').status_code==404
    assert filters[0]['user_id']=='eq.demo-user'
    r=c.get('/payment/return?status_id=1&order_id=FAKE')
    assert 'Bayaran disahkan.' not in r.text
    assert c.post('/api/payment/callback',data={'hash':'invalid','status':'1'}).status_code==400

def test_missing_remote_tables_do_not_silently_fallback(tmp_path,monkeypatch):
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    def fail(*a,**k):raise RuntimeError('missing table')
    s=Store(SimpleNamespace(sb_ready=lambda:True,DEMO_MODE=False,sb_rest=fail))
    assert not s.health()['ready'] and not s.path.exists()
    with pytest.raises(StoreUnavailable):s.history()
