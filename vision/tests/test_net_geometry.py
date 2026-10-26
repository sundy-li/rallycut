from pathlib import Path
import sys
import unittest
import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from net_geometry import side_net_region


class NetGeometryTests(unittest.TestCase):
    def test_two_supported_posts_and_perspective_shape(self):
        frame=np.full((540,960,3),180,dtype='uint8')
        cv2.rectangle(frame,(430,192),(438,222),(15,15,15),-1)
        cv2.rectangle(frame,(632,201),(642,246),(15,15,15),-1)
        region=side_net_region(frame,(180,198,814,265),'side-color-rim')
        self.assertEqual(len(region),6)
        self.assertTrue(.44<region[0]<.47 and .65<region[3]<.68,region)
        self.assertLess(region[1],region[2]);self.assertLess(region[4],region[5])

    def test_no_posts_one_post_and_untrusted_view_disable_net_rule(self):
        frame=np.full((540,960,3),180,dtype='uint8');bounds=(180,198,814,265)
        self.assertEqual(side_net_region(frame,bounds,'side-color-rim'),[])
        cv2.rectangle(frame,(632,201),(642,246),(15,15,15),-1)
        self.assertEqual(side_net_region(frame,bounds,'side-color-rim'),[])
        self.assertEqual(side_net_region(frame,bounds,'perspective-rims'),[])


if __name__=='__main__':unittest.main()
