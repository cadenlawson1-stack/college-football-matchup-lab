"""Chronological points model; all features exist before kickoff. No API dependencies."""
import math
from collections import defaultdict
from datetime import datetime, timezone

VERSION = 'points-v1'

def probability(margin, scale):
    return 1 / (1 + math.exp(-max(-35, min(35, margin / scale))))

class Model:
    def __init__(self):
        self.teams = defaultdict(lambda: [0., 0., 0])
        self.year = None
    def season(self, year):
        if year != self.year:
            for team, (o, d, n) in self.teams.items():
                self.teams[team] = [o * .35, d * .35, n * .35]
            self.year = year
    def predict(self, home, away, neutral=False):
        ho, hd, hn = self.teams[home]
        ao, ad, an = self.teams[away]
        h = 28 + ho/(hn+5) + ad/(an+5) + (0 if neutral else 1.5)
        a = 28 + ao/(an+5) + hd/(hn+5) - (0 if neutral else 1.5)
        return max(0, h), max(0, a)
    def update(self, game):
        h, a = game['homeTeam'], game['awayTeam']
        hp, ap = game['homePoints'], game['awayPoints']
        for t, scored, allowed in [(h,hp,ap),(a,ap,hp)]:
            s = self.teams[t]
            s[0] += scored-28; s[1] += allowed-28; s[2] += 1

def completed(g, cutoff):
    return (g.get('completed') is True and isinstance(g.get('homePoints'), (int,float))
            and isinstance(g.get('awayPoints'), (int,float)) and g.get('startDate','') < cutoff
            and g.get('homeClassification') == 'fbs' and g.get('awayClassification') == 'fbs')

def run(games, now=None):
    cutoff = now or datetime.now(timezone.utc).isoformat()
    model = Model(); rows=[]
    by_day = defaultdict(list)
    for g in games:
        if completed(g, cutoff): by_day[(g['season'],g['startDate'][:10])].append(g)
    # Batch each day: no game on a given day learns from another game that day.
    for (year, day), batch in sorted(by_day.items()):
        model.season(year)
        for g in batch:
            h,a=model.predict(g['homeTeam'],g['awayTeam'],g.get('neutralSite',False))
            if g['homePoints'] != g['awayPoints']:
                rows.append(dict(year=year, home=h, away=a, margin=h-a,
                    hp=g['homePoints'], ap=g['awayPoints'], y=int(g['homePoints']>g['awayPoints']),
                    baselineH=28+(0 if g.get('neutralSite') else 1.5),
                    baselineA=28-(0 if g.get('neutralSite') else 1.5)))
        for g in batch: model.update(g)
    return model, rows

def metrics(rows, scale):
    if not rows: return None
    ps=[probability(r['margin'],scale) for r in rows]; n=len(rows)
    bins=[]
    for lo in range(0,100,10):
        b=[(p,r['y']) for p,r in zip(ps,rows) if lo/100<=p<(lo+10)/100]
        if b: bins.append(dict(lower=lo/100, count=len(b), predicted=sum(p for p,y in b)/len(b), actual=sum(y for p,y in b)/len(b)))
    return dict(games=n, brier=sum((p-r['y'])**2 for p,r in zip(ps,rows))/n,
        logLoss=-sum(r['y']*math.log(max(p,1e-12))+(1-r['y'])*math.log(max(1-p,1e-12)) for p,r in zip(ps,rows))/n,
        scoreMAE=sum(abs(r['home']-r['hp'])+abs(r['away']-r['ap']) for r in rows)/(2*n),
        baselineScoreMAE=sum(abs(r['baselineH']-r['hp'])+abs(r['baselineA']-r['ap']) for r in rows)/(2*n),
        accuracy=sum((p>=.5)==bool(r['y']) for p,r in zip(ps,rows))/n,
        calibrationError=sum(b['count']*abs(b['predicted']-b['actual']) for b in bins)/n,
        calibrationBins=bins)

def validate(rows, current_year):
    # Strict year separation: calibration never includes the held-out season.
    calibration=[r for r in rows if r['year']==current_year-2]
    holdout=[r for r in rows if r['year']==current_year-1]
    if len(calibration)<200 or len(holdout)<200:
        return dict(status='insufficient_history', version=VERSION, scale=10, calibrationYear=current_year-2, holdoutYear=current_year-1)
    scale=min(range(4,41), key=lambda s: metrics(calibration,s)['logLoss'])
    m=metrics(holdout,scale)
    home_rate=sum(r['y'] for r in calibration)/len(calibration)
    baseline_brier=sum((home_rate-r['y'])**2 for r in holdout)/len(holdout)
    passed=m['brier']<min(.25,baseline_brier) and m['scoreMAE']<m['baselineScoreMAE'] and m['calibrationError']<=.10
    return dict(status='passed' if passed else 'failed', version=VERSION, scale=scale,
        calibrationYear=current_year-2,holdoutYear=current_year-1,baselineBrier=baseline_brier,
        criteria='200+ games in calibration and holdout; Brier below 0.25 and calibrated home-rate baseline; score MAE below fixed 28-point baseline; ECE <= 0.10.', metrics=m)
