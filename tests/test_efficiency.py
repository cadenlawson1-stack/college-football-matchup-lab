import unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from efficiency import EfficiencyState,features,fit,predict_regression,raw_values,build_rows,PRIORS

def game(i,date):
    return dict(id=i,season=2023,week=i,startDate=date,homeTeam='A',awayTeam='B',homePoints=30,awayPoints=20,completed=True,homeClassification='fbs',awayClassification='fbs',neutralSite=False)
def stats(i,name):
    return dict(gameId=i,team=name,offense=dict(ppa=.3,successRate=.5,drives=12,plays=60,passingPlays=dict(ppa=.5,totalPPA=15,successRate=.5),rushingPlays=dict(ppa=.2,totalPPA=6,successRate=.4)))
class EfficiencySafeguards(unittest.TestCase):
    def test_no_game_result_or_efficiency_leaks_into_its_features(self):
        games=[game(1,'2023-09-01'),game(2,'2023-09-08')];advanced=[stats(i,n) for i in [1,2] for n in ['A','B']]
        _,first=build_rows(games,advanced,.93,'2024-01-01')
        games[1]['homePoints']=90;advanced[2]['offense']['passingPlays']['ppa']=9
        _,second=build_rows(games,advanced,.93,'2024-01-01')
        self.assertEqual([r['profiles'] for r in first],[r['profiles'] for r in second])
    def test_same_day_stats_wait_until_all_predictions(self):
        games=[game(1,'2023-09-01T12:00:00Z'),game(2,'2023-09-01T19:00:00Z')]
        advanced=[stats(i,n) for i in [1,2] for n in ['A','B']]
        _,rows=build_rows(games,advanced,.93,'2024-01-01')
        self.assertEqual(rows[0]['profiles'],rows[1]['profiles'])
    def test_strong_opponent_adjustment(self):
        ordinary=EfficiencyState(.93);strong=EfficiencyState(.93)
        opponent=PRIORS[:];opponent[0]-=.2
        ordinary.update('A','offense',PRIORS[:],PRIORS[:]);strong.update('A','offense',PRIORS[:],opponent)
        self.assertGreater(strong.profile('A','offense')[0],ordinary.profile('A','offense')[0])
    def test_missing_data_is_not_zero(self):
        values=raw_values({},30)
        self.assertTrue(all(v is None for v in values))
    def test_zero_ppa_does_not_divide_by_zero(self):
        raw=stats(1,'A')['offense'];raw['passingPlays']['ppa']=0
        self.assertIsNone(raw_values(raw,30)[6])
    def test_regression_does_not_use_evaluation_data(self):
        x=[[i/100] for i in range(200)];y=[2+3*r[0] for r in x]
        model=fit(x,y,0)
        self.assertAlmostEqual(predict_regression(model,[2]),8,places=6)
    def test_pass_mix_changes_efficiency_features(self):
        a=PRIORS[:];b=PRIORS[:];a[6]=.8;b[6]=.2
        self.assertNotEqual(features(a,PRIORS,28,0)[0][3],features(b,PRIORS,28,0)[0][3])
if __name__=='__main__':unittest.main()
