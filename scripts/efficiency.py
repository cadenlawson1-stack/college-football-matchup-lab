"""Game-level inputs for chronological efficiency modeling. No season-total leakage."""
import json, math

def collect_history(fetch, write, cache, root, games, year):
    keys=('ppa','successRate','explosiveness','drives','plays')
    result=[]
    for y in range(year-4,year+1):
        path=cache/f'advanced-games-full-{y}.json'
        if y==year or not path.exists():
            write(path,fetch('/stats/game/advanced',year=y,seasonType='both',excludeGarbageTime='false'))
        source=json.loads(path.read_text())
        for row in source:
            units={}
            for unit in ('offense','defense'):
                raw=row.get(unit,{})
                v={k:raw.get(k) for k in keys}
                for split in ('passingPlays','rushingPlays'):
                    v[split]={k:raw.get(split,{}).get(k) for k in ('ppa','successRate','totalPPA')}
                units[unit]=v
            result.append(dict(gameId=row.get('gameId'),team=row.get('team'),**units))
    dest=cache;dest.mkdir(exist_ok=True)
    write(dest/'model_history.json',dict(games=games,advanced=result))
    print('Efficiency history:',len(result),'team-game rows')
    return dict(games=games,advanced=result)

from collections import defaultdict
from model import Model, completed, metrics, probability, validate
from datetime import datetime, timezone
import random

CANDIDATE_VERSION='efficiency-v2'
PRIORS=[.25,.10,.43,.43,2.2,12.,.50]
RIDGES=(10.,40.,120.)
DECAYS=(.85,.93,.98)
BLENDS=(.25,.5,.75,1.)

def finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def raw_values(raw, points):
    passing=raw.get('passingPlays') or {}; rushing=raw.get('rushingPlays') or {}
    drives=raw.get('drives')
    drives=drives if finite(drives) and 3<=drives<=30 else None
    counts=[]
    for split in (passing,rushing):
        p,t=split.get('ppa'),split.get('totalPPA')
        counts.append(t/p if finite(p) and finite(t) and abs(p)>1e-8 and 0<t/p<200 else None)
    rate=counts[0]/sum(counts) if all(c is not None for c in counts) and sum(counts)>0 else None
    return [passing.get('ppa'),rushing.get('ppa'),passing.get('successRate'),rushing.get('successRate'),points/drives if drives else None,drives,rate]

class EfficiencyState:
    def __init__(self,decay):
        self.decay=decay;self.year=None;self.teams={}
    def season(self,year):
        if year!=self.year:
            for units in self.teams.values():
                for s,w in units.values():
                    for i in range(7):s[i]*=.5;w[i]*=.5
            self.year=year
    def profile(self,name,unit):
        pair=self.teams.get(name,{}).get(unit)
        if pair is None:return PRIORS[:]
        s,w=pair
        return [p+s[i]/(w[i]+4) for i,p in enumerate(PRIORS)]
    def update(self,name,unit,values,opponent):
        units=self.teams.setdefault(name,{})
        s,w=units.setdefault(unit,([0.]*7,[0.]*7))
        for i,v in enumerate(values):
            s[i]*=self.decay;w[i]*=self.decay
            if not finite(v):continue
            adjusted=v-(opponent[i]-PRIORS[i]) if i<5 else v
            s[i]+=adjusted-PRIORS[i];w[i]+=1
    def export(self,names):
        return {n:{u:self.profile(n,u) for u in ('offense','defense')} for n in names}

def features(off,defense,old_score,home):
    mix=max(.2,min(.8,.75*off[6]+.25*defense[6]))
    ppd=[old_score/12,off[4],defense[4],off[0]*mix,defense[0]*mix,
         off[1]*(1-mix),defense[1]*(1-mix),off[2]*mix,defense[2]*mix,
         off[3]*(1-mix),defense[3]*(1-mix),off[5],defense[5],home,mix]
    pace=[off[5],defense[5],off[2]*mix+off[3]*(1-mix),defense[2]*mix+defense[3]*(1-mix),home]
    return ppd,pace

def solve(a,b):
    a=[row[:]+[v] for row,v in zip(a,b)];n=len(b)
    for i in range(n):
        pivot=max(range(i,n),key=lambda j:abs(a[j][i]));a[i],a[pivot]=a[pivot],a[i]
        div=a[i][i]
        if abs(div)<1e-10:raise ValueError('Singular training matrix')
        a[i]=[v/div for v in a[i]]
        for j in range(n):
            if j!=i:
                f=a[j][i];a[j]=[x-f*y for x,y in zip(a[j],a[i])]
    return [row[-1] for row in a]

def fit(x,y,penalty):
    if len(x)<100:raise ValueError('Not enough training observations')
    n=len(x);k=len(x[0]);means=[sum(r[j] for r in x)/n for j in range(k)]
    scales=[max(1e-6,math.sqrt(sum((r[j]-means[j])**2 for r in x)/n)) for j in range(k)]
    a=[[0.]*(k+1) for _ in range(k+1)];b=[0.]*(k+1)
    for row,target in zip(x,y):
        z=[1.]+[(v-m)/s for v,m,s in zip(row,means,scales)]
        for i in range(k+1):
            b[i]+=z[i]*target
            for j in range(i,k+1):a[i][j]+=z[i]*z[j]
    for i in range(k+1):
        for j in range(i):a[i][j]=a[j][i]
        if i:a[i][i]+=penalty
    return dict(means=means,scales=scales,coefficients=solve(a,b))

def predict_regression(fit,x):
    return fit['coefficients'][0]+sum(c*(v-m)/s for c,v,m,s in zip(fit['coefficients'][1:],x,fit['means'],fit['scales']))

def predict_team(engine,off,defense,old_score,home):
    x,z=features(off,defense,old_score,home)
    ppd=max(.3,min(5.5,predict_regression(engine['ppd'],x)))
    drives=max(7.,min(18.,predict_regression(engine['pace'],z)))
    return engine['blend']*ppd*drives+(1-engine['blend'])*old_score

def build_rows(games,advanced,decay,cutoff):
    lookup={(r['gameId'],r['team']):r for r in advanced}
    days=defaultdict(list)
    for g in games:
        if completed(g,cutoff):days[(g['season'],g['startDate'][:10])].append(g)
    state=EfficiencyState(decay);old=Model();rows=[]
    for (year,day),batch in sorted(days.items()):
        state.season(year);old.season(year);updates=[]
        for g in batch:
            hn,an=g['homeTeam'],g['awayTeam'];h,a=old.predict(hn,an,g.get('neutralSite',False))
            sign=0 if g.get('neutralSite') else 1
            profiles=[state.profile(hn,'offense'),state.profile(an,'defense'),state.profile(an,'offense'),state.profile(hn,'defense')]
            hr=lookup.get((g['id'],hn));ar=lookup.get((g['id'],an))
            hv=raw_values(hr['offense'],g['homePoints']) if hr else [None]*7
            av=raw_values(ar['offense'],g['awayPoints']) if ar else [None]*7
            ready=all(finite(v) for v in hv[:6]+av[:6])
            if g['homePoints']!=g['awayPoints']:
                rows.append(dict(id=g['id'],year=year,week=g['week'],day=day,home=h,away=a,margin=h-a,
                    hp=g['homePoints'],ap=g['awayPoints'],y=int(g['homePoints']>g['awayPoints']),
                    baselineH=28+1.5*sign,baselineA=28-1.5*sign,profiles=profiles,sign=sign,
                    homeTarget=hv[4],awayTarget=av[4],homeDrives=hv[5],awayDrives=av[5],covered=ready))
            # Opponent adjustment uses only pregame estimates. All updates wait until the day's games are predicted.
            updates.extend([(hn,'offense',hv,profiles[1]),(an,'defense',hv,profiles[0]),
                            (an,'offense',av,profiles[3]),(hn,'defense',av,profiles[2])])
        for name,unit,values,opp in updates:state.update(name,unit,values,opp)
        for g in batch:old.update(g)
    return state,rows

def train(rows,penalty,last_year):
    x=[];z=[];y=[];d=[]
    for r in rows:
        if r['year']>last_year or not r['covered']:continue
        ho,ad,ao,hd=r['profiles']
        for off,de,score,sign,target,drives in [(ho,ad,r['home'],r['sign'],r['homeTarget'],r['homeDrives']),(ao,hd,r['away'],-r['sign'],r['awayTarget'],r['awayDrives'])]:
            a,b=features(off,de,score,sign);x.append(a);z.append(b);y.append(target);d.append(drives)
    return dict(ppd=fit(x,y,penalty),pace=fit(z,d,penalty))

def candidate_rows(rows,engine,year):
    out=[]
    for r in rows:
        if r['year']!=year:continue
        ho,ad,ao,hd=r['profiles'];c=r.copy()
        c['home']=predict_team(engine,ho,ad,r['home'],r['sign']);c['away']=predict_team(engine,ao,hd,r['away'],-r['sign']);c['margin']=c['home']-c['away'];out.append(c)
    return out

def paired_interval(base,candidate,base_scale,candidate_scale,kind):
    groups=defaultdict(list)
    for b,c in zip(base,candidate):
        assert b['id']==c['id']
        if kind=='score':
            error=lambda r:(abs(r['home']-r['hp'])+abs(r['away']-r['ap']))/2
        else:
            error=lambda r:(probability(r['margin'],base_scale if r is b else candidate_scale)-r['y'])**2
        groups[b['week']].append(error(b)-error(c))
    keys=list(groups);rng=random.Random(70421);samples=[]
    if not keys:return [None,None]
    for _ in range(1000):
        picked=[groups[rng.choice(keys)] for _ in keys]
        samples.append(sum(sum(v) for v in picked)/sum(len(v) for v in picked))
    samples.sort();return [samples[25],samples[974]]

def evaluate_upgrade(games,advanced,year,cutoff=None):
    cutoff=cutoff or datetime.now(timezone.utc).isoformat()
    tune_year=year-3;cal_year=year-2;hold_year=year-1
    selected=None;states={}
    # Selection is confined to the tuning season; no holdout or current outcomes enter this loop.
    for decay in DECAYS:
        state,rows=build_rows(games,advanced,decay,cutoff);states[decay]=(state,rows)
        for ridge in RIDGES:
            initial=train(rows,ridge,tune_year-1)
            for blend in BLENDS:
                engine=dict(initial,blend=blend,decay=decay,ridge=ridge)
                trial=candidate_rows(rows,engine,tune_year)
                score=sum(abs(r['home']-r['hp'])+abs(r['away']-r['ap']) for r in trial)/(2*len(trial))
                if selected is None or score<selected[0]:selected=(score,decay,ridge,blend)
    tuning_mae,decay,ridge,blend=selected;state,rows=states[decay]
    engine=dict(train(rows,ridge,tune_year),blend=blend,decay=decay,ridge=ridge)
    cal=candidate_rows(rows,engine,cal_year)
    if len(cal)<200:raise ValueError('Insufficient probability calibration history')
    scale=min(range(4,41),key=lambda s:metrics(cal,s)['logLoss'])
    original=validate(rows,year);reports={};paired={}
    for y in (hold_year,year):
        base=[r for r in rows if r['year']==y];cand=candidate_rows(rows,engine,y)
        if not base:continue
        bm=metrics(base,original['scale']);cm=metrics(cand,scale)
        cm['marginMAE']=sum(abs(r['margin']-(r['hp']-r['ap'])) for r in cand)/len(cand)
        bm['marginMAE']=sum(abs(r['margin']-(r['hp']-r['ap'])) for r in base)/len(base)
        coverage=sum(r['covered'] for r in base)/len(base)
        reports[str(y)]=dict(baseline=bm,candidate=cm,coverage=coverage)
        if y==hold_year:
            paired=dict(scoreGain95CI=paired_interval(base,cand,original['scale'],scale,'score'),brierGain95CI=paired_interval(base,cand,original['scale'],scale,'brier'))
    test=reports.get(str(hold_year));audit=reports.get(str(year))
    reasons=[]
    if not test or test['baseline']['games']<200:reasons.append('Insufficient holdout history')
    else:
        b,c=test['baseline'],test['candidate']
        if test['coverage']<.95:reasons.append('Game-level advanced-stat coverage below 95%')
        if b['scoreMAE']-c['scoreMAE']<.15:reasons.append('Score-error reduction below 0.15 points per team')
        if b['brier']-c['brier']<.002:reasons.append('Brier improvement below 0.002')
        if paired['scoreGain95CI'][0]<=0:reasons.append('Score improvement not clear in week-block bootstrap')
        if paired['brierGain95CI'][0]<=0:reasons.append('Probability improvement not clear in week-block bootstrap')
        if c['marginMAE']>b['marginMAE']:reasons.append('Margin error increased')
        if c['calibrationError']>min(.075,b['calibrationError']+.01):reasons.append('Probability calibration worsened')
    if not audit or audit['baseline']['games']<100:reasons.append('Insufficient current-season audit history')
    elif audit['coverage']<.95 or audit['candidate']['scoreMAE']>audit['baseline']['scoreMAE']+.2 or audit['candidate']['brier']>audit['baseline']['brier']+.005:
        reasons.append('Current-season audit exceeded non-regression tolerance')
    promoted=not reasons
    report=dict(candidateVersion=CANDIDATE_VERSION,selectedVersion=CANDIDATE_VERSION if promoted else 'points-v1',promoted=promoted,
        status='promoted' if promoted else 'retained_baseline',reasons=reasons,trainingThrough=tune_year,tuningYear=tune_year,
        calibrationYear=cal_year,holdoutYear=hold_year,auditYear=year,configuration=dict(decay=decay,ridge=ridge,blend=blend,scale=scale),
        tuningScoreMAE=tuning_mae,seasons=reports,**paired,
        protocol='Tune 36 fixed candidates on the tuning year using earlier training only; refit through tuning year; calibrate probabilities on the next year; test the following year and audit completed current games. Never tune on either evaluation set. Week-block bootstrap uses 1,000 resamples. Candidate must improve score MAE by 0.15+, Brier by 0.002+, both 95% gain intervals above zero, margin MAE no worse, ECE <= min(0.075, baseline+0.01), 95% advanced coverage, and current-season non-regression.',
        limitations='Game-level statistics include garbage time to align drive counts with final scores. Points per drive includes all team points, including defense/special teams; pass mix is inferred from total PPA divided by per-play PPA when available. Opponent adjustment is online and approximate. Historical source revisions and date-level rather than publication-time availability can affect retrospective results.')
    state.season(year)
    return report,engine,state,original
