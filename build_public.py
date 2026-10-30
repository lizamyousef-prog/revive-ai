"""build_public.py - records every demo run and builds public.html (no server needed).   python3.15 build_public.py"""
import base64, json
import dash_api
from diagnose import diagnose
from llm_diagnose import make_llm_diagnoser

SEED = 7
data = {"cases": dash_api.catalog(), "runs": {}}
for key in dash_api.CASES:
    for agent in ("revive", "naive"):
        # only the ambiguous case replays the saved real Gemini answer; the rest use the rules diagnoser
        dash_api.make_llm_diagnoser = make_llm_diagnoser if key == "d2b" else (lambda: diagnose)
        data["runs"][f"{key}|{agent}"] = dash_api.run_case(key, agent, SEED)
cal = json.load(open("calibration.json"))
b64 = lambda p: "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()
data["results"] = json.load(open("results.json"))
data["split"] = json.load(open("results_split.json"))
data["cal"] = {"target": cal["target"], "curve": cal["curve"]}

h = open("dashboard.html").read()
style = h[h.index("<style>"):h.index("</style>")]
markup = h[h.index("<header>"):h.index("<script>")]
script = h[h.index("<script>") + 8:h.index("</script>")]

extra = """
  :root{color-scheme:dark}
  html,body{background:#0f1b21}
  body{padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
  header,main{padding-left:0;padding-right:0}
  main>section{min-width:0}
  .log{height:260px}
  .wrap{overflow-x:auto}
  .res{padding:8px 0 40px;display:grid;gap:16px;grid-template-columns:minmax(0,1fr)}
  .res>.card{min-width:0}
  .res h2.big{font-size:16px;color:var(--text);text-transform:none;letter-spacing:0;margin:0 0 6px}
  .res p{color:var(--mute);margin:4px 0 10px;max-width:75ch}
  .chart{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:8px 0;display:flex;flex-wrap:wrap;gap:18px 28px}
  .chart>svg{flex:1 1 340px;min-width:0;max-width:640px}
  .chart svg{display:block;width:100%;height:auto;overflow:visible}
  .chart .ct{font:600 14px Inter,system-ui,sans-serif;fill:var(--text)}
  .chart .ax{font:12px Inter,system-ui,sans-serif;fill:var(--mute)}
  .chart .vl{font:700 12px Inter,system-ui,sans-serif;fill:var(--text)}
  .chart .grid{stroke:#24404c;stroke-width:1}
  .chart .base{stroke:#5d7b88;stroke-width:1.5}
  .chart .bar{transform-box:fill-box;transform-origin:50% 100%;transform:scaleY(0);transition:transform .9s cubic-bezier(.2,.8,.2,1)}
  .chart .fade{opacity:0;transition:opacity .45s ease}
  .chart .ln{stroke-dasharray:1;stroke-dashoffset:1;transition:stroke-dashoffset 1.6s ease}
  .chart.in .bar{transform:scaleY(1)} .chart.in .fade{opacity:1} .chart.in .ln{stroke-dashoffset:0}
  .legend{flex-basis:100%;display:flex;gap:16px;flex-wrap:wrap;margin:4px 0 0;font-size:13px;color:var(--mute)}
  .legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
  @media (prefers-reduced-motion: reduce){.chart .bar,.chart .fade,.chart .ln{transition:none}}
  .faq details{border-top:1px solid var(--line);padding:12px 2px}
  .faq details:last-child{border-bottom:1px solid var(--line)}
  .faq summary{cursor:pointer;list-style:none;font-weight:600;color:var(--text);display:flex;justify-content:space-between;gap:16px;align-items:center}
  .faq summary::-webkit-details-marker{display:none}
  .faq summary::after{content:"+";color:var(--teal);font-size:20px;line-height:1;transition:transform .25s ease}
  .faq details[open] summary::after{transform:rotate(45deg)}
  .faq details p{margin:10px 0 2px;color:var(--mute);max-width:80ch;line-height:1.55;animation:faqIn .3s ease}
  @keyframes faqIn{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
  @media (prefers-reduced-motion: reduce){.faq details p{animation:none}.faq summary::after{transition:none}}
  .gbtn{position:fixed;right:20px;bottom:20px;z-index:50;display:flex;align-items:center;gap:10px;padding:13px 18px;border-radius:999px;border:0;background:var(--teal);color:#06222b;font:700 15px Inter,system-ui,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.45);cursor:pointer;transition:transform .2s ease}
  .gbtn:hover{transform:translateY(-2px)} .gbtn .dot{width:9px;height:9px;border-radius:50%;background:#06222b;animation:gpulse 1.8s infinite}
  @keyframes gpulse{0%,100%{opacity:1}50%{opacity:.25}}
  .gbox{position:fixed;right:20px;bottom:84px;z-index:51;width:380px;max-width:calc(100vw - 32px);height:560px;max-height:calc(100vh - 110px);display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line);border-radius:18px;box-shadow:0 24px 60px rgba(0,0,0,.55);overflow:hidden;opacity:0;transform:translateY(16px) scale(.98);pointer-events:none;transition:opacity .25s ease,transform .25s ease}
  .gbox.open{opacity:1;transform:none;pointer-events:auto}
  .ghead{display:flex;align-items:center;gap:12px;padding:14px 16px;border-bottom:1px solid var(--line);background:var(--panel2)}
  .ghead b{display:block;color:var(--text);font-size:15px} .ghead small{color:var(--mute);font-size:12px}
  .ghead .x{margin-left:auto;background:none;border:0;color:var(--mute);font-size:22px;cursor:pointer;line-height:1}
  .gav{width:34px;height:34px;border-radius:10px;background:#0f1b21;display:flex;align-items:center;justify-content:center;flex:none}
  .gmsgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;scroll-behavior:smooth}
  .gm{max-width:86%;padding:10px 13px;border-radius:14px;font-size:14px;line-height:1.5;animation:gin .25s ease}
  .gm.bot{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-bottom-left-radius:4px;align-self:flex-start}
  .gm.me{background:var(--teal);color:#06222b;font-weight:600;border-bottom-right-radius:4px;align-self:flex-end}
  @keyframes gin{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
  .gtyping{display:flex;gap:4px;padding:12px 14px} .gtyping i{width:7px;height:7px;border-radius:50%;background:var(--mute);animation:gdot 1s infinite}
  .gtyping i:nth-child(2){animation-delay:.15s} .gtyping i:nth-child(3){animation-delay:.3s}
  @keyframes gdot{0%,60%,100%{opacity:.25;transform:none}30%{opacity:1;transform:translateY(-3px)}}
  .gchips{display:flex;flex-wrap:wrap;gap:7px;padding:12px 14px;border-top:1px solid var(--line);background:var(--panel);max-height:150px;overflow-y:auto}
  .gchips button{padding:7px 11px;border-radius:999px;border:1px solid var(--line);background:var(--panel2);color:var(--text);font:600 12.5px Inter,system-ui,sans-serif;cursor:pointer;transition:border-color .15s,color .15s}
  .gchips button:hover{border-color:var(--teal);color:var(--teal)} .gchips button:disabled{opacity:.4;cursor:default}
  .gnote{padding:0 14px 10px;color:var(--mute);font-size:11px;background:var(--panel)}
  @media (max-width:520px){.gbox{right:8px;left:8px;width:auto;bottom:76px;height:70vh}.gbtn{right:14px;bottom:14px}}
  @media (prefers-reduced-motion: reduce){.gbox,.gm,.gbtn{transition:none;animation:none}.gtyping i,.gbtn .dot{animation:none}}
  .rt th,.rt td{padding:6px 10px;white-space:nowrap;font-variant-numeric:tabular-nums}
  .rt .n{text-align:right} .rt tr.me td{color:var(--green);font-weight:700}
  .lim{margin:6px 0 0 18px;padding:0} .lim li{margin:6px 0}
  .tabs{display:flex;gap:6px;margin:0 0 10px;flex-wrap:wrap}
  .tabs button{padding:7px 12px;border-radius:8px;border:1px solid var(--line);background:var(--panel2);color:var(--mute);font-weight:600;cursor:pointer}
  .tabs button.on{background:var(--teal);color:#06222b;border-color:var(--teal)}
  .banner{margin:14px 0 0;padding:10px 14px;border:1px solid var(--line);border-radius:10px;background:var(--panel);color:var(--mute);font-size:13px}
"""
markup = markup.replace("Simulated supplier-payment system. Synthetic data only: no real money moves.",
                        "Simulated supplier-payment system. Synthetic data only: no real money moves.")
markup = markup.replace('<div class="note">Every run uses a fresh random seed. Dashed buttons are unseen tests that ReVive was not tuned on.</div>',
                        '<div class="note">These are recorded runs of the real code (seed 7). Dashed buttons are unseen tests. Run it live with the code to change the seed.</div>')

results_html = """
<section class="res">
  <div class="card">
    <h2 class="big">Results: three variants, same faults</h2>
    <p>B1 naive fixer: same detection, then just fixes. B0 strong rules: everything ReVive has except the uncertainty gate, so it acts on its best guess. B2 ReVive: full system. Dev = 10 scenarios x 30 seeds. Held-out = 7 frozen scenarios x 30 seeds, never tuned against.</p>
    <div class="tabs"><button id="tDev" class="on" onclick="showRes('dev')">Dev set</button><button id="tHeld" onclick="showRes('held')">Held-out set</button></div>
    <div class="wrap" id="restable"></div>
  </div>
  <div class="card">
    <h2 class="big">Safety vs autonomy</h2>
    <p>On clear cases B0 matches ReVive. The difference is the ambiguous case: B0 guesses and acts, ReVive escalates.</p>
    <div class="chart" id="f4"></div>
  </div>
  <div class="card">
    <h2 class="big">Is the uncertainty gate honest?</h2>
    <p>Synthetic incidents with a hidden true cause. Threshold set on 100 dev incidents, checked on 200 held-out. The gate's set contains the true cause 95% of the time (target 90%) and asks a human on about 15% of incidents.</p>
    <div class="chart" id="f6"></div>
  </div>
</section>

<button class="gbtn" id="gbtn" aria-expanded="false" aria-controls="gbox"><span class="dot"></span>Ask about ReVive</button>
<div class="gbox" id="gbox" role="dialog" aria-label="ReVive guide">
  <div class="ghead"><div class="gav"><svg viewBox="0 0 200 200" width="24" height="24" aria-hidden="true"><path d="M100 14A86 86 0 0 1 186 100" stroke="#2fb5d0" stroke-width="14" stroke-linecap="round" fill="none"/><path d="M100 186A86 86 0 0 1 14 100" stroke="#2fb5d0" stroke-width="14" stroke-linecap="round" fill="none"/><path d="M100 48L140 63V100C140 126 123 142 100 152C77 142 60 126 60 100V63Z" stroke="#f0b429" stroke-width="13" stroke-linejoin="round" fill="none"/><path d="M80 100L95 115L122 84" stroke="#34c27a" stroke-width="15" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg></div><div><b>ReVive guide</b><small>Prepared answers, checked against our results</small></div><button class="x" id="gx" aria-label="Close">×</button></div>
  <div class="gmsgs" id="gmsgs" aria-live="polite"></div>
  <div class="gchips" id="gchips"></div>
</div>
"""

new_script = script
new_script = new_script.replace('const r = await (await fetch(`/api/run?case=${sel}&agent=${agent}&seed=${Math.floor(Math.random()*1000)}`)).json();',
                                'const r = DATA.runs[`${sel}|${agent}`];')
new_script = new_script.replace('cases = await (await fetch("/api/cases")).json();', 'cases = DATA.cases;')
new_script = new_script.replace('try{ const i = await (await fetch("/api/info")).json(); $("aiflag").textContent = i.ai ? "· AI diagnosis: ON" : "· AI diagnosis: OFF (rules only)"; }catch(e){}',
                                '$("aiflag").textContent = "· Recorded runs";')
assert "DATA.runs" in new_script and "DATA.cases" in new_script

res_js = """
const NAMES={"B1 naive fixer":"B1 naive fixer","B0 strong rules":"B0 strong rules","B2 ReVive":"B2 ReVive"};
const ROWS=[["task_success_pct","Task success %"],["unsafe_run_rate_pct","Unsafe runs %"],["duplicate_payments","Duplicate payments"],
 ["misdirected_payments","Wrong-account payments"],["correct_autonomous_recovery_pct","Correct autonomous recovery %"],
 ["over_escalation_pct","Over-escalation %"],["under_escalation_pct","Under-escalation %"],["money_protected_sar","Money protected (SAR)"],
 ["avg_ticks_to_verified_recovery","Avg ticks to verified recovery"]];
function showRes(w){
  const key = w==="dev" ? "DEV SET (seeds 0-29)" : "HELD-OUT SET (seeds 100-129, never tuned)";
  const R = DATA.results[key], names = Object.keys(R);
  $("tDev").className = w==="dev"?"on":""; $("tHeld").className = w==="held"?"on":"";
  $("restable").innerHTML = `<table class="rt"><tr><th>Metric (${R[names[0]].runs} runs per variant)</th>`+names.map(n=>`<th class="n">${n}</th>`).join("")+`</tr>`+
    ROWS.map(([k,l])=>`<tr>${`<td>${l}</td>`}`+names.map(n=>{const v=R[n][k]; return `<td class="n ${n==="B2 ReVive"?"":""}">${v===null?"-":Number(v).toLocaleString()}</td>`}).join("")+`</tr>`).join("")+`</table>`;
}
const C3=[["B1 naive fixer","var(--red)"],["B0 strong rules","var(--amber)"],["B2 ReVive","var(--green)"]];
function barPanel(title,groups){
  const W=440,H=300,b=230,sc=1.8; let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${title}"><text class="ct" x="0" y="16">${title}</text>`;
  [0,25,50,75,100].forEach(v=>{const y=b-v*sc; s+=`<line class="grid" x1="34" x2="${W}" y1="${y}" y2="${y}"/><text class="ax" x="28" y="${y+4}" text-anchor="end">${v}</text>`});
  s+=`<line class="base" x1="34" x2="${W}" y1="${b}" y2="${b}"/>`;
  groups.forEach((g,gi)=>{const gx=60+gi*200;
    g.vals.forEach((v,i)=>{const h=Math.max(v*sc,2),x=gx+i*50,d=(gi*3+i)*0.12;
      s+=`<rect class="bar" style="transition-delay:${d}s" x="${x}" y="${b-h}" width="40" height="${h}" rx="5" fill="${C3[i][1]}"/>`+
         `<text class="vl fade" style="transition-delay:${d+.6}s" x="${x+20}" y="${b-h-7}" text-anchor="middle">${+v.toFixed(1)}%</text>`});
    s+=`<text class="ax" x="${gx+70}" y="${b+22}" text-anchor="middle">${g.l1}</text><text class="ax" x="${gx+70}" y="${b+38}" text-anchor="middle">${g.l2}</text>`});
  return s+`</svg>`;
}
function linePanel(title,xs,series,ymin,ymax,target,ylab,ticks){
  const W=440,H=300,L=40,R=W-8,T=34,B=236,X=v=>L+(v/0.85)*(R-L),Y=v=>B-(v-ymin)/(ymax-ymin)*(B-T);
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${title}"><text class="ct" x="0" y="16">${title}</text>`;
  (ticks||[0,25,50,75,100]).forEach(v=>{const y=Y(v); s+=`<line class="grid" x1="${L}" x2="${R}" y1="${y}" y2="${y}"/><text class="ax" x="${L-6}" y="${y+4}" text-anchor="end">${v}</text>`});
  [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8].forEach(v=>{s+=`<text class="ax" x="${X(v)}" y="${B+18}" text-anchor="middle">${v}</text>`});
  s+=`<text class="ax" x="${(L+R)/2}" y="${B+40}" text-anchor="middle">inclusion threshold q · ${ylab}</text><line class="base" x1="${L}" x2="${R}" y1="${B}" y2="${B}"/>`;
  s+=`<line x1="${X(0.3)}" x2="${X(0.3)}" y1="${T}" y2="${B}" stroke="#7d97a2" stroke-dasharray="3 4"/><text class="ax fade" x="${X(0.3)+5}" y="${T+10}">current setting</text>`;
  if(target!==null) s+=`<line class="fade" x1="${L}" x2="${R}" y1="${Y(target)}" y2="${Y(target)}" stroke="var(--red)" stroke-width="1.5" stroke-dasharray="6 5"/><text class="ax fade" x="${R}" y="${Y(target)+16}" text-anchor="end" style="fill:var(--red)">${target}% target</text>`;
  series.forEach((se,si)=>{const pts=xs.map((x,i)=>[X(x),Y(se.v[i])]);
    s+=`<path class="ln" pathLength="1" style="transition-delay:${si*0.3}s" d="M${pts.map(p=>p.join(" ")).join("L")}" fill="none" stroke="${se.c}" stroke-width="${se.w||2.5}" stroke-linejoin="round"/>`;
    pts.forEach((p,i)=>{s+=`<circle class="fade" style="transition-delay:${si*0.3+0.15+i*0.12}s" cx="${p[0]}" cy="${p[1]}" r="${se.r||4}" fill="${se.c}"/>`})});
  return s+`</svg>`;
}
function drawCharts(){
  const cl=DATA.split.clear, am=DATA.split.ambiguous, N=C3.map(c=>c[0]);
  $("f4").innerHTML = barPanel(`Clear cases (${cl["B2 ReVive"].runs} runs each)`,[
      {vals:N.map(n=>cl[n].correct_autonomous_recovery_pct||0),l1:"Recovered",l2:"on its own"},
      {vals:N.map(n=>cl[n].unsafe_run_rate_pct||0),l1:"Unsafe",l2:"runs"}]) +
    barPanel(`Ambiguous cases (${am["B2 ReVive"].runs} runs each)`,[
      {vals:N.map(n=>100-(am[n].under_escalation_pct||0)),l1:"Sent to a human",l2:"when needed"},
      {vals:N.map(n=>am[n].unsafe_run_rate_pct||0),l1:"Unsafe",l2:"runs"}]) +
    `<div class="legend">${C3.map(c=>`<span><i style="background:${c[1]}"></i>${c[0]}</span>`).join("")}</div>`;
  const qs=Object.keys(DATA.cal.curve).map(Number).sort((a,b)=>a-b), cv=q=>DATA.cal.curve[String(q)];
  $("f6").innerHTML = linePanel("Coverage: is the true cause in the set?",qs,[
      {v:qs.map(q=>cv(q).dev.coverage*100),c:"#7d97a2",w:1.8,r:3},{v:qs.map(q=>cv(q).held.coverage*100),c:"var(--teal)"}],75,100,DATA.cal.target*100,"% of incidents",[75,80,85,90,95,100]) +
    linePanel("Cost of caution: sent to a human",qs,[{v:qs.map(q=>cv(q).held.escalation_rate*100),c:"var(--green)"}],0,100,null,"% (held-out)") +
    `<div class="legend"><span><i style="background:var(--teal)"></i>held-out coverage</span><span><i style="background:#7d97a2"></i>dev coverage</span><span><i style="background:var(--green)"></i>escalation rate</span></div>`;
  const els=[$("f4"),$("f6")];
  if("IntersectionObserver" in window){const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add("in");io.unobserve(e.target)}}),{threshold:0.25}); els.forEach(e=>io.observe(e));}
  else els.forEach(e=>e.classList.add("in"));
}
drawCharts(); showRes("dev");
const GQA=[{"s": "Why not let AI fix everything?", "q": "Why not just let an AI agent fix everything?", "a": "We tested exactly that. A naive fixer that sees the same problems and simply fixes them was unsafe in 50% of development runs: 240 payments went to the wrong account and 30 were paid twice. In payments a wrong fix is worse than no fix, because a settled bank transfer cannot be undone."}, {"s": "What does the AI do?", "q": "What does the AI actually do in ReVive?", "a": "One job: diagnosis. A rules engine and a live Gemini call each name the possible causes of a fault from a small fixed list. Plain code does everything else: detecting the problem, both safety gates, the repair and the final check. The AI can never move money or change a bank account."}, {"s": "Why escalate, not guess?", "q": "Why does ReVive escalate instead of making its best guess?", "a": "When the evidence points to more than one cause, for example a changed bank account that could be a sync bug or fraud, a guess can send money to a fraudster. ReVive holds the payment and gives a person a report with the evidence for each cause and the actions it did not take. The strong-rules system guessed in these cases; ReVive escalated every one."}, {"s": "Isn't escalating everything safe?", "q": "Isn't escalating everything the safe option?", "a": "It would be safe but useless, which is why we measure both. ReVive fixed 100% of the clear cases on its own, and its over-escalation rate was 0%: it never sent a person a problem it could have safely fixed."}, {"s": "What if Gemini is down?", "q": "What happens if Gemini is slow or unavailable?", "a": "Each call has a 12-second limit and retries a backup model if the service is busy. If there is still no answer, ReVive uses a saved answer and then its rules. It never waits forever, and the two safety gates apply either way."}, {"s": "What if the bank doesn't reply?", "q": "What if the bank doesn't reply to a payment?", "a": "A timeout does not mean the payment failed. It means UNKNOWN: the money may have left. ReVive asks the bank by transaction reference first. If the bank says FAILED, it resubmits once with the same idempotency key, and the bank rejects duplicates, so it can never pay twice. If the bank stays silent, the payment is held and a person decides."}, {"s": "Are the results real?", "q": "How do I know these results are real?", "a": "Three systems were run on identical faults: 10 development failures and 7 held-out failures frozen before testing, each with 30 random seeds, 510 runs in total. The demos on this page are recorded runs of the actual code, not animations."}, {"s": "Is it real money?", "q": "Does it use real money or real bank data?", "a": "No. Everything runs in a simulator with synthetic suppliers, invoices and a simulated bank, so every failure can be injected and repeated exactly."}];
(function(){
  const box=$("gbox"),btn=$("gbtn"),msgs=$("gmsgs"),chips=$("gchips"); let started=false,busy=false; const asked=new Set();
  const add=(t,who)=>{const d=document.createElement("div");d.className="gm "+who;d.textContent=t;msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;return d};
  const typing=()=>{const d=document.createElement("div");d.className="gm bot gtyping";d.innerHTML="<i></i><i></i><i></i>";msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;return d};
  const drawChips=()=>{chips.innerHTML="";GQA.forEach((x,i)=>{if(asked.has(i))return;const b=document.createElement("button");b.textContent=x.s;b.title=x.q;b.onclick=()=>ask(i);b.disabled=busy;chips.appendChild(b)});
    if(asked.size===GQA.length){const b=document.createElement("button");b.textContent="Start over";b.onclick=()=>{asked.clear();msgs.innerHTML="";greet()};chips.appendChild(b)}};
  async function ask(i){if(busy)return;busy=true;asked.add(i);const q=add(GQA[i].q,"me");drawChips();const t=typing();await sleep(650+Math.min(GQA[i].a.length*2,700));t.remove();add(GQA[i].a,"bot");msgs.scrollTop=q.offsetTop-12;busy=false;drawChips()}
  async function greet(){busy=true;drawChips();const t=typing();await sleep(600);t.remove();add("Hi! I can explain how ReVive works and what the results show. Pick a question below.","bot");busy=false;drawChips()}
  const open=o=>{box.classList.toggle("open",o);btn.setAttribute("aria-expanded",o);if(o&&!started){started=true;greet()}};
  btn.onclick=()=>open(!box.classList.contains("open")); $("gx").onclick=()=>open(false);
  document.addEventListener("keydown",e=>{if(e.key==="Escape")open(false)});
})();
"""
# insert results js before the final async IIFE ends: simply append after it
page = ('<style>\n' + style[len("<style>"):] + extra + '</style>\n'
        '<meta name="claude:viewport-fit-sides" content="cover">\n'
        '<title>ReVive AI</title>\n' + markup + results_html +
        '<script>\nconst DATA = ' + json.dumps(data, separators=(",", ":")) + ';\n' + new_script + res_js + '</script>\n')
# title/meta must be near the top: move them before <style>
page = ('<meta name="claude:viewport-fit-sides" content="cover">\n<title>ReVive AI</title>\n' +
        page.replace('<meta name="claude:viewport-fit-sides" content="cover">\n<title>ReVive AI</title>\n', '', 1))
open("public.html", "w").write(page)
print("public.html", len(page) // 1024, "KB")
