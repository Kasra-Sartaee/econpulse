; Windows installer for EconPulse (Inno Setup 6). Built by tools/build_windows.py --installer,
; which passes the version:  ISCC /DAppVersion=3.4.0 installer\EconPulse.iss
;
; Installs per user by default (no administrator rights, no UAC prompt), so the in-app
; updater can replace it in place. The user's settings and notes in %APPDATA%\EconPulse
; are never touched by installing, updating or uninstalling.

#ifndef AppVersion
  #error Pass the version: ISCC /DAppVersion=x.y.z installer\EconPulse.iss
#endif

[Setup]
AppId={{5E7A3D2C-8B41-4C6F-9D2E-EC0F0B9A3401}
AppName=EconPulse
AppVersion={#AppVersion}
AppVerName=EconPulse {#AppVersion}
AppPublisher=Aref Hosseini and Kasra Sartaee
AppCopyright=Copyright (c) 2026 Aref Hosseini, Kasra Sartaee and EconPulse contributors
AppPublisherURL=https://github.com/Kasra-Sartaee/econpulse
AppSupportURL=https://github.com/Kasra-Sartaee/econpulse/issues
AppUpdatesURL=https://github.com/Kasra-Sartaee/econpulse/releases
VersionInfoVersion={#AppVersion}
VersionInfoDescription=EconPulse economic calendar setup
DefaultDirName={autopf}\EconPulse
DefaultGroupName=EconPulse
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=EconPulse-{#AppVersion}-Setup
SetupIconFile=..\econpulse\assets\econpulse.ico
UninstallDisplayIcon={app}\EconPulse.exe
UninstallDisplayName=EconPulse
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\EconPulse\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; An update replaces the bundled libraries completely, so no stale file from an older version lingers.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\EconPulse"; Filename: "{app}\EconPulse.exe"
Name: "{autodesktop}\EconPulse"; Filename: "{app}\EconPulse.exe"; Tasks: desktopicon

[Registry]
; Start-at-login is set from the app's own Settings; remove it when EconPulse is uninstalled.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "EconPulse"; Flags: uninsdeletevalue dontcreatekey

[Run]
; Interactive install: offer to start the app. Silent install (the in-app updater): start it again.
Filename: "{app}\EconPulse.exe"; Description: "{cm:LaunchProgram,EconPulse}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\EconPulse.exe"; Flags: nowait; Check: WizardSilent
