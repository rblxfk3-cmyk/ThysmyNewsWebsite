"""Read-only provider adapters with shared caching, bounded latency and honest freshness."""
from __future__ import annotations
import copy
import csv
import io
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlparse
import requests
from domain import dt,iso,number,normalize_event,url,utcnow

class Feeds:
    def __init__(self):
        self.cache={};self.locks={};self.guard=threading.Lock()
        self.enabled=os.getenv('LIVE_DATA_ENABLED','true').lower()=='true'
    def cached(self,key,ttl,fn,empty):
        now=time.monotonic()
        with self.guard: lock=self.locks.setdefault(key,threading.Lock())
        with lock:
            prior=self.cache.get(key)
            if prior and now<prior.get('retry_at',prior['attempt']+ttl): return copy.deepcopy(prior['value'])
            try:
                if not self.enabled: raise RuntimeError('disabled')
                value=fn();value.update({'retrieved_at':iso(),'ok':True})
                if 'status' not in value:value['status']='live'
                self.cache[key]={'attempt':now,'value':value}
            except Exception as exc:
                value=copy.deepcopy(prior['value']) if prior else copy.deepcopy(empty)
                value.update({'status':'stale' if value.get('ok') else 'unavailable','error':'Sumber belum dapat dicapai. Cuba lagi kemudian.'})
                response=getattr(exc,'response',None);delay=ttl
                if response is not None and response.status_code==429:
                    retry=number(response.headers.get('Retry-After'))
                    delay=max(ttl,min(retry or 60,3600))
                self.cache[key]={'attempt':now,'retry_at':now+delay,'value':value}
            return copy.deepcopy(value)
    def get(self,target,params=None):
        r=requests.get(target,params=params,headers={'User-Agent':'THYSMY-News/4.0 (+https://github.com/rblxfk3-cmyk/ThysmyNewsWebsite)','Accept':'application/json'},timeout=(3,8))
        r.raise_for_status();return r
    def calendar(self):
        def fetch():
            start=(utcnow()-timedelta(days=15)).date().isoformat();end=(utcnow()+timedelta(days=30)).date().isoformat()
            te=os.getenv('TRADING_ECONOMICS_KEY','')
            if te:
                rows=self.get(f'https://api.tradingeconomics.com/calendar/country/united%20states/{start}/{end}',{'c':te,'f':'json'}).json();provider='Trading Economics'
            else:
                rows=self.get('https://biquote.io/api/calendar',{'from':start+'T00:00:00Z','to':end+'T23:59:59Z','countries':'US','importance':'medium','limit':1000}).json();provider='BiQuote'
            if not isinstance(rows,list): raise ValueError('calendar')
            events=[e for r in rows if isinstance(r,dict) and (e:=normalize_event(r,provider))]
            events=list({e['id']:e for e in events}.values());events.sort(key=lambda e:e['time'])
            return {'events':events,'provider':provider,'source_url':'https://tradingeconomics.com/calendar' if te else 'https://biquote.io/docs/'}
        result=self.cached('calendar',30,fetch,{'ok':False,'events':[],'provider':'BiQuote','retrieved_at':None})
        age=(utcnow()-dt(result['retrieved_at'])).total_seconds() if dt(result.get('retrieved_at')) else None
        if age is not None and age>120:result['status']='stale'
        return result
    def markets(self):
        def fetch():
            rows=self.get('https://biquote.io/api/latest',[('symbols','XAUUSD'),('symbols','DXY')]).json()
            if isinstance(rows,dict): rows=rows.get('items') or rows.get('ticks') or list(rows.values())
            if not isinstance(rows,list): raise ValueError('quote')
            return {'quotes':{str(r.get('symbol')):r for r in rows if isinstance(r,dict) and r.get('symbol') in ('XAUUSD','DXY')}}
        bundle=self.cached('markets',8,fetch,{'ok':False,'quotes':{},'retrieved_at':None})
        quotes={}
        for symbol in ('XAUUSD','DXY'):
            raw=bundle.get('quotes',{}).get(symbol,{})
            ts=dt(raw.get('timestamp') or raw.get('lastQuoteAt'));price=number(raw.get('mid'))
            age=max(0,(utcnow()-ts).total_seconds()) if ts else None
            closed=raw.get('marketState')=='closed'
            stale=bool(raw.get('stale')) or age is None or age>90 or bundle.get('status')=='stale'
            state='unavailable' if price is None or price<=0 else 'closed' if closed else 'stale' if stale else 'live'
            quotes[symbol]={'symbol':symbol,'price':price if price and price>0 else None,'change':number(raw.get('dayDiffPercent')) if state=='live' else None,
              'bid':number(raw.get('bid')),'ask':number(raw.get('ask')),'spread':number(raw.get('spread')),
              'status':state,'timestamp':iso(ts) if ts else None,'retrieved_at':bundle.get('retrieved_at'),
              'source':str(raw.get('source') or 'BiQuote'),'source_url':'https://biquote.io/docs/','age_seconds':age}
        return quotes
    def treasury(self):
        def fetch():
            raw=self.get('https://fred.stlouisfed.org/graph/fredgraph.csv',{'id':'DGS10','cosd':(utcnow()-timedelta(days=20)).date().isoformat()}).text
            rows=[r for r in csv.DictReader(io.StringIO(raw)) if number(r.get('DGS10')) is not None]
            if not rows:raise ValueError('yield')
            last=rows[-1];value=number(last['DGS10']);previous=number(rows[-2]['DGS10']) if len(rows)>1 else None
            timestamp=last.get('DATE') or last.get('observation_date')
            return {'symbol':'US10Y','price':value,'change':round((value-previous)*100,2) if previous is not None else None,'timestamp':timestamp,'status':'daily','source':'FRED · Federal Reserve H.15','source_url':'https://fred.stlouisfed.org/series/DGS10'}
        result=self.cached('treasury',3600,fetch,{'ok':False,'symbol':'US10Y','price':None,'change':None,'timestamp':None,'source':'FRED','source_url':'https://fred.stlouisfed.org/series/DGS10'})
        stamp=dt(result.get('timestamp'))
        if stamp and (utcnow()-stamp).days>5:result['status']='stale'
        return result
    def candles(self,interval='5m',start=None,end=None,limit=120):
        key=f'ohlc:{interval}:{start}:{end}:{limit}'
        def fetch():
            params={'interval':interval,'limit':limit}
            if start:params['from']=start
            if end:params['to']=end
            obj=self.get('https://biquote.io/api/XAUUSD/ohlc',params).json()
            raw=obj.get('bars',[]) if isinstance(obj,dict) else []
            bars=[]
            for b in raw:
                stamp=dt(b.get('openTime'))
                values={k:number(b.get(k)) for k in ('open','high','low','close')}
                if not stamp or any(v is None or v<=0 for v in values.values()):continue
                if values['high']<max(values['open'],values['close'],values['low']) or values['low']>min(values['open'],values['close']):continue
                bars.append({'time':iso(stamp),**values,'is_open':bool(b.get('isOpen'))})
            bars=sorted({b['time']:b for b in bars}.values(),key=lambda b:b['time'])
            return {'bars':bars,'interval':interval,'source':'BiQuote OHLC','source_url':'https://biquote.io/docs/'}
        return self.cached(key,30 if start is None else 60,fetch,{'ok':False,'bars':[],'interval':interval,'source':'BiQuote OHLC'})
    def news(self):
        def fetch():
            q='(gold OR "Federal Reserve" OR inflation OR "Treasury yields" OR geopolitical OR sanctions) sourcelang:english'
            obj=self.get('https://api.gdeltproject.org/api/v2/doc/doc',{'query':q,'mode':'artlist','format':'json','maxrecords':40,'timespan':'12h','sort':'datedesc'}).json()
            if not isinstance(obj,dict) or not isinstance(obj.get('articles'),list):raise ValueError('news')
            articles=[];seen=set()
            for a in obj['articles']:
                link=url(a.get('url'));title=str(a.get('title') or '')[:350]
                if not link or not title or link in seen:continue
                seen.add(link);raw=str(a.get('seendate') or '');stamp=None
                try:
                    from datetime import datetime,timezone
                    stamp=datetime.strptime(raw,'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).isoformat()
                except ValueError:pass
                lower=title.lower();category='Makroekonomi'
                context='Baca sumber asal untuk butiran penuh. Tajuk sahaja tidak cukup untuk menentukan arah gold.'
                if any(t in lower for t in ('fed','rate','yield')):category='Kadar faedah';context='Semak nada dasar monetari serta perubahan jangkaan kadar dan hasil bon.'
                if any(t in lower for t in ('war','attack','geopolit','sanction')):category='Geopolitik';context='Pantau perkembangan dan reaksi pasaran; kesan permintaan aset perlindungan tidak semestinya sehala.'
                if any(t in lower for t in ('inflation','cpi','ppi')):category='Inflasi';context='Bandingkan data sebenar dengan konsensus dan komponen teras sebelum mentafsir reaksi.'
                articles.append({'title':title,'url':link,'source':urlparse(link).hostname,'observed_at':stamp,'category':category,'context_ms':context})
            return {'articles':articles,'source':'GDELT','source_url':'https://www.gdeltproject.org/','summary_type':'Konteks kategori; bukan terjemahan atau ringkasan artikel penuh.'}
        return self.cached('news',900,fetch,{'ok':False,'articles':[],'source':'GDELT'})
    def snapshot(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            fs=[pool.submit(fn) for fn in (self.calendar,self.markets,self.treasury,self.news)]
            cal,markets,treasury,news=[f.result() for f in fs]
        return {'calendar':cal,'markets':{**markets,'US10Y':treasury},'news':news,'server_time':iso()}
