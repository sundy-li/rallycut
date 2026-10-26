from pathlib import Path
import sys
import os
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from table_jump import anchors,neighbors,search_later,JumpSearchExhausted,validate_jump_budget
from table_locator import stable_table,calibrate,SeekUnavailable
from test_table_locator import CalibrationCapture,item
import cv2

MAIN=(315,214,706,298)


def consensus(samples):return stable_table(samples)


class TableJumpTests(unittest.TestCase):
    def test_dyadic_order_and_tail_neighbors_have_three_distinct_times(self):
        points=list(anchors(600,1500))
        self.assertEqual(points[0],602)
        self.assertAlmostEqual(points[1],1049.875)
        self.assertAlmostEqual(points[2],1499.75)
        self.assertTrue(points[3]<points[1]<points[4])
        self.assertEqual(len(points),len(set(points)))
        self.assertLessEqual(len(points),32)
        for point in points:
            local=neighbors(point,600,1500)
            self.assertEqual(len(local),3)
            self.assertTrue(all(600<t<1500 for t in local))
        self.assertEqual(list(anchors(600,600)),[])
        self.assertEqual(neighbors(601,600,601),[])
        self.assertEqual(len(list(anchors(600,1e9))),32)
        huge=list(anchors(1e308,1.1e308))
        self.assertLessEqual(len(huge),32)
        self.assertTrue(all(1e308<t<=1.1e308 for t in huge))

    def test_local_three_point_consensus_finds_late_table_and_stops(self):
        requests=[]
        def read(t):
            requests.append(t)
            return t,[item(MAIN)] if 1040<t<1060 else [],[]
        found,_=search_later(600,1500,96,read,consensus,lambda *_:None)
        self.assertEqual(found['jump_windows'],2)
        self.assertEqual(found['jump_samples'],6)
        self.assertTrue(1040<found['first_evidence']<found['last_evidence']<1060)
        self.assertEqual(len(requests),6)

    def test_refinement_can_confirm_a_candidate_missed_in_one_base_frame(self):
        seen=[]
        def read(t):
            seen.append(t)
            return t,[item(MAIN)] if t in (602,603,604) else [],[]
        found,_=search_later(600,1500,96,read,consensus,lambda *_:None)
        self.assertEqual(found['observations'],3)
        self.assertEqual(found['jump_samples'],5)
        self.assertEqual(len(seen),len(set(seen)))

    def test_no_cross_minute_voting_duplicate_pts_or_single_hit_acceptance(self):
        centers=list(anchors(600,1500))
        def isolated(t):return t,[item(MAIN)] if any(abs(t-c)<.01 for c in centers) else [],[]
        with self.assertRaises(JumpSearchExhausted):
            search_later(600,1500,96,isolated,consensus,lambda *_:None)
        with self.assertRaises(JumpSearchExhausted):
            search_later(600,1500,12,lambda t:(601,[item(MAIN)],[]),consensus,lambda *_:None)

    def test_sample_wall_budgets_and_cancellation_stop_without_false_result(self):
        reads=[]
        with self.assertRaises(JumpSearchExhausted) as error:
            search_later(600,1500,7,lambda t:(reads.append(t) or t,[],[]),consensus,lambda *_:None)
        self.assertLessEqual(len(reads),7)
        self.assertEqual(error.exception.reason,'sample_budget')
        clock=iter([0,61])
        with self.assertRaises(JumpSearchExhausted) as error:
            search_later(600,1500,96,lambda t:self.fail('read after budget'),consensus,lambda *_:None,clock=lambda:next(clock))
        self.assertEqual(error.exception.reason,'time_budget')
        def cancel(t):raise InterruptedError('user cancelled')
        with self.assertRaises(InterruptedError):search_later(600,1500,96,cancel,consensus,lambda *_:None)
        for value in (-1,385,True,1.5,float('nan')):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_jump_budget(value)

    def test_ambiguity_is_not_resolved_by_arbitrarily_choosing_another_table(self):
        with self.assertRaises(JumpSearchExhausted):
            search_later(600,1500,12,lambda t:(t,[item((70,210,400,280)),item((550,210,880,280))],[]),consensus,lambda *_:None)

    def test_calibrate_integrates_initial_failure_with_late_window(self):
        first=CalibrationCapture();late=CalibrationCapture()
        def candidates(_):
            return [item(MAIN)] if late.seeks and 1040<late.position<1060 else []
        with mock.patch.object(cv2,'VideoCapture',side_effect=[first,late]),mock.patch('table_locator.candidates',side_effect=candidates):
            found=calibrate('fixture',1500,lambda *_:None)
        self.assertEqual(len(first.seeks),145)
        self.assertEqual(found['strategy'],'seek_sparse_then_jump')
        self.assertEqual(found['search_seconds'],600)
        self.assertEqual(found['jump_samples'],6)
        self.assertEqual(found['sampled_frames'],151)
        self.assertGreater(found['last_evidence'],600)
        self.assertTrue(first.closed and late.closed)

    def test_late_seek_failure_never_falls_back_to_full_sequential_scan(self):
        first=CalibrationCapture();late=CalibrationCapture(seek_supported=False)
        with mock.patch.object(cv2,'VideoCapture',side_effect=[first,late]) as opening,mock.patch('table_locator.candidates',return_value=[]),self.assertRaisesRegex(ValueError,'不顺扫整片'):
            calibrate('fixture',1500,lambda *_:None)
        self.assertEqual(opening.call_count,2)
        self.assertTrue(first.closed and late.closed)

    @unittest.skipUnless(os.getenv('RALLYCUT_JUMP_SYNTHETIC_VIDEO'),'explicit delayed-table synthetic media')
    def test_real_decoder_delayed_table_media(self):
        found=calibrate(os.environ['RALLYCUT_JUMP_SYNTHETIC_VIDEO'],900,lambda *_:None)
        self.assertEqual(found['strategy'],'seek_sparse_then_jump')
        self.assertTrue(700<=found['first_evidence']<found['last_evidence']<720)
        self.assertLessEqual(found['jump_samples'],96)
        self.assertGreater(found['sampled_frames'],145)

    def test_late_progress_exception_releases_decoder(self):
        first=CalibrationCapture();late=CalibrationCapture()
        def progress(_,message):
            if message.startswith('后段跳搜'):raise InterruptedError('cancelled')
        with mock.patch.object(cv2,'VideoCapture',side_effect=[first,late]),mock.patch('table_locator.candidates',return_value=[]),self.assertRaises(InterruptedError):
            calibrate('fixture',1500,progress)
        self.assertTrue(first.closed and late.closed)


if __name__=='__main__':unittest.main()
