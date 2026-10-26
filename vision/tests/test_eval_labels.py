"""eval_labels CLI on a synthetic dataset + L0 cache (no private media)."""
from pathlib import Path
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import detection_cache
import test_full_frame

_spec=importlib.util.spec_from_file_location('eval_labels',Path(__file__).resolve().parents[2]/'scripts'/'eval_labels.py')
eval_labels=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(eval_labels)


class EvalLabelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)/'labels';self.root=root
        (root/'videos').mkdir(parents=True)
        recorder=detection_cache.Recorder()
        helper=test_full_frame.FullFrameTests();result,_,_=helper.run_mode('off',recorder=recorder)
        rallies=result['rallies'];self.assertTrue(rallies)
        truth=[{'id':'r1','start':rallies[0]['start'],'end':rallies[0]['end']}]
        (root/'videos'/'v.json').write_text(json.dumps({'covered':[[0,5]],'rallies':truth}))
        (root/'dataset.json').write_text(json.dumps({'videos':[{'id':'v','labels':'videos/v.json','file':'v.mp4'}]}))
        cache=root/'cache'/'v'/'abc';recorder.save(cache/'l0.json.gz')
        (cache/'meta.json').write_text(json.dumps({'created':'2026-01-01T00:00:00','verified':True,
                                                   'sources':detection_cache.source_digest()}))
        self.cache=cache

    def tearDown(self):self.tmp.cleanup()

    def run_cli(self,*args):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):eval_labels.main(['--labels',str(self.root),*args])
        return out.getvalue()

    def test_run_scores_replay_saves_baseline_and_gates(self):
        text=self.run_cli('run','--save-baseline','base')
        self.assertIn('1 / 0 / 0',text)
        self.assertTrue((self.root/'baselines'/'base.json').is_file())
        self.assertTrue(list((self.root/'reports').glob('*.md')))
        self.assertIn('退化检查通过',self.run_cli('run','--compare','base','--gate'))
        # A label the rules miss lowers recall: the gate fails against the baseline.
        doc=json.loads((self.root/'videos'/'v.json').read_text())
        doc['rallies'].append({'id':'r2','start':4.0,'end':4.6})
        (self.root/'videos'/'v.json').write_text(json.dumps(doc))
        with self.assertRaises(SystemExit):self.run_cli('run','--compare','base','--gate')

    def test_stale_or_unverified_cache_is_not_used(self):
        meta=json.loads((self.cache/'meta.json').read_text())
        for change in ({'sources':'old'},{'verified':False}):
            (self.cache/'meta.json').write_text(json.dumps({**meta,**change}))
            self.assertIn('没有有效 L0 缓存',self.run_cli('run'))

    def test_import_takes_only_human_rallies_from_a_project(self):
        video=Path(self.tmp.name)/'clip.mp4';video.write_bytes(b'x'*10)
        project=Path(self.tmp.name)/'p.json'
        project.write_text(json.dumps({'video':{'name':'clip.mp4','path':str(video),'duration':60.0,'fingerprint':'f'},
            'rallies':[{'id':'manual-1','start':20,'end':25},{'id':'visual-3','start':30,'end':34,'edited':True},
                       {'id':'visual-4','start':40,'end':44}]}))
        text=self.run_cli('import',str(project),'--id','new','--covered','0-35','--view','side')
        self.assertIn('导入 2 个回合',text)
        doc=json.loads((self.root/'videos'/'new.json').read_text())
        self.assertEqual([r['id'] for r in doc['rallies']],['manual-1','visual-3'])
        self.assertEqual(doc['covered'],[[0.0,35.0]])
        entry=[v for v in json.loads((self.root/'dataset.json').read_text())['videos'] if v['id']=='new'][0]
        self.assertEqual((entry['role'],entry['view']),('dev','side'))
        self.assertTrue((self.root/'sources'/'new-project-manual.json').is_file())
        with self.assertRaises(SystemExit):self.run_cli('import',str(project),'--id','new')   # no silent overwrite


if __name__=='__main__':
    unittest.main()
