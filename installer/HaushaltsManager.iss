; Inno Setup script for HaushaltsManager (onedir build -> per-user installer).
; Build:  ISCC.exe /DMyAppVersion=1.0.4 installer\HaushaltsManager.iss
;
; Per-user install (no admin/UAC) so the in-app updater can run the installer
; silently and replace the program files without elevation. The app's data
; (%APPDATA%\HaushaltsManager) is never touched by install/uninstall.

#define MyAppName "HaushaltsManager"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppExe "HaushaltsManager.exe"
#define MyAppPublisher "Mijonex"

[Setup]
AppId={{8F3A1C42-9E7B-4D52-A6F1-2C4B8E0D7A93}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
WizardStyle=modern
; Per-user install: no admin rights needed (lets silent auto-update work).
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=HaushaltsManager-Setup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
; Close the running app (Restart Manager) before replacing files during update.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole PyInstaller onedir folder (exe + _internal/) ships as-is.
Source: "..\dist\HaushaltsManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
; Relaunch after install. No 'skipifsilent', so a silent auto-update also
; relaunches the freshly updated app.
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall
