; The Windows installer for dist\Luikki (ROADMAP B4). Build the app first
; (luikki.spec, which also draws build\luikki.ico), then:
;
;     "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" packaging\luikki.iss
;
; Out: dist\installer\Luikki-<version>-setup.exe. Unsigned while testing: the
; tester clicks "More info -> Run anyway" once.
;
; Installed for the current user, without asking for administrator rights, in
; %LOCALAPPDATA%\Programs\Luikki. The artist's project is not in there: it lives
; in %LOCALAPPDATA%\Luikki, and uninstalling leaves it alone.

#ifndef AppVersion
  #define AppVersion "0.3.1"
#endif

[Setup]
; Never change: it is how an update finds the copy it replaces.
AppId={{6F1C2A94-3B7D-4E58-9A21-C47D0E8B5F13}
AppName=Luikki
AppVersion={#AppVersion}
AppPublisher=Luikki
DefaultDirName={autopf}\Luikki
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=Luikki-{#AppVersion}-setup
SetupIconFile=..\build\luikki.ico
UninstallDisplayIcon={app}\Luikki.exe
WizardStyle=modern
; The models are most of the size and do not compress much.
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
fr.NoWebView2=Luikki s'affiche avec Microsoft Edge WebView2, qui n'est pas installé sur cet ordinateur.%n%nInstallez-le depuis https://developer.microsoft.com/microsoft-edge/webview2/ (« Evergreen Bootstrapper »), puis lancez Luikki.
en.NoWebView2=Luikki is displayed with Microsoft Edge WebView2, which is not installed on this computer.%n%nInstall it from https://developer.microsoft.com/microsoft-edge/webview2/ ("Evergreen Bootstrapper"), then start Luikki.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Luikki\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; An update replaces the whole bundle: a library left over from the previous
; version would be loaded next to its replacement.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Luikki"; Filename: "{app}\Luikki.exe"
Name: "{autodesktop}\Luikki"; Filename: "{app}\Luikki.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Luikki.exe"; Description: "{cm:LaunchProgram,Luikki}"; Flags: nowait postinstall skipifsilent
; An update pressed in the app runs silently, and the app closed for it
; (`web/update.py`): open it again.
Filename: "{app}\Luikki.exe"; Flags: nowait; Check: WizardSilent

[Code]
// WebView2 comes with Windows 11 and, through Windows Update, with most of
// Windows 10. Where it is missing the window would open blank, so say so.
function HasWebView2(): Boolean;
var
  Version: String;
begin
  Result :=
    (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'))
    or (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and not HasWebView2() and not WizardSilent() then
    MsgBox(ExpandConstant('{cm:NoWebView2}'), mbInformation, MB_OK);
end;
