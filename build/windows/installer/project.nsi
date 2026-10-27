; Based on the Wails v2 NSIS project template (MIT).
; Own this file, not generated wails_tools.nsh. The default Wails x64-only
; architecture/file macros reject native ARM64, so both checks and payload
; selection below intentionally allow x64 emulation on Windows 11 ARM.
Unicode true

!define INFO_PROJECTNAME "RallyCut"
!define INFO_COMPANYNAME "RallyCut"
!define INFO_PRODUCTNAME "RallyCut"
!define INFO_PRODUCTVERSION "0.1.0"
!ifndef REQUEST_EXECUTION_LEVEL
  !define REQUEST_EXECUTION_LEVEL "user"
!endif
!ifndef WAILS_INSTALL_SCOPE
  !define WAILS_INSTALL_SCOPE "user"
!endif
!define WAILS_INSTALL_WEBVIEW_DETAILPRINT "正在准备 Microsoft WebView2 窗口运行环境…"
!include "wails_tools.nsh"

!ifndef ARG_WAILS_AMD64_BINARY
  !error "This installer requires the x64 application payload"
!endif

VIProductVersion "${INFO_PRODUCTVERSION}.0"
VIFileVersion "${INFO_PRODUCTVERSION}.0"
VIAddVersionKey /LANG=2052 "CompanyName" "${INFO_COMPANYNAME}"
VIAddVersionKey /LANG=2052 "FileDescription" "RallyCut Windows x64 测试版安装器"
VIAddVersionKey /LANG=2052 "ProductVersion" "${INFO_PRODUCTVERSION}"
VIAddVersionKey /LANG=2052 "ProductName" "${INFO_PRODUCTNAME}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "${INFO_COPYRIGHT}"
ManifestDPIAware true

!include "MUI.nsh"
!define MUI_ICON "..\icon.ico"
!define MUI_UNICON "..\icon.ico"
!define MUI_FINISHPAGE_NOAUTOCLOSE
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "安装 RallyCut 测试版"
!define MUI_WELCOMEPAGE_TEXT "此包为 Windows x64 版，也可在 Windows 11 ARM 中测试 x64 模拟运行，不是原生 ARM64 版。$\r$\n$\r$\n首次打开后，先检测环境；点击准备按钮后才下载 Python、视频工具、分析依赖与模型。建议预留至少 5 GB 空间，并保持网络可用。"
!define MUI_FINISHPAGE_TEXT "安装完成。请从桌面或开始菜单打开 RallyCut，完成首次环境准备。$\r$\n$\r$\nWindows ARM 上的运行速度和推理库兼容性仍需实测，不代表普通 x64 电脑的性能。"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Name "RallyCut 测试版"
OutFile "..\..\bin\${INFO_PROJECTNAME}-${ARCH}-installer.exe"
InstallDir "$LOCALAPPDATA\Programs\RallyCut"
ShowInstDetails show

Function .onInit
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_OK "需要 Windows 10 或更新的 x64 系统，或支持 x64 模拟的 Windows 11 ARM。"
    Quit
  ${EndIf}
  ${If} ${IsNativeAMD64}
    Goto supported
  ${EndIf}
  ${If} ${IsNativeARM64}
    ; Windows 11 begins at build 22000. Accepting ARM does not assert that
    ; every third-party x64 inference library will work under emulation.
    SetRegView 64
    ReadRegStr $0 HKLM "SOFTWARE\Microsoft\Windows NT\CurrentVersion" "CurrentBuildNumber"
    ${If} $0 >= 22000
      IfSilent supported 0
      MessageBox MB_OKCANCEL "检测到 Windows ARM。将安装 x64 模拟测试版，不是原生 ARM64 版；分析依赖和显卡加速可能不兼容。是否继续？" IDOK supported
      Quit
    ${EndIf}
  ${EndIf}
  MessageBox MB_OK "当前架构不受支持。需要 Windows x64，或 Windows 11 ARM 的 x64 模拟环境。"
  SetErrorLevel 65
  Quit
  supported:
FunctionEnd

Section "安装 RallyCut"
  !insertmacro wails.setShellContext
  !insertmacro wails.webview2runtime
  SetOutPath $INSTDIR
  ; Do not call wails.files: it selects no x64 payload on an ARM64 host.
  File "/oname=${PRODUCT_EXECUTABLE}" "${ARG_WAILS_AMD64_BINARY}"
  !if /FileExists "runtime-payload.zip"
    File "/oname=runtime-payload.zip" "runtime-payload.zip"
  !endif
  CreateShortcut "$SMPROGRAMS\RallyCut.lnk" "$INSTDIR\${PRODUCT_EXECUTABLE}"
  CreateShortcut "$DESKTOP\RallyCut.lnk" "$INSTDIR\${PRODUCT_EXECUTABLE}"
  !insertmacro wails.associateFiles
  !insertmacro wails.associateCustomProtocols
  !insertmacro wails.writeUninstaller
SectionEnd

Section "uninstall"
  !insertmacro wails.setShellContext
  Delete "$INSTDIR\${PRODUCT_EXECUTABLE}"
  Delete "$INSTDIR\runtime-payload.zip"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\RallyCut.lnk"
  Delete "$DESKTOP\RallyCut.lnk"
  !insertmacro wails.unassociateFiles
  !insertmacro wails.unassociateCustomProtocols
  !insertmacro wails.deleteUninstaller
  ; Preserve projects, downloaded environments and models in AppData.
SectionEnd
