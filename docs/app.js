'use strict';
const $=id=>document.getElementById(id);
const METRICS=[
 ['Overall EPA / play','ppa','number','CFBD PPA: expected scoring value added per play. Offense: produced; defense: allowed.','Overall efficiency'],
 ['Overall success rate','successRate','percent','Successful plays gain at least 50% of needed yards on first down, 70% on second, and 100% on third or fourth.'],
 ['Explosiveness','explosiveness','number','Average EPA (CFBD PPA) on successful plays.'],
 ['Passing EPA / play','passingPlays.ppa','number','Passing efficiency: EPA per passing play. Offense: produced; defense: allowed.','Passing efficiency'],
 ['Passing success rate','passingPlays.successRate','percent','Passing efficiency: share of passing plays classified as successful.'],
 ['Passing explosiveness','passingPlays.explosiveness','number','Average EPA (CFBD PPA) on successful passing plays.'],
 ['Rushing EPA / play','rushingPlays.ppa','number','Rushing efficiency: EPA per rushing play. Offense: produced; defense: allowed.','Rushing efficiency'],
 ['Rushing success rate','rushingPlays.successRate','percent','Rushing efficiency: share of rushing plays classified as successful.'],
 ['Rushing explosiveness','rushingPlays.explosiveness','number','Average EPA (CFBD PPA) on successful rushing plays.'],
 ['Standard-down success','standardDowns.successRate','percent','Success rate on standard downs.','Situations & scoring'],
 ['Passing-down success','passingDowns.successRate','percent','Success rate on second-and-8+, or third/fourth-and-5+.'],
 ['Points / opportunity','pointsPerOpportunity','number','Points per drive reaching the opponent’s 40-yard line or closer.'],
 ['Havoc allowed / created','havoc.total','percent','Offense: havoc allowed (lower is better). Defense: havoc created (higher is better).','Disruption & the run game'],
 ['Stuff rate','stuffRate','percent','Offense: rushes stuffed (lower is better). Defense: opponent rushes stuffed (higher is better).'],
 ['Power success','powerSuccess','percent','Short-yardage rushing success: produced by offense, allowed by defense.'],
 ['Line yards / rush','lineYards','number','Blocking contribution per rush: produced by offense, allowed by defense.'],
 ['Second-level yards','secondLevelYards','number','Second-level rushing yards per rush: produced by offense, allowed by defense.'],
 ['Open-field yards','openFieldYards','number','Open-field rushing yards per rush: produced by offense, allowed by defense.']
];
let data=null,selected=null;
function val(obj,path){return path.split('.').reduce((o,k)=>o?.[k],obj);}
function finite(v){return typeof v==='number'&&Number.isFinite(v);}
function format(v,type){return finite(v)?(type==='percent'?(v*100).toFixed(1)+'%':v.toFixed(2)):'—';}
function text(id,value){$(id).textContent=value;}
function option(label,value){const o=document.createElement('option');o.value=value;o.textContent=label;return o;}
function unitRank(team,unit,path){
 const v=val(team?.[unit],path);if(!finite(v))return null;
 const values=Object.values(data?.teams||{}).map(t=>val(t[unit],path)).filter(finite);
 const inverse=['havoc.total','stuffRate'].includes(path),lower=unit==='defense'?!inverse:inverse;
 return {rank:1+values.filter(x=>lower?x<v:x>v).length,total:values.length};
}
function renderMatchup(prefix,offense,defense){
 text(prefix+'-title',(offense?.name||'Away')+' offense vs. '+(defense?.name||'Home')+' defense');
 const header=(id,name,unit)=>{const th=$(id);th.replaceChildren(document.createTextNode(name));const small=document.createElement('small');small.textContent=unit;th.append(small);};
 header(prefix+'-offense',offense?.name||'Offense','OFFENSE');header(prefix+'-defense',defense?.name||'Defense','DEFENSE');
 const rows=[];
 METRICS.forEach(([label,path,type,description,group])=>{
  if(group){const row=document.createElement('tr'),th=document.createElement('th');th.colSpan=3;th.scope='colgroup';th.textContent=group;row.className='metric-group';row.append(th);rows.push(row);}
  const row=document.createElement('tr');row.dataset.metric=path;
  const metric=document.createElement('th');metric.scope='row';metric.textContent=label;metric.title=description;
  const cell=(team,unit)=>{const td=document.createElement('td'),v=val(team?.[unit],path);td.textContent=format(v,type);const rank=unitRank(team,unit,path);
   if(rank){const small=document.createElement('small');small.textContent='#'+rank.rank+' / '+rank.total;small.setAttribute('aria-label','FBS '+unit+' rank '+rank.rank+' of '+rank.total);td.append(small);if(rank.rank<=Math.ceil(rank.total/4))td.className='top-unit';}
   return td;};
  row.append(cell(offense,'offense'),metric,cell(defense,'defense'));rows.push(row);
 });
 $(prefix+'-metrics').replaceChildren(...rows);
}
function renderMetrics(){
 const away=data?.teams?.[$('away').value],home=data?.teams?.[$('home').value];
 renderMatchup('away-matchup',away,home);renderMatchup('home-matchup',home,away);
}
function efficiencyEstimate(home,away,neutral,oldHome,oldAway){
 const engine=data?.candidateModel,ht=data?.teams?.[home]?.efficiency,at=data?.teams?.[away]?.efficiency;
 if(!engine||!ht||!at)return null;
 const clamp=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
 const regression=(m,x)=>m.coefficients[0]+x.reduce((sum,v,i)=>sum+m.coefficients[i+1]*(v-m.means[i])/m.scales[i],0);
 const team=(off,defense,old,homeSign)=>{
  const mix=clamp(.75*off[6]+.25*defense[6],.2,.8);
  const x=[old/12,off[4],defense[4],off[0]*mix,defense[0]*mix,off[1]*(1-mix),defense[1]*(1-mix),off[2]*mix,defense[2]*mix,off[3]*(1-mix),defense[3]*(1-mix),off[5],defense[5],homeSign,mix];
  const z=[off[5],defense[5],off[2]*mix+off[3]*(1-mix),defense[2]*mix+defense[3]*(1-mix),homeSign];
  return engine.blend*clamp(regression(engine.ppd,x),.3,5.5)*clamp(regression(engine.pace,z),7,18)+(1-engine.blend)*old;
 };
 const h=team(ht.offense,at.defense,oldHome,neutral?0:1),a=team(at.offense,ht.defense,oldAway,neutral?0:-1);
 return {home:h,away:a,homeWin:1/(1+Math.exp(-clamp((h-a)/engine.scale,-35,35)))};
}
function render(){
 renderMetrics();if(!data||data.status!=='ready')return;
 const away=$('away').value,home=$('home').value,neutral=$('neutral').checked;
 text('away-name',away);text('home-name',home);
 if(away===home){$('candidate-preview').hidden=true;text('fixture','Choose two different teams.');['away-score','home-score'].forEach(id=>text(id,'—'));['away-prob','home-prob'].forEach(id=>text(id,'Unavailable'));$('prob-bar').style.width='50%';return;}
 const ar=data.teams[away]?.rating,hr=data.teams[home]?.rating;
 if(!ar||!hr)return;
 let h=Math.max(0,28+hr[0]/(hr[2]+5)+ar[1]/(ar[2]+5)+(neutral?0:1.5));
 let a=Math.max(0,28+ar[0]/(ar[2]+5)+hr[1]/(hr[2]+5)-(neutral?0:1.5));
 const candidate=efficiencyEstimate(home,away,neutral,h,a);
 const active=data.modelVersion==='efficiency-v2';
 $('candidate-preview').hidden=!candidate||active;
 if(candidate&&!active){
  text('candidate-score',away+' '+Math.round(candidate.away)+' – '+home+' '+Math.round(candidate.home));
  text('candidate-odds',home+' win probability: '+(candidate.homeWin*100).toFixed(1)+'% • Experimental; not approved as the default.');
 }
 if(candidate&&active){h=candidate.home;a=candidate.away;}
 const p=1/(1+Math.exp(-Math.max(-35,Math.min(35,(h-a)/(data.validation.scale||10)))));
 text('away-score',Math.round(a));text('home-score',Math.round(h));
 const homePct=Math.round(p*1000)/10; text('home-prob',homePct.toFixed(1)+'% win probability');text('away-prob',(100-homePct).toFixed(1)+'% win probability');
 $('prob-bar').style.width=(100-homePct)+'%';
 const g=selected&&selected.away===away&&selected.home===home&&Boolean(selected.neutral)===neutral?selected:null;
 text('fixture',g?new Date(g.date).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'})+' • '+(g.venue||'Venue not supplied'):'Custom matchup • '+(neutral?'Neutral site':home+' at home'));
 text('model-label',active?'Efficiency model • checks passed':data.validation.status==='passed'?'Scoring model • initial checks passed':'Experimental estimate');
 text('projection-note','Expected score, rounded • '+(data.validation.status==='passed'?'Passed initial held-out criteria; future accuracy is uncertain.':'Historical validation has not passed. Treat scores and probabilities as experimental.')+(Math.min(ar[2],hr[2])<3?' Limited team history.':''));
}
function validation(){const v=data.validation||{};if(!v.metrics){text('validation','Not yet validated: '+String(v.status||'not run').replaceAll('_',' ')+'.');return;}
 text('validation',(v.status==='passed'?'Initial criteria passed.':'Criteria failed; projections remain experimental.')+' Probability calibration: '+v.calibrationYear+'. Unseen test season: '+v.holdoutYear+' ('+v.metrics.games+' games).');
 const m=v.metrics;$('validation-metrics').replaceChildren(...[['Brier score',m.brier.toFixed(3)],['Score error',m.scoreMAE.toFixed(1)+' pts'],['Calibration error',(100*m.calibrationError).toFixed(1)+'%']].map(([label,value])=>{const d=document.createElement('div');d.textContent=label;const s=document.createElement('strong');s.textContent=value;d.append(s);return d;}));
 const p=document.createElement('p');p.textContent='Lower is better. Baselines: Brier '+v.baselineBrier.toFixed(3)+'; score error '+m.baselineScoreMAE.toFixed(1)+' points per team. No in-season accuracy claim is implied.';$('validation-metrics').after(p);
}
function renderComparison(){
 const r=data?.modelComparison;if(!r)return;
 $('upgrade-evidence').hidden=false;
 text('upgrade-decision',r.promoted?'Efficiency model passed all promotion checks and is active.':'Current scoring model retained. The efficiency candidate has not passed every promotion check.');
 text('upgrade-protocol','Parameters selected using '+r.tuningYear+' only; final training through '+r.trainingThrough+'; probabilities calibrated on '+r.calibrationYear+'. Evaluations below were excluded from fitting and parameter selection.');
 const body=$('upgrade-results');body.replaceChildren();
 for(const [year,season] of Object.entries(r.seasons)){
  for(const [label,key,fmt] of [['Score error / team','scoreMAE',v=>v.toFixed(2)+' pts'],['Brier probability error','brier',v=>v.toFixed(4)],['Margin error','marginMAE',v=>v.toFixed(2)+' pts']]){
   const row=document.createElement('tr');[year+' · '+season.baseline.games+' games',label,fmt(season.baseline[key]),fmt(season.candidate[key])].forEach(v=>{const td=document.createElement('td');td.textContent=v;row.append(td);});body.append(row);
  }
 }
 text('upgrade-reasons',r.promoted?'All predeclared promotion checks passed.':r.reasons.join('; ')+'.');
 const ci=(r.scoreGain95CI||[]).map(v=>v.toFixed(3)).join(' to '),bi=(r.brierGain95CI||[]).map(v=>v.toFixed(4)).join(' to ');
 text('upgrade-intervals',r.holdoutYear+' holdout improvement, 95% week-block bootstrap intervals: score '+ci+' points/team; Brier '+bi+'. An interval crossing zero does not establish an improvement.');
 text('upgrade-limitations',r.limitations);
 if(r.promoted)text('model-description','The efficiency model predicts points per drive and drive count from opponent-adjusted, recency-weighted passing/rushing EPA and success, scoring and pace history. Ridge coefficients, recency, shrinkage and optional blend with the original score model are fitted using earlier seasons. Home field is learned through regression. The training and evaluation years are shown below.');
}
async function init(){renderMetrics();try{
 const response=await fetch('data/snapshot.json',{cache:'no-store'});if(!response.ok)throw Error('snapshot');data=await response.json();
 if(data.status!=='ready'){text('status','Data connection pending. The dashboard is installed; live stats and historical testing will begin after the CFBD secret is saved and the update runs.');$('status').classList.add('warn');return;}
 const age=(Date.now()-Date.parse(data.updatedAt))/3600000;
 if(!Number.isFinite(age))throw Error('invalid timestamp');
 text('status',(age>48?'Data is stale. ':'Daily snapshot connected. ')+data.season+' season • '+Object.keys(data.teams).length+' teams • '+data.games.length+' upcoming matchups'+(age>48?' • Check the update workflow.':''));$('status').classList.toggle('warn',age>48);
 text('updated','Updated '+new Date(data.updatedAt).toLocaleString());
 const names=Object.keys(data.teams).sort();for(const id of ['away','home']){$(id).replaceChildren(...names.map(n=>option(n,n)));$(id).disabled=false;}
 $('home').value=names[1]||names[0];
 $('game').replaceChildren(option('Build a custom matchup',''),...data.games.map(g=>option('W'+g.week+' · '+g.away+' at '+g.home,String(g.id))));$('game').disabled=false;
 const query=new URLSearchParams(location.search);const first=data.games.find(g=>String(g.id)===query.get('game'))||data.games[0];
 if(first){$('game').value=first.id;chooseGame();}else render();validation();renderComparison();
 }catch(e){text('status','Unable to load the data snapshot. Reload or check the repository update status below.');$('status').classList.add('warn');}}
function chooseGame(){selected=data.games.find(g=>String(g.id)===$('game').value)||null;if(selected){$('away').value=selected.away;$('home').value=selected.home;$('neutral').checked=Boolean(selected.neutral);history.replaceState(null,'','?game='+encodeURIComponent(selected.id));}else history.replaceState(null,'',location.pathname);render();}
$('game').addEventListener('change',chooseGame);
for(const id of ['away','home','neutral'])$(id).addEventListener('change',()=>{selected=null;$('game').value='';history.replaceState(null,'',location.pathname);render();});
init();
