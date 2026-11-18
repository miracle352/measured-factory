"""Shared browser shell: CSS, JS helper library (window.DX), render_page and the
auth / list / dossier screens. Screens render client-side from the JSON API."""
import html as _html
import json as _json

FIELD_ORDER = ["legal_name", "hq_city", "ceo", "founded_year", "headcount_range", "funding_total"]

CSS = r"""
:root{
  --bg:#f6f4ee;--surface:#fffefb;--ink:#1b2430;--muted:#556070;--line:#d9d5c8;
  --accent:#0b5560;--accent-ink:#ffffff;--accent-soft:#e1f0f1;
  --known:#17603a;--known-bg:#e3f2e8;
  --unknown:#4a525e;--unknown-bg:#ebebe8;
  --contested:#7d4300;--contested-bg:#fdecc8;
  --building:#1b4a9c;--building-bg:#e2ecfb;
  --failed:#9b1c1c;--failed-bg:#fbe3e3;
  --radius:10px;--shadow:0 1px 2px rgba(27,36,48,.08),0 4px 14px rgba(27,36,48,.05);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,"Helvetica Neue",Arial,sans-serif;overflow-x:hidden}
h1,h2,h3{line-height:1.2;margin:0}
h1{font-size:1.6rem;letter-spacing:-.01em}
h2{font-size:1.05rem}
a{color:var(--accent)}
a:hover{text-decoration-thickness:2px}
:focus-visible{outline:3px solid #f2a900;outline-offset:2px;border-radius:4px}
.topbar{background:var(--surface);border-bottom:1px solid var(--line)}
.topbar-in{max-width:1040px;margin:0 auto;padding:10px 16px 0}
.topbar-row{display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:0}
.brand{font-weight:700;font-size:1.1rem;color:var(--ink);text-decoration:none;white-space:nowrap}
.brand span{color:var(--accent)}
.userbox{display:flex;align-items:center;gap:8px;min-width:0}
.userbox [data-testid=current-user]{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600;font-size:.92rem}
.nav{display:flex;gap:4px;margin-top:6px}
.nav a{flex:0 0 auto;padding:9px 14px;text-decoration:none;color:var(--muted);font-weight:600;border-bottom:3px solid transparent;white-space:nowrap}
.nav a[aria-current=page]{color:var(--accent);border-bottom-color:var(--accent)}
main{max-width:1040px;margin:0 auto;padding:22px 16px 60px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:18px}
.stack>*+*{margin-top:16px}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.muted{color:var(--muted)}
.small{font-size:.88rem}
label{display:block;font-weight:600;font-size:.92rem;margin-bottom:4px}
input[type=text],input[type=email],input[type=password],input[type=search],input:not([type]){width:100%;font:inherit;padding:10px 12px;border:1.5px solid #8a93a0;border-radius:8px;background:#fff;color:var(--ink);min-height:44px}
.btn{font:inherit;font-weight:600;padding:10px 16px;border-radius:8px;border:1.5px solid var(--accent);background:var(--surface);color:var(--accent);cursor:pointer;min-height:44px;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}
.btn.primary{background:var(--accent);color:var(--accent-ink)}
.btn:disabled{opacity:.6;cursor:progress}
.btn.quiet{border-color:#8a93a0;color:var(--ink)}
.btn.small{min-height:36px;padding:6px 12px}
.badge{display:inline-flex;align-items:center;gap:5px;font-size:.8rem;font-weight:700;padding:2px 10px;border-radius:99px;white-space:nowrap}
.badge::before{content:"";width:8px;height:8px;border-radius:50%;background:currentColor}
.b-known,.b-ready{background:var(--known-bg);color:var(--known)}
.b-unknown{background:var(--unknown-bg);color:var(--unknown)}
.b-unknown::before{border-radius:2px;background:transparent;border:2px solid currentColor;width:9px;height:9px}
.b-contested{background:var(--contested-bg);color:var(--contested)}
.b-contested::before{border-radius:0;transform:rotate(45deg);width:8px;height:8px}
.b-building{background:var(--building-bg);color:var(--building)}
.b-building::before{animation:pulse 1.2s infinite}
.b-failed{background:var(--failed-bg);color:var(--failed)}
.b-failed::before{border-radius:0;clip-path:polygon(0 0,100% 0,50% 100%)}
@keyframes pulse{50%{opacity:.25}}
.msg{border-radius:8px;padding:10px 14px;border:1px solid;font-weight:500;overflow-wrap:anywhere}
.msg.error{background:var(--failed-bg);border-color:#e3a6a6;color:var(--failed)}
.msg.uncertain{background:var(--contested-bg);border-color:#e6c06b;color:var(--contested)}
.msg.success{background:var(--known-bg);border-color:#a5d3b5;color:var(--known)}
.msg.info{background:var(--building-bg);border-color:#a9c0ec;color:var(--building)}
.msg.loading{background:#fff;border:1px dashed #8a93a0;color:var(--muted)}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:spin .8s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
.empty{text-align:center;padding:34px 16px;color:var(--muted);border:1.5px dashed #8a93a0;border-radius:var(--radius);background:var(--surface)}
.list{list-style:none;margin:0;padding:0;display:grid;gap:10px}
a.item,.list .item{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;justify-content:space-between;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;text-decoration:none;color:var(--ink);box-shadow:var(--shadow)}
a.item:hover{border-color:var(--accent)}
.item .dom{font-weight:700;overflow-wrap:anywhere;min-width:0}
.item .sub{color:var(--muted);width:100%;font-size:.92rem;overflow-wrap:anywhere}
.head{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;justify-content:space-between}
.head h1{overflow-wrap:anywhere;min-width:0}
.facts{display:flex;flex-wrap:wrap;gap:6px 22px;margin:10px 0 0}
.facts div{min-width:0}
.facts dt{font-size:.78rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.facts dd{margin:0;font-weight:600}
.field{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}
.field .label{font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700}
.field-value{font-size:1.45rem;font-weight:700;margin:4px 0 8px;overflow-wrap:anywhere}
.field-none{font-size:1.05rem;color:var(--muted);margin:4px 0 8px}
.field.contested{border-left:6px solid #d79a1e}
.field.known{border-left:6px solid #3a9b62}
.field.unknown{border-left:6px solid #a4a9b1}
.cites{display:grid;gap:10px;min-width:0}
figure.cite{margin:0;background:#f4f2ea;border-radius:8px;padding:10px 12px;min-width:0}
figure.cite blockquote{margin:0 0 6px;font-style:italic;overflow-wrap:anywhere}
figure.cite blockquote::before{content:"\201C"}
figure.cite blockquote::after{content:"\201D"}
figure.cite figcaption{font-size:.84rem;color:var(--muted);overflow-wrap:anywhere}
.cand{border:1px solid var(--line);border-radius:8px;padding:12px;background:var(--surface);overflow-wrap:anywhere}
.cand.selected{border-color:var(--known);box-shadow:inset 4px 0 0 var(--known)}
@media(min-width:760px){
  .field{grid-template-columns:minmax(0,5fr) minmax(0,6fr);gap:22px}
  h1{font-size:1.9rem}
  .topbar-in{padding-top:12px}
}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
"""

JS_LIB = r"""
var DX=(function(){
  var FIELDS=%FIELDS%;
  var LABELS={legal_name:"Legal name",hq_city:"Headquarters city",ceo:"Chief executive",founded_year:"Year founded",headcount_range:"Headcount",funding_total:"Total funding"};
  var PROV={nimble:"Nimble",tavily:"Tavily",kernel:"Kernel browser",browserbase:"Browserbase"};
  var KIND={own:"Company site",filing:"Filing registry",news:"News report",aggregator:"Data aggregator"};
  var STATUS={known:"Known",unknown:"Unknown",contested:"Contested"};
  var STATE={building:"Building",ready:"Ready",failed:"Failed"};
  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
  function tok(){try{return localStorage.getItem("dossier.token")||"";}catch(e){return "";}}
  function userName(){try{return localStorage.getItem("dossier.user")||"";}catch(e){return "";}}
  function setSession(t,n){try{localStorage.setItem("dossier.token",t);localStorage.setItem("dossier.user",n);}catch(e){}}
  function clearSession(){try{localStorage.removeItem("dossier.token");localStorage.removeItem("dossier.user");}catch(e){}}
  function uuid(){if(window.crypto&&crypto.randomUUID)return crypto.randomUUID();return "k-"+Date.now().toString(36)+"-"+Math.random().toString(36).slice(2)+Math.random().toString(36).slice(2);}
  /* api(method,path,{body,headers,timeout}) -> Promise<{status,body,net}>. net=true when no usable response arrived. */
  function api(method,path,o){
    o=o||{};var h={"Accept":"application/json"};var t=tok();if(t)h["Authorization"]="Bearer "+t;
    var init={method:method,headers:h,cache:"no-store"};
    if(o.body!==undefined){h["Content-Type"]="application/json";init.body=JSON.stringify(o.body);}
    if(o.headers){for(var k in o.headers)h[k]=o.headers[k];}
    var ctl=window.AbortController?new AbortController():null;var timer=null;
    if(ctl){init.signal=ctl.signal;timer=setTimeout(function(){ctl.abort();},o.timeout||60000);}
    return fetch(path,init).then(function(r){
      return r.text().then(function(txt){
        if(timer)clearTimeout(timer);
        var b=null;try{b=txt?JSON.parse(txt):null;}catch(e){return {status:r.status,body:null,net:true};}
        if(r.status===401&&t&&path.indexOf("/auth/")!==0){clearSession();renderUser();}
        return {status:r.status,body:b,net:r.status>=500};
      },function(){if(timer)clearTimeout(timer);return {status:r.status,body:null,net:true};});
    },function(){if(timer)clearTimeout(timer);return {status:0,body:null,net:true};});
  }
  function cap(s){s=String(s);return s.charAt(0).toUpperCase()+s.slice(1);}
  function errMsg(r,fallback){
    var c=r&&r.body&&r.body.error&&r.body.error.code;var m=r&&r.body&&r.body.error&&r.body.error.message;
    if(r&&r.status===401)return "Please sign in first.";
    if(c==="email_taken")return "That email is already registered. Try signing in instead.";
    if(c==="not_found")return "We could not find that.";
    if(m)return cap(m)+(/[.!?]$/.test(m)?"":".");
    return fallback||"Something went wrong.";
  }
  function fmtTime(iso){
    if(!iso)return "";var d=new Date(iso);if(isNaN(d.getTime()))return String(iso);
    function p(n){return (n<10?"0":"")+n;}
    return d.getUTCFullYear()+"-"+p(d.getUTCMonth()+1)+"-"+p(d.getUTCDate())+" "+p(d.getUTCHours())+":"+p(d.getUTCMinutes())+" UTC";
  }
  function fmtMoney(n){return typeof n==="number"?"$"+n.toLocaleString("en-US"):String(n);}
  function fmtValue(field,v){
    if(v===null||v===undefined)return "";
    if(field==="funding_total"&&typeof v==="number")return fmtMoney(v);
    if(field==="headcount_range"&&typeof v==="string")return v.replace("-","–")+" people";
    return String(v);
  }
  function dataValue(v){return v===null||v===undefined?"":String(v);}
  function host(u){try{var x=new URL(u);return x.host+(x.pathname&&x.pathname!=="/"?x.pathname:"");}catch(e){return String(u);}}
  function badge(kind,text){return '<span class="badge b-'+esc(kind)+'">'+esc(text)+'</span>';}
  /* latest-read-wins: r.read(fetcher,apply) -- apply only runs for the newest read started. */
  function reader(){var seq=0;return {read:function(fetcher,apply){var my=++seq;return Promise.resolve().then(fetcher).then(function(res){if(my===seq)return apply(res);},function(){if(my===seq)return apply({status:0,body:null,net:true});});},cancel:function(){seq++;}};}
  function gateHtml(){return '<div class="card stack" data-testid="auth-required"><h2>Sign in to continue</h2><p class="muted">Dossiers are available to signed-in researchers.</p><div class="row"><a class="btn primary" href="/login">Sign in</a><a class="btn" href="/signup">Create account</a></div></div>';}
  /* gate(el): returns false (and shows a sign-in prompt in el) when not signed in. */
  function gate(el){if(tok())return true;el.innerHTML=gateHtml();return false;}
  function renderUser(){
    var box=document.getElementById("userbox");if(!box)return;
    if(tok()){
      box.innerHTML='<span data-testid="current-user" title="Signed in">'+esc(userName()||"Signed in")+'</span><button type="button" class="btn small quiet" data-testid="logout-button">Sign out</button>';
      box.querySelector("button").onclick=function(){clearSession();location.href="/login";};
    }else{
      box.innerHTML='<a class="btn small quiet" href="/login">Sign in</a><a class="btn small primary" href="/signup">Sign up</a>';
    }
  }
  renderUser();
  return {FIELDS:FIELDS,LABELS:LABELS,PROV:PROV,KIND:KIND,STATUS:STATUS,STATE:STATE,esc:esc,tok:tok,userName:userName,setSession:setSession,clearSession:clearSession,uuid:uuid,api:api,errMsg:errMsg,fmtTime:fmtTime,fmtMoney:fmtMoney,fmtValue:fmtValue,dataValue:dataValue,host:host,badge:badge,reader:reader,gate:gate,renderUser:renderUser,
    fieldLabel:function(f){return LABELS[f]||f;},providerLabel:function(p){return PROV[p]||p||"Unknown source";},kindLabel:function(k){return k?(KIND[k]||k):"Imported (unclassified)";},statusLabel:function(s){return STATUS[s]||s;},stateLabel:function(s){return STATE[s]||s;}};
})();
""".replace("%FIELDS%", _json.dumps(FIELD_ORDER))


def esc(s):
    return _html.escape(str(s), quote=True)


def render_page(title, main_html, script="", active=""):
    """Shared shell. active: 'list' | 'contested' | '' (nav highlight)."""
    def cur(k):
        return ' aria-current="page"' if active == k else ""
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s · Dossier</title>
<style>%s</style></head>
<body>
<header class="topbar"><div class="topbar-in">
<div class="topbar-row"><a class="brand" href="/">Dossier<span>.</span></a><div class="userbox" id="userbox"></div></div>
<nav class="nav" aria-label="Main"><a href="/"%s>Dossiers</a><a href="/contested"%s>Contested</a></nav>
</div></header>
<main id="app">%s</main>
<script>%s</script>
<script>%s</script>
</body></html>""" % (esc(title), CSS, cur("list"), cur("contested"), main_html, JS_LIB,
                     script.replace("</script", "<\\/script"))


# ------------------------------------------------------------------ auth screens

def _auth_main(kind):
    signup = kind == "signup"
    p = "signup" if signup else "login"
    name_field = ('<div><label for="signup-display-name">Display name</label>'
                  '<input id="signup-display-name" data-testid="signup-display-name" '
                  'autocomplete="name" maxlength="100"></div>') if signup else ""
    return """<div class="card stack" style="max-width:440px;margin:0 auto">
<h1>%s</h1>
<p class="muted">%s</p>
<form id="authform" class="stack" novalidate>
%s
<div><label for="%s-email">Email</label><input id="%s-email" data-testid="%s-email" type="email" autocomplete="email"></div>
<div><label for="%s-password">Password</label><input id="%s-password" data-testid="%s-password" type="password" autocomplete="%s"></div>
<div id="auth-slot" aria-live="polite"></div>
<button class="btn primary" type="submit" data-testid="%s-submit" style="width:100%%">%s</button>
</form>
<p class="small muted">%s</p>
</div>""" % (
        "Create your account" if signup else "Sign in",
        "Start researching companies, with every source shown." if signup else "Welcome back.",
        name_field, p, p, p, p, p, p, "new-password" if signup else "current-password", p,
        "Create account" if signup else "Sign in",
        'Already registered? <a href="/login">Sign in</a>' if signup
        else 'New here? <a href="/signup">Create an account</a>')


def _auth_script(kind):
    return r"""
(function(){
var signup=%s;var form=document.getElementById("authform");var slot=document.getElementById("auth-slot");var busy=false;
function val(id){return document.getElementById(id).value;}
form.addEventListener("submit",function(ev){
  ev.preventDefault();if(busy)return;
  var btn=form.querySelector("button[type=submit]");
  var body=signup?{email:val("signup-email"),password:val("signup-password"),display_name:val("signup-display-name")}:{email:val("login-email"),password:val("login-password")};
  slot.innerHTML='<div class="msg loading"><span class="spinner"></span>Please wait…</div>';busy=true;btn.disabled=true;
  DX.api("POST",signup?"/auth/signup":"/auth/login",{body:body}).then(function(r){
    busy=false;btn.disabled=false;
    if(r.status>=200&&r.status<300&&r.body&&r.body.token){
      DX.setSession(r.body.token,r.body.display_name||body.display_name||"");
      slot.innerHTML='<div class="msg success">Signed in. Taking you to your dossiers…</div>';
      location.href="/";return;
    }
    var m;
    if(r.net)m="We could not reach the service. Check your connection and try again.";
    else if(r.status===401)m="That email and password do not match.";
    else m=DX.errMsg(r,"Could not complete that request.");
    slot.innerHTML='<div class="msg error" role="alert" data-testid="auth-error">'+DX.esc(m)+'</div>';
  });
});
})();
""" % ("true" if kind == "signup" else "false")


def signup_page():
    return render_page("Sign up", _auth_main("signup"), _auth_script("signup"))


def login_page():
    return render_page("Sign in", _auth_main("login"), _auth_script("login"))


# ------------------------------------------------------------------ routes' pages

def _external(mod, name, *args):
    try:
        m = __import__(mod)
        return getattr(m, name)(*args)
    except Exception:
        return None


def evidence_page(domain):
    r = _external("ui_evidence", "evidence_main", domain)
    if r is None:
        r = ('<div class="empty">The evidence view is not available yet.</div>', "")
    main, script = r
    return render_page("Evidence · " + domain, main, script)


def contested_page():
    r = _external("ui_evidence", "contested_main")
    if r is None:
        r = ('<div class="empty">The contested view is not available yet.</div>', "")
    main, script = r
    return render_page("Contested fields", main, script, active="contested")


def list_page():
    import ui_pages
    return ui_pages.list_page()


def dossier_page(domain):
    import ui_pages
    return ui_pages.dossier_page(domain)
