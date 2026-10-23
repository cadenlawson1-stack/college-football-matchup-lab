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
    dest=root/'docs/data';dest.mkdir(exist_ok=True)
    write(dest/'model_history.json',dict(games=games,advanced=result))
    print('Efficiency history:',len(result),'team-game rows')
