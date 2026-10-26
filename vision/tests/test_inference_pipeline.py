import sys
from pathlib import Path
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inference_pipeline import run_batches


class InferencePipelineTests(unittest.TestCase):
    def test_order_empty_predictions_tail_and_main_thread_gpu_ownership(self):
        for pipeline in (False,True):
            with self.subTest(pipeline=pipeline):
                main=threading.get_ident();decoded=[];forward_ids=[];consumed=[];closed=[]
                def source():
                    try:
                        for frame in range(25):
                            decoded.append(threading.get_ident());yield frame
                    finally:closed.append(True)
                def forward(frame):
                    forward_ids.append(threading.get_ident());return [] if frame%2 else [frame]
                metrics=run_batches(source(),forward,lambda frame,output:consumed.append((frame,output,threading.get_ident())),pipelined=pipeline)
                self.assertEqual([item[0] for item in consumed],list(range(25)))
                self.assertEqual([item[1] for item in consumed],[[] if n%2 else [n] for n in range(25)])
                self.assertEqual(set(forward_ids),{main})
                self.assertEqual(closed,[True])
                self.assertEqual(metrics['batches'],25)
                self.assertLessEqual(metrics['input_queue_peak'],2)
                self.assertLessEqual(metrics['output_queue_peak'],2)
                if pipeline:
                    self.assertNotIn(main,decoded)
                    self.assertNotIn(main,[item[2] for item in consumed])
                else:self.assertEqual(set(decoded),{main})

    def test_exceptions_stop_all_threads_and_close_source(self):
        for failing in ('producer','forward','consumer','cancel'):
            closed=threading.Event()
            def source():
                try:
                    for index in range(10000):
                        if failing=='producer' and index==2:raise ValueError('producer failed')
                        yield index
                finally:closed.set()
            def forward(value):
                if failing=='forward':raise ValueError('forward failed')
                if failing=='cancel':raise KeyboardInterrupt('cancel')
                return value
            def consume(*_):
                if failing=='consumer':raise ValueError('consumer failed')
            with self.subTest(failing=failing),self.assertRaises(KeyboardInterrupt if failing=='cancel' else ValueError):
                run_batches(source(),forward,consume)
            self.assertTrue(closed.is_set())
            self.assertFalse(any(t.name in ('rallycut-decode','rallycut-postprocess') for t in threading.enumerate()))

    def test_iter_creation_failure_propagates_instead_of_hanging(self):
        class Bad:
            def __iter__(self):raise RuntimeError('broken iterator')
        with self.assertRaisesRegex(RuntimeError,'broken iterator'):
            run_batches(Bad(),lambda x:x,lambda *_:None)

    def test_empty_source_and_invalid_queue_depth(self):
        for mode in (True,False):
            self.assertEqual(run_batches(iter([]),lambda x:x,lambda *_:None,pipelined=mode)['batches'],0)
        for invalid in (0,5,True):
            with self.assertRaises(ValueError):run_batches([],lambda x:x,lambda *_:None,queue_depth=invalid)


if __name__=='__main__':unittest.main()
