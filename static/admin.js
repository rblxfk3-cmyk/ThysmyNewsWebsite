'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=v=>v?new Date(v).toLocaleString('en-GB',{timeZone:'Asia/Kuala_Lumpur'}):'—';
async function api(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:{'Content-Type':'application/json','X-THYSMY-Request':'1'},...(data?{body:JSON.stringify(data)}:{}),signal:AbortSignal.timeout(25000)});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Permintaan tidak berjaya.');return d;}
async function load(){
 $('admin-message').textContent='Memuatkan…';$('admin-refresh').disabled=true;
 try{const [d,s]=await Promise.all([api('/api/admin/overview'),api('/api/admin/system')]),u=d.users||[],p=d.payments||[];
 $('adminStats').innerHTML=[['AKAUN TERKINI',u.length],['PRO AKTIF',u.filter(x=>x.plan==='pro'&&x.status==='active'&&(!x.expires_at||new Date(x.expires_at)>new Date())).length],['BAYARAN TERKINI',p.length],['VERSI',s.version]].map(([k,v])=>'<div class="panel"><small>'+esc(k)+'</small><strong>'+esc(v)+'</strong></div>').join('');
 $('system-status').innerHTML=[['Penyimpanan',s.storage.ready?s.storage.backend+(s.storage.durable?' · persistent':' · sementara'):'Perlu kemas kini Supabase V4'],['AI',s.ai_ready?'Disambungkan':'Panduan aturan · sambungan AI belum aktif'],['Pembayaran',s.payment_configured?s.payment_mode:'Belum dikonfigurasi'],['Sesi',s.session_configured?'Dikonfigurasi':'SESSION_SECRET belum ditetapkan'],['Recorder terakhir',date(s.recorder_last_seen)],['Recorder',s.recorder_error||'Tiada ralat dilaporkan']].map(([k,v])=>'<div class="detail-row"><span>'+esc(k)+'</span><span>'+esc(v)+'</span></div>').join('');
 $('users').innerHTML=u.map(x=>'<tr><td>'+esc(x.email)+'</td><td>'+esc(x.role)+'</td><td>'+esc(x.plan)+'</td><td>'+date(x.expires_at)+'</td><td><button class="button small" data-user="'+esc(x.id)+'" data-plan="pro">Pro 30 hari</button> <button class="button small outline" data-user="'+esc(x.id)+'" data-plan="free">Free</button></td></tr>').join('');
 $('payments').innerHTML=p.map(x=>'<tr><td>'+esc(x.order_id)+'</td><td>'+esc(x.email||'—')+'</td><td>RM'+((x.amount_sen||0)/100).toFixed(2)+'</td><td>'+esc(x.status)+'</td><td>'+date(x.created_at)+'</td></tr>').join('');
 $('admin-message').textContent=d.demo?'MOD DEMO · Ini akaun dan transaksi ujian.':'';
 }catch(err){$('admin-message').textContent=err.message;}finally{$('admin-refresh').disabled=false;}
}
$('users').onclick=async ev=>{const b=ev.target.closest('[data-user]');if(!b)return;if(!confirm('Tukar langganan akaun ini kepada '+b.dataset.plan.toUpperCase()+'? Pro manual menetapkan tamat 30 hari dari sekarang.'))return;b.disabled=true;try{await api('/api/admin/subscription',{user_id:b.dataset.user,plan:b.dataset.plan,days:30});await load();}catch(err){$('admin-message').textContent=err.message;b.disabled=false;}};
$('admin-refresh').onclick=load;load();
