"""Durable workspace data. Production uses Supabase; local development uses SQLite."""
from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path
from domain import iso

class StoreUnavailable(RuntimeError): pass

class Store:
    def __init__(self,ctx):
        self.ctx=ctx
        self.remote=ctx.sb_ready() and not ctx.DEMO_MODE
        self.path=Path(os.getenv('DATA_DIR',str(Path(__file__).parent/'data')))/'workspace-v4.sqlite3'
        if not self.remote:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.db() as c:
                c.executescript('''
                create table if not exists snapshots(id text primary key,label text,event_time text,phase text,bias text,created_at text,payload text);
                create index if not exists idx_snapshots_created on snapshots(created_at desc);
                create trigger if not exists snapshots_no_update before update on snapshots begin select raise(abort,'Snapshot is immutable'); end;
                create trigger if not exists snapshots_no_delete before delete on snapshots begin select raise(abort,'Snapshot is immutable'); end;
                create table if not exists outcomes(snapshot_id text primary key references snapshots(id),payload text);
                create table if not exists journal(id text primary key,user_id text,created_at text,payload text,deleted integer default 0);
                create index if not exists idx_journal_user_created on journal(user_id,created_at desc);
                create table if not exists preferences(user_id text primary key,payload text);
                ''')
    def db(self):
        c=sqlite3.connect(self.path,timeout=10);c.row_factory=sqlite3.Row;c.execute('pragma foreign_keys=on');return c
    def api(self,method,table,**kwargs):
        try:return self.ctx.sb_rest(method,table,**kwargs)
        except Exception as e:raise StoreUnavailable('Penyimpanan belum tersedia. Pentadbir perlu semak sambungan pangkalan data V4.') from e
    def health(self):
        try:
            if self.remote:self.api('GET','analysis_snapshots',params={'select':'id','limit':'1'})
            else:
                with self.db() as c:c.execute('select id from snapshots limit 1')
            return {'ready':True,'backend':'supabase' if self.remote else 'sqlite','durable':self.remote or bool(os.getenv('DATA_DIR'))}
        except StoreUnavailable:return {'ready':False,'backend':'supabase','durable':False}
    def snapshot(self,payload):
        row={k:payload[k] for k in ('id','label','event_time','phase','bias')};row['created_at']=payload['generated_at'];row['payload']=payload
        if self.remote:
            self.api('POST','analysis_snapshots',payload=row,prefer='resolution=ignore-duplicates,return=minimal')
        else:
            with self.db() as c:c.execute('insert or ignore into snapshots values(?,?,?,?,?,?,?)',(row['id'],row['label'],row['event_time'],row['phase'],row['bias'],row['created_at'],json.dumps(payload,allow_nan=False)))
    def history(self,limit=200):
        if self.remote:
            rows=self.api('GET','analysis_snapshots',params={'select':'id,payload,created_at','order':'created_at.desc','limit':str(limit)}) or []
            ids=[r['id'] for r in rows]
            outcomes=self.api('GET','analysis_outcomes',params={'select':'snapshot_id,payload','snapshot_id':'in.('+','.join(ids)+')'}) if ids else []
            mapping={r['snapshot_id']:r['payload'] for r in outcomes or []}
            return [{**r['payload'],'reaction':mapping.get(r['id'])} for r in rows]
        with self.db() as c:
            rows=c.execute('select s.payload,o.payload as reaction from snapshots s left join outcomes o on o.snapshot_id=s.id order by s.created_at desc limit ?',(limit,)).fetchall()
        return [{**json.loads(r['payload']),'reaction':json.loads(r['reaction']) if r['reaction'] else None} for r in rows]
    def outcome(self,identifier,payload):
        if self.remote:self.api('POST','analysis_outcomes',payload={'snapshot_id':identifier,'payload':payload,'updated_at':iso()},prefer='resolution=merge-duplicates,return=minimal')
        else:
            with self.db() as c:c.execute('insert into outcomes values(?,?) on conflict(snapshot_id) do update set payload=excluded.payload',(identifier,json.dumps(payload,allow_nan=False)))
    def journal_list(self,uid,archived=False):
        if self.remote:
            params={'user_id':f'eq.{uid}','select':'id,payload,created_at,deleted','order':'created_at.desc','limit':'500'}
            params['deleted']='eq.true' if archived else 'eq.false'
            rows=self.api('GET','journal_entries',params=params) or []
            return [{**r['payload'],'id':r['id'],'created_at':r['created_at'],'archived':bool(r['deleted'])} for r in rows]
        with self.db() as c:rows=c.execute('select id,created_at,payload,deleted from journal where user_id=? and deleted=? order by created_at desc limit 500',(uid,int(archived))).fetchall()
        return [{**json.loads(r['payload']),'id':r['id'],'created_at':r['created_at'],'archived':bool(r['deleted'])} for r in rows]
    def journal_save(self,uid,identifier,payload):
        created=iso()
        if self.remote:
            self.api('POST','journal_entries',payload={'id':identifier,'user_id':uid,'payload':payload,'created_at':created},prefer='return=minimal')
        else:
            with self.db() as c:c.execute('insert into journal values(?,?,?,?,0)',(identifier,uid,created,json.dumps(payload,allow_nan=False)))
        return {**payload,'id':identifier,'created_at':created}
    def journal_delete(self,uid,identifier,deleted=True):
        if self.remote:
            rows=self.api('PATCH','journal_entries',params={'id':f'eq.{identifier}','user_id':f'eq.{uid}'},payload={'deleted':deleted},prefer='return=representation')
            return bool(rows)
        with self.db() as c:return c.execute('update journal set deleted=? where id=? and user_id=?',(int(deleted),identifier,uid)).rowcount>0
    def preferences(self,uid,payload=None):
        defaults={'categories':['CPI','PPI','NFP','FOMC'],'minutes':[15,5],'release':True,'enabled':False}
        if self.remote:
            if payload is not None:self.api('POST','alert_preferences',payload={'user_id':uid,'payload':payload,'updated_at':iso()},prefer='resolution=merge-duplicates,return=minimal')
            rows=self.api('GET','alert_preferences',params={'user_id':f'eq.{uid}','select':'payload'}) or []
            return {**defaults,**(rows[0]['payload'] if rows else {})}
        with self.db() as c:
            if payload is not None:c.execute('insert into preferences values(?,?) on conflict(user_id) do update set payload=excluded.payload',(uid,json.dumps(payload)))
            row=c.execute('select payload from preferences where user_id=?',(uid,)).fetchone()
        return {**defaults,**(json.loads(row[0]) if row else {})}
