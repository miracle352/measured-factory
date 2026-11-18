"""Evidence screen (/dossiers/{domain}/evidence) and contested-fields screen (/contested).

Both render client-side from the JSON API with the shared DX helpers of ui.py:

    evidence_main(domain) -> (main_html, script)
    contested_main()      -> (main_html, script)
"""
import html as _html
from urllib.parse import quote

STYLE = """<style>
.pagehead{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;justify-content:space-between}
.pagehead h1{min-width:0;overflow-wrap:anywhere}
.crumbs{font-size:.92rem;margin:0 0 6px}
.efield{display:grid;gap:12px}
.efield h2{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}
.cands{display:grid;gap:10px;min-width:0}
.cand .cv{font-size:1.2rem;font-weight:700;overflow-wrap:anywhere}
.cand .tags{display:flex;flex-wrap:wrap;gap:6px 8px;margin:6px 0 8px;align-items:center}
.tag{display:inline-flex;align-items:center;font-size:.8rem;font-weight:600;padding:2px 10px;border-radius:99px;background:#ebebe8;color:#333b47;border:1px solid #cfcbbd}
.tag.sel{background:var(--known-bg);color:var(--known);border-color:#a5d3b5}
.cand blockquote{margin:0 0 8px;font-style:italic;overflow-wrap:anywhere}
.cand blockquote::before{content:"\\201C"}
.cand blockquote::after{content:"\\201D"}
.cand .src{font-size:.86rem;color:var(--muted);overflow-wrap:anywhere}
.cand .src a{overflow-wrap:anywhere}
.ci{flex-direction:column;flex-wrap:nowrap;align-items:stretch;justify-content:flex-start;text-align:left;gap:6px}
.ci .vals{display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-start;align-self:flex-start}
.fkey{font-size:.8rem;background:#ebebe8;border-radius:4px;padding:0 6px;color:#333b47}
.ci .small{align-self:flex-start}
.ci .top{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;width:100%;justify-content:space-between}
</style>"""

COMMON_JS = r"""
function when(iso,none){return iso?DX.fmtTime(iso):none;}
function fmtV(f,v){return DX.fmtValue(f,v);}
function loadingHtml(t){return '<div class="msg loading" data-testid="screen-loading"><span class="spinner"></span>'+DX.esc(t)+'</div>';}
function errorHtml(t,id){return '<div class="msg error" role="alert" data-testid="screen-error">'+DX.esc(t)+' <button type="button" class="btn small quiet" id="'+id+'">Try again</button></div>';}
"""


def evidence_main(domain):
    d = _html.escape(domain, quote=True)
    du = _html.escape(quote(domain, safe=""), quote=True)
    main = STYLE + """<div class="stack" id="ev-root" data-domain="%s">
<div><p class="crumbs"><a href="/dossiers/%s">&larr; Back to the dossier</a></p>
<div class="pagehead"><h1>Evidence for <span data-testid="evidence-domain">%s</span></h1>
<button type="button" class="btn" id="ev-reload">Reload</button></div>
<p class="muted">Every value the sources support, ranked. The best-ranked source is selected: the most authoritative
(company site or filing, then news, then data aggregators), then the most recently published.</p></div>
<div id="ev-view" class="stack" aria-live="polite"></div>
</div>""" % (d, du, d)
    script = COMMON_JS + r"""
(function(){
var root=document.getElementById("ev-root"),D=root.getAttribute("data-domain"),view=document.getElementById("ev-view");
var app=document.getElementById("app");
if(!DX.tok()){app.innerHTML="";DX.gate(app);return;}
var rd=DX.reader(),shown=false;
function cand(f,c,i){
  var sel=c.selected===true;
  var h='<article class="cand'+(sel?' selected':'')+'" data-testid="candidate-'+f+'-'+(i+1)+'" data-value="'+DX.esc(DX.dataValue(c.value))+'" data-provider="'+DX.esc(c.provider||"")+'" data-kind="'+DX.esc(c.kind||"")+'" data-url="'+DX.esc(c.url||"")+'" data-published-at="'+DX.esc(c.published_at||"")+'" data-selected="'+(sel?"true":"false")+'">';
  h+='<div class="cv">'+DX.esc(fmtV(f,c.value))+'</div><div class="tags">';
  h+=sel?'<span class="tag sel">&#10003; Selected value</span>':'<span class="tag">Not selected</span>';
  h+='<span class="tag">'+DX.esc(DX.kindLabel(c.kind))+'</span><span class="tag">'+DX.esc(DX.providerLabel(c.provider))+'</span></div>';
  h+='<blockquote>'+DX.esc(c.excerpt)+'</blockquote>';
  h+='<div class="src"><a href="'+DX.esc(c.url)+'" target="_blank" rel="noopener noreferrer">'+DX.esc(DX.host(c.url))+'</a><br>'+(c.published_at?'Published '+DX.esc(DX.fmtTime(c.published_at)):'Publication date not stated')+(c.retrieved_at?' · Retrieved '+DX.esc(DX.fmtTime(c.retrieved_at)):'')+'</div>';
  return h+'</article>';
}
function render(b){
  var h='<p class="small muted">'+DX.badge(b.state,DX.stateLabel(b.state))+(b.researched_at?' &nbsp;Researched '+DX.esc(DX.fmtTime(b.researched_at)):' &nbsp;Not researched yet')+'</p>';
  DX.FIELDS.forEach(function(f){
    var fo=(b.fields||{})[f]||{status:"unknown",candidates:[]};
    var cs=fo.candidates||[];
    var st=fo.status||"unknown";
    h+='<section class="card efield"><h2>'+DX.esc(DX.fieldLabel(f))+' '+(st==="contested"?DX.badge("contested","Sources disagree"):DX.badge(st==="known"?"known":"unknown",DX.statusLabel(st)))+'</h2>';
    h+='<div class="cands" data-testid="evidence-'+f+'">';
    if(!cs.length)h+='<div class="empty" data-testid="evidence-empty-'+f+'">No source supports a value for this field yet.</div>';
    cs.forEach(function(c,i){h+=cand(f,c,i);});
    h+='</div></section>';
  });
  view.innerHTML=h;shown=true;
}
function load(){
  if(!shown)view.innerHTML=loadingHtml("Loading evidence…");
  rd.read(function(){return DX.api("GET","/dossiers/"+encodeURIComponent(D));},function(r){
    if(r.status===200&&r.body&&r.body.fields){render(r.body);return;}
    if(r.status===401){DX.gate(view);return;}
    if(r.status===404){shown=false;view.innerHTML='<div class="empty" data-testid="evidence-not-found"><strong>No dossier exists for this domain.</strong><br>Research it from the <a href="/">dossier list</a> first.</div>';return;}
    if(shown)return;
    view.innerHTML=errorHtml("We could not load the evidence.","ev-retry");
    document.getElementById("ev-retry").onclick=load;
  });
}
document.getElementById("ev-reload").onclick=load;
load();
})();
"""
    return main, script


def contested_main():
    main = STYLE + """<div class="stack" id="ct-root">
<div class="pagehead"><h1>Contested fields</h1><button type="button" class="btn" id="ct-reload">Reload</button></div>
<p class="muted">Fields where trustworthy sources report different values. Each shows the selected value and the others.</p>
<div id="ct-view" class="stack" aria-live="polite"></div>
</div>"""
    script = COMMON_JS + r"""
(function(){
var view=document.getElementById("ct-view"),app=document.getElementById("app");
if(!DX.tok()){app.innerHTML="";DX.gate(app);return;}
var rd=DX.reader(),shown=false;
function listAll(){
  var all=[];
  function page(off){
    return DX.api("GET","/dossiers?limit=200&offset="+off).then(function(r){
      if(r.status!==200||!r.body||!r.body.dossiers)return {fail:r};
      all=all.concat(r.body.dossiers);
      if(r.body.has_more&&r.body.dossiers.length)return page(off+r.body.dossiers.length);
      return {ok:all};
    });
  }
  return page(0);
}
function pool(items,n,fn){
  var out=new Array(items.length),i=0;
  function worker(){if(i>=items.length)return Promise.resolve();var k=i++;return fn(items[k]).then(function(v){out[k]=v;return worker();});}
  var ws=[];for(var j=0;j<Math.min(n,items.length);j++)ws.push(worker());
  return Promise.all(ws).then(function(){return out;});
}
function fetchAll(){
  return listAll().then(function(l){
    if(l.fail)return l.fail;
    var doms=l.ok.map(function(d){return d.domain;}).sort();
    return pool(doms,6,function(d){return DX.api("GET","/dossiers/"+encodeURIComponent(d));}).then(function(rs){
      for(var i=0;i<rs.length;i++){if(rs[i].status===401)return rs[i];}
      var items=[];
      rs.forEach(function(r,i){
        if(r.status!==200||!r.body||!r.body.fields)return;
        DX.FIELDS.forEach(function(f){var fo=r.body.fields[f];if(fo&&fo.status==="contested")items.push({domain:doms[i],field:f,fo:fo});});
      });
      return {status:200,body:{items:items}};
    });
  });
}
function distinct(f,fo){
  var seen={},out=[];
  [fo.value].concat((fo.candidates||[]).map(function(c){return c.value;})).forEach(function(v){var k=JSON.stringify(v);if(!seen[k]){seen[k]=1;out.push(v);}});
  return out;
}
function render(items){
  if(!items.length){view.innerHTML='<div class="empty" data-testid="empty-contested"><strong>No contested fields.</strong><br>Every field with a value has sources that agree.</div>';shown=true;return;}
  var h='<div class="list" data-testid="contested-list">';
  items.forEach(function(it){
    var vals=distinct(it.field,it.fo);
    h+='<a class="item ci" data-testid="contested-item-'+DX.esc(it.domain)+'-'+it.field+'" data-value="'+DX.esc(DX.dataValue(it.fo.value))+'" href="/dossiers/'+encodeURIComponent(it.domain)+'/evidence">';
    h+='<span class="top"><span class="dom">'+DX.esc(it.domain)+'</span>'+DX.badge("contested","Sources disagree")+'</span>';
    h+='<span class="sub">'+DX.esc(DX.fieldLabel(it.field))+' <code class="fkey">'+it.field+'</code> &middot; selected <strong>'+DX.esc(fmtV(it.field,it.fo.value))+'</strong></span>';
    h+='<span class="vals">';
    vals.forEach(function(v){h+='<span class="tag'+(JSON.stringify(v)===JSON.stringify(it.fo.value)?' sel':'')+'">'+DX.esc(fmtV(it.field,v))+'</span>';});
    h+='</span><span class="small">Compare the sources &rarr;</span></a>';
  });
  view.innerHTML=h+'</div>';shown=true;
}
function load(){
  if(!shown)view.innerHTML=loadingHtml("Looking for disagreements…");
  rd.read(fetchAll,function(r){
    if(r.status===200&&r.body&&r.body.items){render(r.body.items);return;}
    if(r.status===401){DX.gate(view);return;}
    if(shown)return;
    view.innerHTML=errorHtml("We could not load the dossiers.","ct-retry");
    document.getElementById("ct-retry").onclick=load;
  });
}
document.getElementById("ct-reload").onclick=load;
load();
})();
"""
    return main, script
