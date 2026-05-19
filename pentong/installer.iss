; 뚝딱비서 — Inno Setup 설치 스크립트
; Inno Setup 6.x 이상 필요

[Setup]
AppName=뚝딱비서
AppVersion=1.0.0
AppPublisher=뚝딱비서
DefaultDirName={autopf}\뚝딱비서
DefaultGroupName=뚝딱비서
OutputDir=installer_output
OutputBaseFilename=뚝딱비서_Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupIconFile=
LicenseFile=
InfoBeforeFile=installer_readme.txt

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\뚝딱비서.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Dirs]
Name: "{app}\templates"

[Icons]
Name: "{group}\뚝딱비서"; Filename: "{app}\뚝딱비서.exe"
Name: "{group}\뚝딱비서 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\뚝딱비서"; Filename: "{app}\뚝딱비서.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 생성"; GroupDescription: "추가 옵션:"; Flags: checked

[Run]
Filename: "{app}\뚝딱비서.exe"; Description: "뚝딱비서 실행"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
var
  HwpPath: String;
  Msg: String;
begin
  Result := True;
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SOFTWARE\HNC\HWP', 'InstallPath', HwpPath) then
  begin
    if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
      'SOFTWARE\WOW6432Node\HNC\Hwp', 'InstallPath', HwpPath) then
    begin
      Msg := '뚝딱비서를 사용하려면 한컴 한글 프로그램이 필요합니다.' + #13#10 +
             #13#10 +
             '한글이 설치되어 있지 않은 것 같습니다.' + #13#10 +
             '한글 없이도 엑셀 기능은 사용할 수 있습니다.' + #13#10 +
             #13#10 +
             '계속 설치하시겠습니까?';
      Result := (MsgBox(Msg, mbConfirmation, MB_YESNO) = IDYES);
    end;
  end;
end;
