from __future__ import annotations

import hashlib
import os
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from engine_v2 import (
    calculate_engine,
    fetch_calendar,
    fetch_upcoming,
    fetch_price,
    fetch_gdelt,
    now_utc,
    parse_dt,
)

load_dotenv()
BASE = Path(__file__).resolve().parent
app = FastAPI(title="THYSMY Fundamental Web V3", version="3.1")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

APP_BASE_URL=os.getenv("APP_BASE_URL","http://127.0.0.1:8000").rstrip("/")
SESSION_SECRET=os.getenv("SESSION_SECRET","CHANGE-ME-BEFORE-PRODUCTION")
DEMO_MODE=os.getenv("DEMO_MODE","true").lower() in ("1","true","yes","on")
SUPABASE_URL=os.getenv("SUPABASE_URL","").rstrip("/")
SUPABASE_PUBLISHABLE_KEY=os.getenv("SUPABASE_PUBLISHABLE_KEY","")
SUPABASE_SECRET_KEY=os.getenv("SUPABASE_SECRET_KEY","")
ADMIN_EMAIL=os.getenv("ADMIN_EMAIL","").strip().lower()
TOYYIBPAY_MODE=os.getenv("TOYYIBPAY_MODE","sandbox").lower()
TOYYIBPAY_SECRET_KEY=os.getenv("TOYYIBPAY_SECRET_KEY","")
TOYYIBPAY_CATEGORY_CODE=os.getenv("TOYYIBPAY_CATEGORY_CODE","")
PRO_PRICE_RM=int(os.getenv("PRO_PRICE_RM","29"))
PRO_DAYS=int(os.getenv("PRO_DAYS","30"))

app.add_middleware(SessionMiddleware,secret_key=SESSION_SECRET,session_cookie="thysmy_session",max_age=1209600,same_site="lax",https_only=APP_BASE_URL.startswith("https://"))

DEMO_USERS={
 "demo@thysmy.local":{"id":"demo-user","email":"demo@thysmy.local","role":"user","plan":"pro","status":"active","expires_at":"2099-12-31T23:59:59+00:00"},
 "admin@thysmy.local":{"id":"demo-admin","email":"admin@thysmy.local","role":"admin","plan":"pro","status":"active","expires_at":"2099-12-31T23:59:59+00:00"},
}

def sb_ready(): return bool(SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY and SUPABASE_SECRET_KEY)
def pay_ready(): return bool(TOYYIBPAY_SECRET_KEY and TOYYIBPAY_CATEGORY_CODE and APP_BASE_URL.startswith("http"))

def sb_headers(service=False,token=None):
    # Supabase new API keys go in `apikey`; only user JWT goes in Authorization.
    key=SUPABASE_SECRET_KEY if service else SUPABASE_PUBLISHABLE_KEY
    h={"apikey":key,"Content-Type":"application/json"}
    if token: h["Authorization"]="Bearer "+token
    return h

def sb_rest(method,table,params=None,payload=None,prefer=None):
    h=sb_headers(True)
    if prefer: h["Prefer"]=prefer
    r=requests.request(method,f"{SUPABASE_URL}/rest/v1/{table}",headers=h,params=params,json=payload,timeout=15)
    if r.status_code>=400: raise RuntimeError(f"Supabase {table}: {r.status_code} {r.text}")
    if not r.text: return None
    try: return r.json()
    except Exception: return r.text

def ensure_profile(uid,email):
    role="admin" if ADMIN_EMAIL and email.lower()==ADMIN_EMAIL else "user"
    sb_rest("POST","profiles",payload={"id":uid,"email":email.lower(),"role":role},prefer="resolution=merge-duplicates,return=minimal")
    sb_rest("POST","subscriptions",payload={"user_id":uid,"plan":"free","status":"active"},prefer="resolution=ignore-duplicates,return=minimal")

def get_profile(uid):
    rows=sb_rest("GET","profiles",params={"id":f"eq.{uid}","select":"*"}) or []
    return rows[0] if rows else {"id":uid,"role":"user"}

def get_subscription(uid):
    rows=sb_rest("GET","subscriptions",params={"user_id":f"eq.{uid}","select":"*"}) or []
    if not rows: return {"user_id":uid,"plan":"free","status":"active","expires_at":None}
    s=rows[0]; exp=parse_dt(s.get("expires_at"))
    if s.get("plan")=="pro" and exp and exp<now_utc(): return {**s,"plan":"free","status":"expired"}
    return s

def identity(request:Request):
    if DEMO_MODE:
        return DEMO_USERS.get(request.session.get("demo_email",""))
    uid=request.session.get("uid"); email=request.session.get("email")
    if not uid or not email or not sb_ready(): return None
    p=get_profile(uid); s=get_subscription(uid)
    return {"id":uid,"email":email,"role":p.get("role","user"),"plan":s.get("plan","free"),"status":s.get("status","active"),"expires_at":s.get("expires_at")}

def require_user(request):
    u=identity(request)
    if not u: raise HTTPException(401,"Login required")
    return u

def require_admin(request):
    u=require_user(request)
    if u.get("role")!="admin": raise HTTPException(403,"Admin only")
    return u

def is_pro(u): return bool(u and u.get("plan")=="pro" and u.get("status")=="active")
def toyyib_base(): return "https://dev.toyyibpay.com" if TOYYIBPAY_MODE=="sandbox" else "https://toyyibpay.com"

@app.get("/",response_class=HTMLResponse)
def landing(): return (BASE/"templates"/"landing.html").read_text(encoding="utf-8")
@app.get("/login",response_class=HTMLResponse)
def login_page(): return (BASE/"templates"/"login.html").read_text(encoding="utf-8")
@app.get("/register",response_class=HTMLResponse)
def register_page(): return (BASE/"templates"/"register.html").read_text(encoding="utf-8")
@app.get("/pricing",response_class=HTMLResponse)
def pricing_page(): return (BASE/"templates"/"pricing.html").read_text(encoding="utf-8")
@app.get("/dashboard",response_class=HTMLResponse)
def dashboard_page(request:Request):
    if not identity(request): return RedirectResponse("/login",302)
    return (BASE/"templates"/"dashboard.html").read_text(encoding="utf-8")
@app.get("/admin",response_class=HTMLResponse)
def admin_page(request:Request):
    u=identity(request)
    if not u or u.get("role")!="admin": return RedirectResponse("/dashboard",302)
    return (BASE/"templates"/"admin.html").read_text(encoding="utf-8")

@app.post("/api/auth/register")
async def register(request:Request):
    d=await request.json(); email=(d.get("email") or "").strip().lower(); password=d.get("password") or ""
    if len(password)<8: raise HTTPException(400,"Password minimum 8 characters")
    if DEMO_MODE: raise HTTPException(400,"Demo mode: use demo login")
    if not sb_ready(): raise HTTPException(503,"Supabase not configured")
    r=requests.post(f"{SUPABASE_URL}/auth/v1/signup",headers=sb_headers(),json={"email":email,"password":password},timeout=15)
    if not r.ok: raise HTTPException(400,(r.json().get("msg") or r.json().get("message") or "Registration failed"))
    body=r.json(); user=body.get("user") or body
    if user.get("id"): ensure_profile(user["id"],email)
    return {"ok":True,"message":"Account created. Check email if confirmation is enabled."}

@app.post("/api/auth/login")
async def login(request:Request):
    d=await request.json(); email=(d.get("email") or "").strip().lower(); password=d.get("password") or ""
    if DEMO_MODE:
        if email in DEMO_USERS and password=="demo12345":
            request.session["demo_email"]=email
            return {"ok":True,"redirect":"/admin" if DEMO_USERS[email]["role"]=="admin" else "/dashboard"}
        raise HTTPException(401,"Demo: demo@thysmy.local / demo12345")
    if not sb_ready(): raise HTTPException(503,"Supabase not configured")
    r=requests.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password",headers=sb_headers(),json={"email":email,"password":password},timeout=15)
    if not r.ok: raise HTTPException(401,(r.json().get("msg") or r.json().get("message") or "Login failed"))
    body=r.json(); user=body.get("user") or {}
    if not user.get("id"): raise HTTPException(401,"Invalid login response")
    ensure_profile(user["id"],email); request.session["uid"]=user["id"]; request.session["email"]=email
    p=get_profile(user["id"])
    return {"ok":True,"redirect":"/admin" if p.get("role")=="admin" else "/dashboard"}

@app.post("/api/auth/logout")
def logout(request:Request): request.session.clear(); return {"ok":True}
@app.get("/api/me")
def me(request:Request): return {"logged_in":bool(identity(request)),"user":identity(request),"demo_mode":DEMO_MODE,"supabase_ready":sb_ready(),"payment_ready":pay_ready(),"pro_price_rm":PRO_PRICE_RM,"pro_days":PRO_DAYS}

@app.get("/api/dashboard")
def dashboard_api(request:Request):
    u=require_user(request); d=calculate_engine()
    if not is_pro(u) and d.get("ok"):
        return {"ok":True,"tier":"free","locked":True,"label":d.get("label"),"event_time":d.get("event_time"),"seconds_to_news":d.get("seconds_to_news"),"events":d.get("events"),"price":d.get("price"),"calendar_status":d.get("calendar_status")}
    d["tier"]="pro"; d["locked"]=False; return d

@app.post("/api/refresh")
def refresh(request:Request):
    require_user(request); fetch_calendar(force=True); fetch_upcoming(force=True); fetch_price(force=True); fetch_gdelt(force=True); return dashboard_api(request)

@app.post("/api/payment/create")
def create_payment(request:Request):
    u=require_user(request)
    if DEMO_MODE: return {"ok":False,"demo":True,"message":"ToyyibPay disabled in demo mode"}
    if not (sb_ready() and pay_ready()): raise HTTPException(503,"Payment system not configured")
    order="THY"+now_utc().strftime("%y%m%d%H%M%S")+secrets.token_hex(3).upper(); amount=PRO_PRICE_RM*100
    sb_rest("POST","payments",payload={"user_id":u["id"],"email":u["email"],"order_id":order,"amount_sen":amount,"status":"created"},prefer="return=minimal")
    payload={"userSecretKey":TOYYIBPAY_SECRET_KEY,"categoryCode":TOYYIBPAY_CATEGORY_CODE,"billName":"THYSMY Pro 30 Days","billDescription":"THYSMY Fundamental Engine Pro Subscription","billPriceSetting":"1","billPayorInfo":"0","billAmount":str(amount),"billReturnUrl":f"{APP_BASE_URL}/payment/return","billCallbackUrl":f"{APP_BASE_URL}/api/payment/callback","billExternalReferenceNo":order,"billTo":u["email"],"billEmail":u["email"],"billPhone":"","billSplitPayment":"0","billSplitPaymentArgs":"","billPaymentChannel":"0","billContentEmail":"Thank you for subscribing to THYSMY Pro","billChargeToCustomer":"1","billExpiryDays":"1","enableDuitNowQR":"1","chargeDuitNowQR":"0"}
    r=requests.post(f"{toyyib_base()}/index.php/api/createBill",data=payload,timeout=20)
    if not r.ok: raise HTTPException(502,"ToyyibPay createBill failed")
    try: code=r.json()[0]["BillCode"]
    except Exception: raise HTTPException(502,"Invalid ToyyibPay response")
    sb_rest("PATCH","payments",params={"order_id":f"eq.{order}"},payload={"bill_code":code,"status":"pending"},prefer="return=minimal")
    return {"ok":True,"checkout_url":f"{toyyib_base()}/{code}","order_id":order}

@app.post("/api/payment/callback")
async def callback(request:Request):
    if not sb_ready(): raise HTTPException(503,"Supabase not configured")
    f=await request.form(); status=str(f.get("status","")); order=str(f.get("order_id","")); ref=str(f.get("refno","")); received=str(f.get("hash","")).lower(); bill=str(f.get("billcode",""))
    expected=hashlib.md5((TOYYIBPAY_SECRET_KEY+status+order+ref+"ok").encode()).hexdigest().lower()
    if not TOYYIBPAY_SECRET_KEY or not secrets.compare_digest(received,expected): raise HTTPException(400,"Invalid callback hash")
    rows=sb_rest("GET","payments",params={"order_id":f"eq.{order}","select":"user_id,status"}) or []
    if not rows: raise HTTPException(404,"Unknown order")
    uid=rows[0]["user_id"]; already=rows[0].get("status")=="success"; raw={k:str(v) for k,v in f.items()}
    if status=="1" and not already:
        sub=get_subscription(uid); exp=parse_dt(sub.get("expires_at")); base=exp if exp and exp>now_utc() else now_utc(); newexp=base+timedelta(days=PRO_DAYS)
        sb_rest("POST","subscriptions",payload={"user_id":uid,"plan":"pro","status":"active","expires_at":newexp.isoformat(),"updated_at":now_utc().isoformat()},prefer="resolution=merge-duplicates,return=minimal")
    mapped="success" if status=="1" else "pending" if status=="2" else "failed"
    sb_rest("PATCH","payments",params={"order_id":f"eq.{order}"},payload={"status":mapped,"refno":ref,"bill_code":bill,"raw":raw,"paid_at":now_utc().isoformat() if status=="1" else None},prefer="return=minimal")
    return {"ok":True,"status":mapped}

@app.get("/payment/return",response_class=HTMLResponse)
def payment_return(status_id:str="",billcode:str="",order_id:str=""):
    status={"1":"Payment submitted successfully","2":"Payment pending","3":"Payment failed"}.get(status_id,"Payment status received")
    h=(BASE/"templates"/"payment_return.html").read_text(encoding="utf-8")
    return h.replace("{{STATUS}}",status).replace("{{ORDER_ID}}",order_id).replace("{{BILLCODE}}",billcode)

@app.get("/api/admin/overview")
def admin_overview(request:Request):
    require_admin(request)
    if DEMO_MODE:
        return {"demo":True,"users":[{"id":"demo-user","email":"demo@thysmy.local","role":"user","plan":"pro","status":"active","expires_at":"2099-12-31"},{"id":"demo-free","email":"free@thysmy.local","role":"user","plan":"free","status":"active","expires_at":None},{"id":"demo-admin","email":"admin@thysmy.local","role":"admin","plan":"pro","status":"active","expires_at":"2099-12-31"}],"payments":[{"order_id":"DEMO001","email":"demo@thysmy.local","amount_sen":2900,"status":"success","created_at":now_utc().isoformat()}]}
    profiles=sb_rest("GET","profiles",params={"select":"id,email,role,created_at","order":"created_at.desc","limit":"200"}) or []
    subs=sb_rest("GET","subscriptions",params={"select":"user_id,plan,status,expires_at","limit":"200"}) or []; sm={s["user_id"]:s for s in subs}
    users=[{**p,"plan":sm.get(p["id"],{}).get("plan","free"),"status":sm.get(p["id"],{}).get("status","active"),"expires_at":sm.get(p["id"],{}).get("expires_at")} for p in profiles]
    pays=sb_rest("GET","payments",params={"select":"order_id,email,amount_sen,status,bill_code,created_at,paid_at","order":"created_at.desc","limit":"100"}) or []
    return {"users":users,"payments":pays}

@app.post("/api/admin/subscription")
async def admin_subscription(request:Request):
    require_admin(request)
    if DEMO_MODE: return {"ok":True,"demo":True}
    d=await request.json(); uid=d.get("user_id"); plan=d.get("plan","free"); days=int(d.get("days",PRO_DAYS))
    if not uid: raise HTTPException(400,"user_id required")
    exp=(now_utc()+timedelta(days=max(1,days))).isoformat() if plan=="pro" else None
    sb_rest("POST","subscriptions",payload={"user_id":uid,"plan":plan,"status":"active","expires_at":exp,"updated_at":now_utc().isoformat()},prefer="resolution=merge-duplicates,return=minimal")
    return {"ok":True}

@app.get("/api/diagnostics")
def diagnostics():
    return {"version":"3.0","demo_mode":DEMO_MODE,"supabase_ready":sb_ready(),"payment_ready":pay_ready(),"toyyibpay_mode":TOYYIBPAY_MODE,"app_base_url":APP_BASE_URL,"calendar_status":fetch_calendar().get("status"),"upcoming_status":fetch_upcoming().get("status"),"price_status":fetch_price().get("status"),"gdelt_status":fetch_gdelt().get("status")}
@app.get("/health")
def health(): return {"ok":True,"app":"THYSMY Fundamental Web V3","demo_mode":DEMO_MODE}
