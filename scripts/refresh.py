"""Free-tier ingestion: 2 current-season calls daily, 4 history calls once/year."""
import json, os, sys, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from model import run, validate, probability, VERSION
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'docs/data'; CACHE=ROOT/'cache'; DATA.mkdir(parents=True,exist_ok=True); CACHE.mkdir(exist_ok=True)

def fetch(path, **params):
    key=os.environ.get('CFBD_API_KEY','').strip()
    if not key: raise RuntimeError('Missing CFBD_API_KEY repository secret. No data was fabricated.')
    url='https://api.collegefootballdata.com'+path+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+key,'Accept':'application/json','User-Agent':'CollegeFootballMatchupLab/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=90) as response: result=json.load(response)
    except Exception as e:
        # Never include request headers, credentials or response body in logs.
        raise RuntimeError('CFBD request failed for '+path+'; check key, tier access, and quota.') from None
    if not isinstance(result,list) or not result: raise RuntimeError('Empty or unexpected CFBD response for '+path)
    return result

def write(path, obj):
    temp=path.with_suffix('.tmp'); temp.write_text(json.dumps(obj,separators=(',',':'),allow_nan=False)); temp.replace(path)

def main():
    now=datetime.now(timezone.utc); year=now.year if now.month>=7 else now.year-1
    games=[]
    for y in range(year-4,year+1):
        path=CACHE/f'games-{y}.json'
        if y==year or not path.exists(): write(path,fetch('/games',year=y,seasonType='both'))
        games.extend(json.loads(path.read_text()))
    advanced=fetch('/stats/season/advanced',year=year,excludeGarbageTime='true',classification='fbs')
    for row in advanced:
        if not isinstance(row.get('team'),str) or not isinstance(row.get('offense'),dict) or not isinstance(row.get('defense'),dict):
            raise RuntimeError('Advanced metric schema changed; last good snapshot preserved.')
    model, rows=run(games,now.isoformat()); report=validate(rows,year); model.season(year)
    teams={r['team']:dict(name=r['team'],conference=r.get('conference'),offense=r['offense'],defense=r['defense']) for r in advanced}
    for name, team in teams.items():
        team['rating'] = model.teams[name]
    upcoming=[]
    for g in games:
        if g.get('season')!=year or g.get('completed') or not g.get('startDate') or g['startDate']<now.isoformat(): continue
        if g.get('homeTeam') not in teams or g.get('awayTeam') not in teams: continue
        h,a=model.predict(g['homeTeam'],g['awayTeam'],g.get('neutralSite',False))
        n=min(model.teams[g['homeTeam']][2],model.teams[g['awayTeam']][2])
        upcoming.append(dict(id=g['id'],home=g['homeTeam'],away=g['awayTeam'],date=g['startDate'],week=g['week'],neutral=g.get('neutralSite',False),venue=g.get('venue'),
            projection=dict(home=round(h,1),away=round(a,1),homeWin=round(probability(h-a,report['scale']),4),experimental=report['status']!='passed',effectiveGames=round(n,1))))
    upcoming.sort(key=lambda g:g['date'])
    if len(teams)<50: raise RuntimeError('Incomplete FBS team response; last good snapshot preserved.')
    snapshot=dict(status='ready',updatedAt=now.isoformat(),season=year,source='CollegeFootballData.com',modelVersion=VERSION,validation=report,teams=teams,games=upcoming)
    write(DATA/'snapshot.json',snapshot)
    print(f'Updated {len(teams)} teams, {len(upcoming)} upcoming games; validation: {report["status"]}')

if __name__=='__main__':
    try: main()
    except Exception as e: print(str(e),file=sys.stderr); sys.exit(1)
