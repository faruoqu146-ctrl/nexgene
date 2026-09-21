const API=window.location.origin.replace(/\/$/,"");
let csrfToken=null;

async function api(path, opts={}){
  const headers=Object.assign({"Content-Type":"application/json"}, opts.headers||{});
  if(opts.method && opts.method!=="GET" && csrfToken) headers["X-CSRF-Token"]=csrfToken;
  const r=await fetch(API+path,{...opts,headers,credentials:"include"});
  const text=await r.text();
  let data=null; try{data=text?JSON.parse(text):null}catch(e){data={raw:text}}
  if(!r.ok){const err=new Error((data&&(data.detail||data.message))||r.statusText); err.status=r.status; err.data=data; throw err}
  return data;
}

function setCsrfFromCookie(){
  const m=document.cookie.match(/(?:^|; )nexgene_csrf=([^;]*)/);
  csrfToken=m?decodeURIComponent(m[1]):null;
}

async function refreshCsrf(){
  await api("/api/v1/auth/csrf");
  setCsrfFromCookie();
}

function show(id){
  document.querySelectorAll(".panel").forEach(p=>p.classList.add("hidden"));
  document.getElementById(id).classList.remove("hidden");
}

function toast(msg, kind="info"){
  const t=document.getElementById("toast");
  t.textContent=msg; t.className="toast "+kind; t.classList.remove("hidden");
  setTimeout(()=>t.classList.add("hidden"),3200);
}

async function register(){
  const email=document.getElementById("email").value.trim();
  const password=document.getElementById("password").value;
  try{
    const data=await api("/api/v1/auth/register",{method:"POST",body:JSON.stringify({email,password})});
    setCsrfFromCookie();
    if(data.dev_verification_token) toast("Dev verify token: "+data.dev_verification_token,"info");
    await boot();
  }catch(e){toast(e.message||"Register failed","error")}
}

async function login(){
  const email=document.getElementById("email").value.trim();
  const password=document.getElementById("password").value;
  try{
    await api("/api/v1/auth/login",{method:"POST",body:JSON.stringify({email,password})});
    setCsrfFromCookie();
    await boot();
  }catch(e){toast(e.message||"Login failed","error")}
}

async function logout(){
  try{
    await api("/api/v1/auth/logout",{method:"POST"});
    csrfToken=null;
    show("auth-panel");
    toast("Signed out");
  }catch(e){toast(e.message||"Logout failed","error")}
}

async function saveCheckin(period){
  const values={};
  document.querySelectorAll(`[data-period="${period}"] [data-kind]`).forEach(el=>{
    const kind=el.getAttribute("data-kind");
    const v=el.value;
    if(v===""||v==null) return;
    values[kind]=isNaN(Number(v))?v:Number(v);
  });
  try{
    await api("/api/v1/checkins/"+period,{method:"POST",body:JSON.stringify({values})});
    toast("Saved "+period+" check-in");
    await loadToday();
  }catch(e){toast(e.message||"Save failed","error")}
}

async function loadToday(){
  try{
    const data=await api("/api/v1/today");
    const box=document.getElementById("today-summary");
    box.innerHTML=Object.keys(data).length?Object.entries(data).map(([k,v])=>`<div><strong>${k}</strong>: ${v}</div>`).join(""):"<em>No readings in the last 24h</em>";
  }catch(e){}
}

async function loadPatterns(){
  try{
    const data=await api("/api/v1/patterns?days=30");
    const box=document.getElementById("patterns-box");
    const avg=data.averages||{};
    box.innerHTML=`<div>Observations: ${data.observation_count}</div>`+Object.entries(avg).map(([k,v])=>`<div><strong>${k}</strong> avg: ${v}</div>`).join("");
  }catch(e){}
}

async function loadInsights(){
  try{
    const data=await api("/api/v1/insights");
    const box=document.getElementById("insights-box");
    box.innerHTML=`<div class="status">${data.status}</div>`+(data.items||[]).map(i=>`<div class="insight">${i}</div>`).join("");
  }catch(e){}
}

async function boot(){
  try{
    const me=await api("/api/v1/auth/me");
    document.getElementById("user-email").textContent=me.email+(me.email_verified?" ✓":"");
    setCsrfFromCookie();
    show("app-panel");
    await Promise.all([loadToday(),loadPatterns(),loadInsights()]);
  }catch(e){
    show("auth-panel");
  }
}

document.addEventListener("DOMContentLoaded",()=>{
  document.getElementById("btn-register").onclick=register;
  document.getElementById("btn-login").onclick=login;
  document.getElementById("btn-logout").onclick=logout;
  document.getElementById("btn-morning").onclick=()=>saveCheckin("morning");
  document.getElementById("btn-evening").onclick=()=>saveCheckin("evening");
  boot();
});
