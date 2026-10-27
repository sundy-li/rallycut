"""Keep filenames out of shell/code-page stdout protocols."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]

class NativePickerContract(unittest.TestCase):
 def test_video_picker_is_framework_native_not_a_shell(self):
  source=(ROOT/'backend/media/picker.go').read_text()
  self.assertIn('wruntime.OpenMultipleFilesDialog',source)
  for fragile in ['"powershell"','"osascript"','"zenity"','strings.TrimSpace','strings.Split','childproc.','exec.']:
   self.assertNotIn(fragile,source)
  self.assertIn('([]string, error)',source)

if __name__=='__main__':unittest.main()
