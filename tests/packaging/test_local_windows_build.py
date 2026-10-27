"""Contracts for clean-checkout local Windows builds."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]

class LocalWindowsBuildContract(unittest.TestCase):
 def test_builds_frontend_and_native_resources(self):
  source=(ROOT/'scripts/build-windows.ps1').read_text(encoding='utf-8-sig')
  self.assertIn('& npm --prefix frontend ci',source)
  self.assertIn('& $Wails build -platform windows/amd64',source)
  self.assertNotIn('& $Go build',source)
  self.assertIn("frontend/dist/index.html",source)
  self.assertIn("frontend/dist/assets",source)
  self.assertIn('-compiler $Go',source)
  self.assertIn('$env:PATH = $originalPath',source)

if __name__=='__main__':unittest.main()
