
const $ = id => document.getElementById(id);
let targetEpoch = null;

function setPct(id, bar, value){
  $(id).textContent = `${value ?? 0}%`;
  $(bar).style.width = `${Math.max(0, Math.min(100, Number(value || 0)))}%`;
}
function fmtNum(v){
  if(v === null || v === undefined) return "—";
  const n = Number(v);
  if(!Number.isFinite(n)) return String(v);
  if(Math.abs(n) >= 1000) return n.toLocaleString();
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}
function fmtCountdown(seconds){
  seconds = Math.max(0, Math.floor(seconds));
  const d = Math.floor(seconds/86400); seconds%=86400;
  const h = Math.floor(seconds/3600); seconds%=3600;
  const m = Math.floor(seconds/60); const s = seconds%60;
  if(d>0) return `${d}d ${h}h ${m}m`;
  if(h>0) return `${h}h ${m}m ${s}s`;
  return `${m}m ${s}s`;
}
function tickCountdown(){
  if(targetEpoch === null) return;
  const sec = Math.max(0, Math.floor(targetEpoch - Date.now()/1000));
  $("countdown").textContent = fmtCountdown(sec);
}
setInterval(tickCountdown, 1000);

function render(data){
  // Price and global status should still render even if the calendar has no event.
  const p0 = data.price || {};
  $("xauPrice").textContent = fmtNum(p0.mid);
  $("marketState").textContent = p0.marketState || p0.status || "—";
  $("priceTime").textContent = p0.timestamp ? new Date(p0.timestamp).toLocaleString() : "—";

  const g0 = data.global || {};
  $("gdeltStatus").textContent = g0.status || "—";
  $("fed").textContent = g0.fed || "—";
  $("risk").textContent = g0.risk || "—";
  $("globalUsd").textContent = g0.usd_score ?? "—";
  $("globalXau").textContent = g0.xau_score ?? "—";
  $("hits").textContent = g0.hits ?? "—";
  $("calendarStatus").textContent = data.upcoming_status || data.calendar_status || "—";

  if(!data.ok){
    $("bias").textContent = "NO NEWS DATA";
    $("newsLabel").textContent = data.status || "NO UPCOMING EVENT";
    $("countdown").textContent = "—";
    $("confidence").textContent = "—%";
    $("finalScore").textContent = "—";
    setPct("spike","spikeBar",0);
    setPct("oneWay","oneBar",0);
    setPct("twoWay","twoBar",0);
    return;
  }

  $("bias").textContent = data.bias;
  $("confidence").textContent = `${data.confidence}%`;
  $("finalScore").textContent = data.final_xau_score;
  setPct("spike","spikeBar",data.spike_potential);
  setPct("oneWay","oneBar",data.one_way);
  setPct("twoWay","twoBar",data.two_way);

  $("newsLabel").textContent = data.label;
  const eventDate = new Date(data.event_time);
  targetEpoch = eventDate.getTime()/1000;
  tickCountdown();

  const eventList = $("newsEvents");
  eventList.innerHTML = "";
  (data.events || []).forEach(e => {
    const row = document.createElement("div");
    row.className = "event";
    row.innerHTML = `
      <div><span>Event</span><b>${e.name || "—"}</b></div>
      <div><span>Forecast</span><b>${fmtNum(e.forecast)}</b></div>
      <div><span>Previous</span><b>${fmtNum(e.revisedPrevious ?? e.previous)}</b></div>
      <div><span>Time</span><b>${new Date(e.time).toLocaleString()}</b></div>`;
    eventList.appendChild(row);
  });

  $("labor").textContent = data.macro.labor;
  $("inflation").textContent = data.macro.inflation;
  $("growth").textContent = data.macro.growth;
  $("rates").textContent = data.macro.rates;
  $("macroTotal").textContent = data.macro.total;

  const recent = $("recentData");
  recent.innerHTML = "";
  (data.macro.used || []).slice(0,7).forEach(r => {
    const el = document.createElement("div");
    el.className = "recentRow";
    el.innerHTML = `<b>${r.name}</b><span>${new Date(r.time).toLocaleString()} · A ${fmtNum(r.actual)} · F ${fmtNum(r.forecast)} · USD score ${r.score}</span>`;
    recent.appendChild(el);
  });

  const g = data.global || {};
  $("gdeltStatus").textContent = g.status || "—";
  $("fed").textContent = g.fed || "—";
  $("risk").textContent = g.risk || "—";
  $("globalUsd").textContent = g.usd_score ?? "—";
  $("globalXau").textContent = g.xau_score ?? "—";
  $("hits").textContent = g.hits ?? "—";
  $("calendarStatus").textContent = data.calendar_status || "—";

  const p = data.price || {};
  $("xauPrice").textContent = fmtNum(p.mid);
  $("marketState").textContent = p.marketState || p.status || "—";
  $("priceTime").textContent = p.timestamp ? new Date(p.timestamp).toLocaleString() : "—";

  const components = $("components");
  components.innerHTML = "";
  (data.pre_components || []).forEach(c => {
    const el = document.createElement("div");
    el.className = "component";
    const side = c.usd_score > 0 ? "USD BULLISH" : c.usd_score < 0 ? "USD BEARISH" : "NEUTRAL";
    el.innerHTML = `<b>${c.name}</b><span>Forecast ${fmtNum(c.forecast)} · Previous ${fmtNum(c.previous)}<br>${side} · ${c.usd_score}</span>`;
    components.appendChild(el);
  });

  const heads = $("headlines");
  heads.innerHTML = "";
  const articles = g.articles || [];
  if(!articles.length){
    heads.innerHTML = `<div class="error">No cached headlines yet.</div>`;
  }else{
    articles.forEach(a => {
      const el = document.createElement("a");
      el.className = "headline";
      el.href = a.url || "#";
      el.target = "_blank";
      el.rel = "noopener noreferrer";
      el.innerHTML = `<b>${a.title || "Untitled"}</b><small>${a.domain || ""} ${a.seendate || ""}</small>`;
      heads.appendChild(el);
    });
  }
}
async function load(){
  try{
    const r = await fetch("/api/dashboard");
    render(await r.json());
  }catch(e){
    $("bias").textContent = "OFFLINE";
  }
}
$("refresh").addEventListener("click", async () => {
  const btn = $("refresh");
  btn.disabled = true;
  btn.textContent = "Refreshing…";
  try{
    const r = await fetch("/api/refresh",{method:"POST"});
    render(await r.json());
  }finally{
    btn.disabled = false;
    btn.textContent = "Refresh";
  }
});
load();
setInterval(load, 60000);
