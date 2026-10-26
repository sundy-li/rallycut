"""Skill portability, atomic output, provenance and CLI cancellation tests."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'vision'))
import headless
from pretrained import MODEL,WEIGHTS_SHA256
spec=importlib.util.spec_from_file_location('build_skill',REPO/'scripts/build_skill.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def result():
    return {'protocol_version':1,'model':MODEL,
            'rallies':[{'id':'unit-only-1','start':.1,'end':.8,'confidence':.5,'score':20,'selected':True,'edited':False,'evidence':'visual'}],
            'tracks':[{'id':'unit-track','points':[{'t':t,'x':.5+t*.1,'y':.4,'confidence':.9} for t in (.1,.2,.3)]}],
            'summary':{'method':MODEL,'weights_sha256':WEIGHTS_SHA256,'decoded_frames':30,'sampled_frames':30,
                       'track_count':1,'elapsed_seconds':1.0,'table_bounds':[.1,.3,.9,.5],'warnings':['unit-only fixture, not recognition']}}


class CandidateOutputTests(unittest.TestCase):
    def test_compact_has_units_review_provenance_and_no_default_tracks(self):
        output=headless.compact({'duration':1},result())
        self.assertEqual(output['kind'],'rallycut.segments')
        self.assertEqual(output['segments'][0]['start_timecode'],'00:00:00.100')
        self.assertTrue(output['review_required'])
        self.assertNotIn('tracks',output)
        self.assertEqual(len(headless.compact({'duration':1},result(),include_tracks=True)['tracks']),1)
        self.assertEqual(headless.compact({'duration':1},result(),minimum=1)['segments'],[])
        flagged=result();flagged['tracks'][0]['off_play']=True   # display hint survives
        self.assertTrue(headless.compact({'duration':1},flagged,include_tracks=True)['tracks'][0]['off_play'])
        self.assertEqual(headless.timecode(59.9999),'00:01:00.000')

    def test_missing_table_is_legal_and_never_filled_with_full_frame_box(self):
        for bounds in ([],None,'absent'):
            data=result()
            if bounds=='absent':data['summary'].pop('table_bounds')
            else:data['summary']['table_bounds']=bounds
            data['summary']['table_mode']='off'
            data['summary']['geometry_available']=False
            data['summary']['table_segments']=[{'start':0,'end':1,'bounds':[]}]
            headless.validate_result(data,1)
            document=headless.compact({'duration':1},data)
            self.assertEqual(len(document['segments']),1)
            self.assertNotEqual(document['summary'].get('table_bounds'),[0,0,1,1])
            self.assertFalse(document['summary']['geometry_available'])

    def test_rejects_fake_weights_times_flags_and_missing_evidence(self):
        cases=[]
        item=result();item['model']='mock-v1';cases.append(item)
        item=result();item['summary']['weights_sha256']='unknown';cases.append(item)
        item=result();item['rallies'][0]['end']=float('nan');cases.append(item)
        item=result();item['rallies'][0]['end']=2;cases.append(item)
        item=result();item['rallies'][0]['selected']='false';cases.append(item)
        item=result();item['tracks'][0]['points'][0]['t']=-.1;cases.append(item)
        item=result();item['tracks']=[];item['summary']['track_count']=0;cases.append(item)
        item=result();item['tracks'][0]['off_play']='yes';cases.append(item)
        for item in cases:
            with self.subTest(item=item),self.assertRaises(ValueError):
                headless.validate_result(item,1)

    def test_atomic_writer_never_clobbers_and_cleans_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'segments.json'
            output=headless.compact({'duration':1},result())
            with mock.patch('sys.stdout'):
                headless.publish(path,output)
            original=path.read_bytes()
            with self.assertRaises(FileExistsError),mock.patch('sys.stdout'):
                headless.publish(path,output)
            self.assertEqual(path.read_bytes(),original)
            broken=copy.deepcopy(output);broken['bad']=float('nan')
            with self.assertRaises(ValueError):
                headless.publish(Path(directory)/'broken.json',broken)
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()),['segments.json'])
            with self.assertRaises(ValueError):
                headless.output_path(str(path),[str(path)])

    def test_hard_timeout_does_not_publish_json(self):
        if not hasattr(signal,'setitimer'):
            self.skipTest('POSIX timer test')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'timeout.json'
            with mock.patch.object(headless,'analyze',side_effect=lambda args:time.sleep(.3)),mock.patch('sys.stderr'):
                code=headless.main(['analyze','--input','unused.mp4','--output',str(path),'--timeout','.03'])
            self.assertEqual(code,1)
            self.assertFalse(path.exists())

    def test_cancellation_cleans_owned_child(self):
        if not hasattr(signal,'setitimer'):
            self.skipTest('POSIX timer test')
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'pid'
            code='import os,pathlib,time;pathlib.Path('+repr(str(marker))+').write_text(str(os.getpid()));time.sleep(20)'
            with self.assertRaises(subprocess.TimeoutExpired):
                headless.command([sys.executable,'-c',code],headless.Deadline(.3))
            pid=int(marker.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid,0)


class PortableSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='rallycut-skill-test-')
        cls.root=Path(cls.temp.name)
        folder,archive,_=builder.build(cls.root/'build')
        cls.archive=archive
        cls.installed=cls.root/'another agent'/'installed skill'
        shutil.copytree(folder,cls.installed)
        cls.launcher=cls.installed/'scripts/rallycut.py'
        cls.env=os.environ.copy()
        cls.env['RALLYCUT_SKILL_HOME']=str(cls.root/'cache')
        cls.env['RALLYCUT_SKILL_PYTHON']=sys.executable
        cls.env['RALLYCUT_MODEL_PATH']=str(cls.root/'missing.pth')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def invoke(self,*args,env=None):
        return subprocess.run([sys.executable,str(self.launcher),*args],cwd=self.root,
                              env=env or self.env,capture_output=True,text=True,timeout=30)

    def test_archive_self_contained_and_no_weights_or_media(self):
        with zipfile.ZipFile(self.archive) as archive:
            names=archive.namelist()
            self.assertTrue(any(n.endswith('assets/runtime/headless.py') for n in names))
            self.assertTrue(any(n.endswith('vendor/blurball/HRNET-LICENSE') for n in names))
            self.assertFalse(any(Path(n).suffix in ('.pth','.pt','.mp4','.onnx','.pyc') for n in names))
            # Source-only sanity bound: weights / media are MB-scale.
            self.assertLess(sum(item.file_size for item in archive.infolist()),300000)
        self.assertFalse((self.installed/'go.mod').exists())
        self.assertFalse((self.installed/'frontend').exists())

    def test_no_implicit_install_and_tamper_fails_before_execution(self):
        env=self.env.copy();env.pop('RALLYCUT_SKILL_PYTHON')
        run=self.invoke('doctor',env=env)
        self.assertEqual(run.returncode,1,run.stderr)
        self.assertTrue(json.loads(run.stdout)['setup_required'])
        target=self.installed/'assets/runtime/headless.py'
        data=target.read_bytes()
        try:
            target.write_bytes(data+b'\n# unit tamper\n')
            run=self.invoke('doctor')
            self.assertNotEqual(run.returncode,0)
            self.assertIn('checksum mismatch',run.stderr)
        finally:
            target.write_bytes(data)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_from_project_without_torch_or_weights_and_source_verification(self):
        video=self.root/'视频 with spaces.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=1',
                        '-an','-c:v','libx264',str(video)],check=True)
        source=headless.probe(video,headless.Deadline(10))
        data=result()
        project=self.root/'20261024-152433-rallycut.json'
        project.write_text(json.dumps({'schema_version':1,'video':source,'model':MODEL,'manual_timeline':True,
                                       'analysis':data['summary'],'tracks':data['tracks'],'rallies':data['rallies']}))
        output=self.root/'片段.json'
        env=self.env.copy();env.pop('RALLYCUT_SKILL_PYTHON')
        run=self.invoke('from-project','--project',str(project),'--output',str(output),env=env)
        self.assertEqual(run.returncode,0,run.stderr)
        document=json.loads(output.read_text())
        self.assertEqual(document['origin'],'saved_project_timeline')
        self.assertTrue(document['summary']['manual_timeline'])
        self.assertEqual(len(document['segments']),1)
        self.assertEqual(document['source']['fingerprint'],hashlib.sha256(video.read_bytes()).hexdigest())
        self.assertEqual(json.loads(run.stdout)['status'],'completed')
        run=self.invoke('from-project','--project',str(project),'--output',str(output))
        self.assertNotEqual(run.returncode,0)
        self.assertIn('already exists',run.stderr)
        broken=json.loads(project.read_text());broken['video']['fingerprint']='changed'
        project.write_text(json.dumps(broken))
        missing=self.root/'must-not-exist.json'
        run=self.invoke('from-project','--project',str(project),'--output',str(missing))
        self.assertNotEqual(run.returncode,0)
        self.assertIn('fingerprint mismatch',run.stderr)
        self.assertFalse(missing.exists())
        run=self.invoke('analyze','--input',str(video),'--output',str(missing))
        self.assertNotEqual(run.returncode,0)
        self.assertFalse(missing.exists())
        self.assertEqual(run.stdout,'')

    def test_inference_options_are_exposed_and_fail_before_reading_input(self):
        help=self.invoke('analyze','--help')
        for option in ('--precision','--batch-size','--no-pipeline','--table-mode'):
            self.assertIn(option,help.stdout)
        output=self.root/'invalid-inference.json'
        for options in (['--table-mode','required'],['--batch-size','0'],['--batch-size','9'],['--device','cpu','--precision','fp16']):
            run=self.invoke('analyze','--input','missing.mp4','--output',str(output),*options)
            self.assertNotEqual(run.returncode,0)
            self.assertFalse(output.exists())
            self.assertNotIn('No such file',run.stderr)

    def test_calibration_window_is_exposed_and_validated(self):
        help=self.invoke('analyze','--help')
        self.assertEqual(help.returncode,0)
        self.assertIn('--calibration-seconds',help.stdout)
        self.assertIn('--calibration-jump-samples',help.stdout)
        output=self.root/'invalid-calibration.json'
        for value in ('0','-1','nan','inf','3601'):
            with self.subTest(value=value):
                run=self.invoke('analyze','--input','missing.mp4','--output',str(output),'--calibration-seconds',value)
                self.assertNotEqual(run.returncode,0)
                self.assertIn('calibration-seconds',run.stderr)
                self.assertFalse(output.exists())

    def test_late_jump_budget_is_checked_before_reading_input(self):
        output=self.root/'bad-jump.json'
        for value in ('-1','385','1.5'):
            with self.subTest(value=value):
                run=self.invoke('analyze','--input','missing.mp4','--output',str(output),'--calibration-jump-samples',value)
                self.assertNotEqual(run.returncode,0)
                self.assertIn('calibration-jump-samples',run.stderr)
                self.assertFalse(output.exists())
                self.assertNotIn('No such file',run.stderr)

    def test_invalid_timeout_and_missing_model_publish_no_result(self):
        output=self.root/'bad.json'
        run=self.invoke('analyze','--input',str(self.root/'missing.mp4'),'--output',str(output),'--timeout','nan')
        self.assertNotEqual(run.returncode,0)
        self.assertIn('timeout',run.stderr)
        self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()
