'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=v=>v?new Date(v).toLocaleString('en-GB',{timeZone:'Asia/Kuala_Lumpur'})+' MYT':'—';
const request=async(path,data)=>{const r=await fetch(path,{method:data?'POST':'GET',headers:{'Content-Type':'application/json','X-THYSMY-Request':'1'},...(data?{body:JSON.stringify(data)}:{}),signal:AbortSignal.timeout(25000)});const d=await r.json();if(!r.ok)throw Object.assign(new Error(d.detail||'Permintaan tidak berjaya.'),{status:r.status});return d;};
if($('pricing-price'))request('/api/me').then(d=>{$('pricing-price').innerHTML='RM'+esc(d.pro_price_rm)+'<small> / '+esc(d.pro_days)+' hari</small>';}).catch(()=>{$('pricing-price').textContent='Harga belum tersedia';});
if($('payment-title')){
 const order=new URLSearchParams(location.search).get('order_id')||'';
 let timer,attempts=0;
 const check=async()=>{clearTimeout(timer);try{
  if(!order)throw new Error('Pilih order daripada sejarah pembayaran dalam akaun.');
  const d=await request('/api/payment/status?order_id='+encodeURIComponent(order)),p=d.payment;
  const paid=p.status==='success';$('payment-title').textContent=paid?'Bayaran disahkan.':p.status==='failed'?'Bayaran belum berjaya.':'Menunggu pengesahan.';
  $('payment-message').textContent=paid?'Langganan Pro telah diproses. Simpan resit ini untuk rujukan.':'Jika wang sudah ditolak, semak semula dengan gateway. Jangan buat bayaran kedua dahulu.';
  const rows=[['Order',p.order_id],['Status',p.status],['Jumlah','RM'+(p.amount_sen/100).toFixed(2)],['Dicipta',date(p.created_at)],['Disahkan',date(p.paid_at)],['Pro tamat',date(d.subscription.expires_at)]];
  $('receipt-details').innerHTML=rows.map(([k,v])=>'<div class="detail-row"><span>'+esc(k)+'</span><span>'+esc(v)+'</span></div>').join('');
  $('print-receipt').hidden=!paid;$('recheck-payment').hidden=paid;
  if(!paid&&++attempts<12)timer=setTimeout(check,5000);
 }catch(err){$('payment-title').textContent=err.status===401?'Log masuk untuk semak resit.':'Status belum dapat disemak.';$('payment-message').textContent=err.message;if(err.status===401){$('receipt-details').innerHTML='<a class="button gold" href="/login">Log masuk</a>';}}};
 $('recheck-payment').onclick=async()=>{const b=$('recheck-payment');b.disabled=true;try{await request('/api/payment/recheck',{order_id:order});await check();}catch(err){$('payment-message').textContent=err.message;}finally{b.disabled=false;}};
 $('print-receipt').onclick=()=>window.print();check();
}
