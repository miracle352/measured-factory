"""Dossier list ('/') and dossier ('/dossiers/{domain}') screens, on the ui.py shell."""
from urllib.parse import quote

from ui import esc, render_page

LIST_HTML = """<div class="stack" id="list-root">
<section class="card stack"><h1>Research a company</h1>
<p class="muted">Enter a company website domain. Every value found is kept with its sources.</p>
<form id="rform" class="stack" novalidate>
<div><label for="research-domain">Company domain</label>
<input id="research-domain" data-testid="research-domain" placeholder="acme-robotics.com" autocapitalize="none" autocorrect="off" spellcheck="false" autocomplete="off"></div>
<div id="rslot" aria-live="polite"></div>
<button class="btn primary" type="submit" data-testid="research-submit">Research</button>
</form></section>
<section class="stack"><h2>Your dossiers</h2>
<div><label for="dossier-search">Search by domain or company name</label>
<input type="search" id="dossier-search" data-testid="dossier-search" autocomplete="off"></div>
<div id="lslot" aria-live="polite"></div></section></div>"""

LIST_JS = r"""
(function(){
var root=document.getElementById("list-root");
if(!DX.gate(root))return;
var form=document.getElementById("rform"),input=document.getElementById("research-domain"),rslot=document.getElementById("rslot");
var search=document.getElementById("dossier-search"),lslot=document.getElementById("lslot");
var pending=null,busy=false,rd=DX.reader(),stimer=null,loaded=false;
function note(kind,testid,html,role){rslot.innerHTML='<div class="msg '+kind+'" data-testid="'+testid+'"'+(role?' role="'+role+'"':'')+'>'+html+'</div>';}
form.addEventListener("submit",function(ev){
  ev.preventDefault();if(busy)return;
  var text=input.value;
  if(!pending||pending.text!==text)pending={text:text,key:DX.uuid()};
  var btn=form.querySelector("button[type=submit]");
  busy=true;btn.disabled=true;
  rslot.innerHTML='<div class="msg loading" data-testid="research-loading"><span class="spinner"></span>Starting research…</div>';
  DX.api("POST","/dossiers",{body:{domain:text},headers:{"Idempotency-Key":pending.key}}).then(function(r){
    busy=false;btn.disabled=false;
    if((r.status===200||r.status===202)&&r.body&&r.body.domain){
      pending=null;note("success","research-success","Research started. Opening the dossier…");
      location.href="/dossiers/"+encodeURIComponent(r.body.domain);return;
    }
    if(r.net){
      note("uncertain","research-uncertain","We could not confirm whether the research request went through. Press Research again to retry — it is safe and will not start a second build.","status");return;
    }
    pending=null;
    var m=r.status===422?"That does not look like a valid company domain. Try something like acme-robotics.com.":r.status===401?"Please sign in to research a company.":DX.errMsg(r,"The request was refused.");
    note("error","research-error",DX.esc(m),"alert");
  });
});
function loadAll(q){
  var all=[];
  function page(off){
    return DX.api("GET","/dossiers?limit=200&offset="+off+(q?"&q="+encodeURIComponent(q):"")).then(function(r){
      if(r.status!==200||!r.body)return r;
      var ds=r.body.dossiers||[];all=all.concat(ds);
      if(r.body.has_more&&ds.length)return page(off+200);
      return {status:200,body:{dossiers:all}};
    });
  }
  return page(0);
}
function render(r,q){
  if(r.status===401){DX.gate(root);return;}
  if(r.status!==200||!r.body){
    lslot.innerHTML='<div class="msg error" role="alert" data-testid="list-error">We could not load the dossiers. <button type="button" class="btn small quiet" id="lretry">Try again</button></div>';
    document.getElementById("lretry").onclick=function(){refreshList();};return;
  }
  loaded=true;
  var items=r.body.dossiers;
  if(!items.length){
    lslot.innerHTML='<div class="empty" data-testid="empty-dossiers">'+(q?"No dossier matches “"+DX.esc(q)+"”.":"No dossiers yet. Research a company above to create the first one.")+'</div>';return;
  }
  var h='<div class="list" data-testid="dossier-list">';
  items.forEach(function(d){
    h+='<a class="item" data-testid="dossier-item-'+DX.esc(d.domain)+'" data-state="'+DX.esc(d.state)+'" href="/dossiers/'+encodeURIComponent(d.domain)+'">'
      +'<span class="dom">'+DX.esc(d.domain)+'</span>'+DX.badge(d.state,d.state==="building"?"Building":d.state==="failed"?"Failed":"Ready")
      +'<span class="sub">'+(d.legal_name?DX.esc(d.legal_name):'<span class="muted">Company name not known yet</span>')+'</span></a>';
  });
  lslot.innerHTML=h+'</div>';
}
function refreshList(){
  var q=search.value.trim();
  if(!loaded)lslot.innerHTML='<div class="msg loading" data-testid="list-loading"><span class="spinner"></span>Loading dossiers…</div>';
  rd.read(function(){return loadAll(q);},function(r){render(r,q);});
}
search.addEventListener("input",function(){clearTimeout(stimer);stimer=setTimeout(refreshList,150);});
refreshList();
})();
"""

DOSSIER_HTML = """<div class="stack" id="dossier-root" data-domain="{D}">
<section class="card">
<div class="head"><h1 data-testid="dossier-domain">{D}</h1><span id="dstate"></span></div>
<dl class="facts" id="dfacts"></dl>
<div class="row" style="margin-top:14px">
<button type="button" class="btn primary" data-testid="dossier-refresh" id="brefresh">Refresh research</button>
<button type="button" class="btn" data-testid="dossier-reload" id="breload">Reload</button>
<a class="btn quiet" data-testid="dossier-evidence-link" href="/dossiers/{DU}/evidence">View all evidence</a>
</div>
<div id="aslot" aria-live="polite" style="margin-top:12px"></div>
</section>
<div id="dview" class="stack"><div class="msg loading" data-testid="dossier-loading"><span class="spinner"></span>Loading dossier…</div></div>
</div>"""

DOSSIER_JS = r"""
(function(){
var root=document.getElementById("dossier-root");var D=root.getAttribute("data-domain");
var view=document.getElementById("dview"),aslot=document.getElementById("aslot"),dstate=document.getElementById("dstate"),dfacts=document.getElementById("dfacts");
var bref=document.getElementById("brefresh"),brel=document.getElementById("breload");
if(!DX.tok()){document.getElementById("app").innerHTML="";DX.gate(document.getElementById("app"));return;}
var path="/dossiers/"+encodeURIComponent(D);
var rd=DX.reader(),poll=null,inflight=0,shown=false;
function cmp(v){return JSON.stringify(v);}
var MON=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtDate(iso){var d=new Date(iso);if(isNaN(d.getTime()))return String(iso);return d.getUTCDate()+" "+MON[d.getUTCMonth()]+" "+d.getUTCFullYear();}
function renderField(f,fo){
  var st=fo.status||"unknown",has=fo.value!==null&&fo.value!==undefined;
  var h='<section class="card field '+DX.esc(st)+'" data-testid="field-'+f+'" data-status="'+DX.esc(st)+'"><div class="field-main"><div class="label">'+DX.esc(DX.fieldLabel(f))+'</div>';
  if(has)h+='<div class="field-value" data-testid="field-value-'+f+'" data-value="'+DX.esc(DX.dataValue(fo.value))+'">'+DX.esc(DX.fmtValue(f,fo.value))+'</div>';
  else h+='<div class="field-none">No value found yet</div>';
  if(has&&fo.true_from)h+='<p class="small muted" style="margin:0 0 6px">In effect since '+DX.esc(DX.fmtDay(fo.true_from))+'</p>';
  h+='<div class="row">';
  if(st==="contested")h+='<span class="badge b-contested" data-testid="field-contested-'+f+'">Sources disagree</span>';
  else h+=DX.badge(st==="known"?"known":"unknown",st==="known"?"Known":"Unknown");
  h+='</div>';
  if(st==="contested"){
    var others=[],seen={};seen[cmp(fo.value)]=1;
    (fo.candidates||[]).forEach(function(c){var k=cmp(c.value);if(!seen[k]){seen[k]=1;others.push(DX.fmtValue(f,c.value));}});
    h+='<p class="small muted" style="margin:8px 0 0">Selected from the most authoritative, most recent source. Also reported: <strong>'+DX.esc(others.join(", "))+'</strong>. <a href="/dossiers/'+encodeURIComponent(D)+'/evidence">Compare sources</a></p>';
  }
  h+='</div><div class="cites" data-testid="field-citations-'+f+'">';
  var cs=fo.citations||[];
  if(!cs.length)h+='<p class="muted small" style="margin:0">No sources for this field yet.</p>';
  cs.forEach(function(c,i){
    var cd=null;(fo.candidates||[]).forEach(function(x){if(!cd&&x.url===c.url&&x.provider===c.provider)cd=x;});
    if(!cd)(fo.candidates||[]).forEach(function(x){if(!cd&&x.url===c.url)cd=x;});
    var meta=cd?' · '+DX.esc(DX.kindLabel(cd.kind))+(cd.published_at?' · published '+DX.esc(fmtDate(cd.published_at)):' · publication date unknown'):'';
    h+='<figure class="cite" data-testid="citation-'+f+'-'+(i+1)+'" data-provider="'+DX.esc(c.provider)+'"><blockquote>'+DX.esc(c.excerpt)+'</blockquote><figcaption><a href="'+DX.esc(c.url)+'" target="_blank" rel="noopener noreferrer">'+DX.esc(DX.host(c.url))+'</a> · via '+DX.esc(DX.providerLabel(c.provider))+meta+'</figcaption></figure>';
  });
  return h+'</div></section>';
}
function renderExecutives(fo){
  fo=fo||{status:"unknown",value:null,citations:[],candidates:[]};
  var st=fo.status||"unknown",members=Array.isArray(fo.value)?fo.value:[];
  var h='<section class="card field execs '+DX.esc(st)+'"><div class="field-main"><div class="label">Executives</div>';
  if(members.length){
    h+='<ul class="exec-list">';
    members.forEach(function(m){
      var sel=null;(fo.candidates||[]).forEach(function(c){if(!sel&&c.title===m.title&&c.selected)sel=c;});
      h+='<li><span class="exec-title">'+DX.esc(DX.titleLabel(m.title))+'</span><span class="exec-name">'+DX.esc(m.name)+'</span>'+(sel&&sel.true_from?'<span class="small muted">In effect since '+DX.esc(DX.fmtDay(sel.true_from))+'</span>':'')+'</li>';
    });
    h+='</ul>';
  }else h+='<div class="field-none">No executives found yet</div>';
  h+='<div class="row">'+(st==="contested"?'<span class="badge b-contested">Sources disagree</span>':DX.badge(st==="known"?"known":"unknown",st==="known"?"Known":"Unknown"))+'</div>';
  if(st==="contested")h+='<p class="small muted" style="margin:8px 0 0">Sources name different people for at least one role. <a href="/dossiers/'+encodeURIComponent(D)+'/evidence">Compare sources</a></p>';
  h+='</div><div class="cites">';
  var cs=fo.citations||[];
  if(!cs.length)h+='<p class="muted small" style="margin:0">No sources for the executives yet.</p>';
  cs.forEach(function(c){
    h+='<figure class="cite"><blockquote>'+DX.esc(c.excerpt)+'</blockquote><figcaption><a href="'+DX.esc(c.url)+'" target="_blank" rel="noopener noreferrer">'+DX.esc(DX.host(c.url))+'</a> · via '+DX.esc(DX.providerLabel(c.provider))+'</figcaption></figure>';
  });
  return h+'</div></section>';
}
function renderInvestors(fo){
  fo=fo||{status:"unknown",value:null,citations:[],candidates:[]};
  var st=fo.status||"unknown",names=Array.isArray(fo.value)?fo.value:[];
  var h='<section class="card field investors '+DX.esc(st)+'"><div class="field-main"><div class="label">Investors</div>';
  if(names.length){
    h+='<ul class="exec-list">';
    names.forEach(function(n){h+='<li><span class="exec-name">'+DX.esc(n)+'</span></li>';});
    h+='</ul>';
    if(fo.true_from)h+='<p class="small muted" style="margin:0 0 6px">In effect since '+DX.esc(DX.fmtDay(fo.true_from))+'</p>';
  }else h+='<div class="field-none">No investors found yet</div>';
  h+='<div class="row">'+DX.badge(st==="known"?"known":"unknown",st==="known"?"Known":"Unknown");
  var no=(fo.origins||[]).length;
  if(st==="known")h+=' <span class="small muted">'+(fo.corroborated?'Confirmed by independent sources':'Not yet confirmed by two independent sources')+(no?' ('+no+(no===1?' source':' sources')+')':'')+'</span>';
  h+='</div></div><div class="cites">';
  var cs=fo.citations||[];
  if(!cs.length)h+='<p class="muted small" style="margin:0">No sources for the investors yet.</p>';
  cs.forEach(function(c){
    h+='<figure class="cite"><blockquote>'+DX.esc(c.excerpt)+'</blockquote><figcaption><a href="'+DX.esc(c.url)+'" target="_blank" rel="noopener noreferrer">'+DX.esc(DX.host(c.url))+'</a> · via '+DX.esc(DX.providerLabel(c.provider))+'</figcaption></figure>';
  });
  return h+'</div></section>';
}
function renderDossier(b){
  dstate.innerHTML='<span class="badge b-'+DX.esc(b.state)+'" data-testid="dossier-state">'+DX.esc(b.state)+'</span>';
  var u=b.spent_units;
  var f='<div><dt>Spent</dt><dd data-testid="dossier-spent" data-units="'+DX.esc(u)+'">'+DX.esc(u)+(u===1?" unit":" units")+'</dd></div>';
  if(b.researched_at)f+='<div><dt>Researched</dt><dd><time data-testid="dossier-researched-at" datetime="'+DX.esc(b.researched_at)+'">'+DX.esc(DX.fmtTime(b.researched_at))+'</time></dd></div>';
  else f+='<div><dt>Researched</dt><dd class="muted">Not yet</dd></div>';
  dfacts.innerHTML=f;
  var h='';
  if(b.state==="building")h+='<div class="msg info" data-testid="dossier-building"><span class="spinner"></span>Research is running. This page updates by itself when it finishes.</div>';
  if(b.state==="failed")h+='<div class="msg error" data-testid="dossier-failed">The last research run failed'+(b.researched_at?'; showing the most recent successful results.':'. Try refreshing.')+'</div>';
  DX.FIELDS.forEach(function(f){h+=renderField(f,(b.fields||{})[f]||{status:"unknown",value:null,citations:[],candidates:[]});});
  h+=renderExecutives((b.fields||{}).executives);
  h+=renderInvestors((b.fields||{}).investors);
  view.innerHTML=h;shown=true;
}
function setPoll(on){
  if(on&&!poll)poll=setInterval(function(){if(inflight<4)load();},1000);
  if(!on&&poll){clearInterval(poll);poll=null;}
}
function clearReadError(){var e=aslot.querySelector("[data-testid=dossier-load-error]");if(e)aslot.innerHTML="";}
function load(){
  inflight++;
  rd.read(function(){return DX.api("GET",path);},function(r){
    var b=r.body;
    if(r.status===200&&b&&b.fields){clearReadError();renderDossier(b);setPoll(b.state==="building");return;}
    if(r.status===401){setPoll(false);DX.gate(view);return;}
    if(r.status===404){setPoll(false);dstate.innerHTML="";dfacts.innerHTML="";view.innerHTML='<div class="empty" data-testid="dossier-not-found"><strong>No dossier for this domain yet.</strong><br>Research it from the <a href="/">dossier list</a>.</div>';shown=false;return;}
    if(!shown)view.innerHTML='<div class="msg error" role="alert" data-testid="dossier-load-error">We could not load this dossier. Press Reload to try again.</div>';
    else aslot.innerHTML='<div class="msg error" role="alert" data-testid="dossier-load-error">We could not update the page data; showing what was loaded before.</div>';
  }).then(function(){inflight--;},function(){inflight--;});
}
brel.addEventListener("click",function(){load();});
var rkey=null,rbusy=false;
bref.addEventListener("click",function(){
  if(rbusy)return;
  if(!rkey)rkey=DX.uuid();
  rbusy=true;bref.disabled=true;
  aslot.innerHTML='<div class="msg loading" data-testid="refresh-loading"><span class="spinner"></span>Requesting a refresh…</div>';
  DX.api("POST",path+"/refresh",{headers:{"Idempotency-Key":rkey}}).then(function(r){
    rbusy=false;bref.disabled=false;
    if(r.status===200||r.status===202){
      rkey=null;aslot.innerHTML='<div class="msg success" data-testid="refresh-success">Refresh started. The results below update when it finishes.</div>';load();return;
    }
    if(r.net){aslot.innerHTML='<div class="msg uncertain" role="status" data-testid="refresh-uncertain">We could not confirm whether the refresh started. Press Refresh again to retry — it is safe and will not start a second build.</div>';return;}
    rkey=null;
    aslot.innerHTML='<div class="msg error" role="alert" data-testid="refresh-error">'+DX.esc(r.status===404?"There is no dossier for this domain to refresh yet.":DX.errMsg(r,"The refresh was refused."))+'</div>';
  });
});
load();
})();
"""


STYLE = """<style>
.exec-list{list-style:none;margin:6px 0 10px;padding:0;display:grid;gap:10px}
.exec-list li{display:grid;gap:2px;min-width:0}
.exec-title{font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700}
.exec-name{font-size:1.3rem;font-weight:700;overflow-wrap:anywhere}
.field.execs.known{border-left:6px solid #3a9b62}
.field.execs.contested{border-left:6px solid #d79a1e}
.field.execs.unknown{border-left:6px solid #a4a9b1}
</style>"""


def list_page():
    return render_page("Dossiers", LIST_HTML, LIST_JS, active="list")


def dossier_page(domain):
    main = DOSSIER_HTML.replace("{D}", esc(domain)).replace("{DU}", esc(quote(domain, safe="")))
    return render_page(domain, STYLE + main, DOSSIER_JS)
