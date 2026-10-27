"""Contract checks for the maintained NSIS source, not an ARM execution test."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class WindowsInstallerTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / 'build/windows/installer/project.nsi').read_text(encoding='utf-8-sig')

    def test_x64_payload_is_not_filtered_out_on_arm(self):
        self.assertIn('${IsNativeAMD64}', self.source)
        self.assertIn('${IsNativeARM64}', self.source)
        self.assertIn('${If} $0 >= 22000', self.source)
        self.assertNotIn('!insertmacro wails.checkArchitecture', self.source)
        self.assertNotIn('!insertmacro wails.files', self.source)
        self.assertIn('File "/oname=${PRODUCT_EXECUTABLE}" "${ARG_WAILS_AMD64_BINARY}"', self.source)

    def test_chinese_user_scope_and_no_project_deletion(self):
        self.assertIn('!insertmacro MUI_LANGUAGE "SimpChinese"', self.source)
        self.assertIn('!define WAILS_INSTALL_SCOPE "user"', self.source)
        self.assertIn('不是原生 ARM64 版', self.source)
        self.assertNotIn('RMDir /r "$APPDATA', self.source)
        self.assertNotIn('RMDir /r "$LOCALAPPDATA', self.source)
        self.assertIn('RMDir /r "$INSTDIR\\runtimes\\${RALLYCUT_RUNTIME_ID}"', self.source)
        self.assertIn('!insertmacro wails.webview2runtime', self.source)

    def test_expanded_runtime_is_installed_before_executable(self):
        self.assertIn('SetCompressor /SOLID lzma', self.source)
        self.assertIn('runtime-layout.nsh', self.source)
        self.assertIn('File /r /x bundle-manifest.json', self.source)
        self.assertLess(self.source.index('File /r /x bundle-manifest.json'), self.source.index('File "/oname=${PRODUCT_EXECUTABLE}"'))
        self.assertNotIn('File "/oname=runtime-payload.zip"', self.source)

    def test_generated_tools_are_not_committed(self):
        ignore = (ROOT / '.gitignore').read_text()
        self.assertIn('build/windows/installer/*', ignore)
        self.assertIn('!build/windows/installer/project.nsi', ignore)


if __name__ == '__main__':
    unittest.main()
