import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from model import Model, run, probability, validate

def game(id,date,hp,ap,season=2025):
    return dict(id=id,season=season,startDate=date,homeTeam='A',awayTeam='B',homePoints=hp,awayPoints=ap,completed=True,homeClassification='fbs',awayClassification='fbs',neutralSite=False)
class Safeguards(unittest.TestCase):
    def test_no_future_outcomes_leak(self):
        first=game(1,'2025-09-01T12:00:00Z',40,10)
        second=game(2,'2025-09-08T12:00:00Z',10,50)
        _,rows=run([first,second],'2026-01-01')
        second['homePoints']=99
        _,changed=run([first,second],'2026-01-01')
        self.assertEqual([r['margin'] for r in rows],[r['margin'] for r in changed])
    def test_same_day_batched(self):
        _,r=run([game(1,'2025-09-01T12:00:00Z',40,10),game(2,'2025-09-01T18:00:00Z',20,10)],'2026-01-01')
        self.assertEqual(r[0]['margin'],r[1]['margin'])
    def test_home_and_neutral(self):
        m=Model();h,a=m.predict('A','B');self.assertEqual(h-a,3)
        h,a=m.predict('A','B',True);self.assertEqual(h,a)
    def test_probability_symmetry(self):
        for x in [-100,-10,0,10,100]:self.assertAlmostEqual(probability(x,10)+probability(-x,10),1)
    def test_unfinished_and_future_excluded(self):
        g=game(1,'2025-09-01',40,10);g['completed']=False
        _,r=run([g,game(2,'2027-01-01',99,0)],'2026-01-01');self.assertEqual(r,[])
    def test_insufficient_history_cannot_pass(self):
        self.assertEqual(validate([],2026)['status'],'insufficient_history')
    def test_calibration_excludes_holdout(self):
        rows=[dict(year=y,margin=10,home=30,away=20,hp=30,ap=20,y=i%2,baselineH=29.5,baselineA=26.5) for y in [2024,2025] for i in range(220)]
        a=validate(rows,2026)
        for r in rows:
            if r['year']==2025:r['y']=1
        b=validate(rows,2026)
        self.assertEqual(a['scale'],b['scale'])
if __name__=='__main__':unittest.main()
