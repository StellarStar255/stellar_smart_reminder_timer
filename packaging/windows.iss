; Inno Setup script for StellarPulse.
; Build (after `pyinstaller --noconfirm packaging/stellarpulse.spec`):
;   iscc /DAppVersion=1.0.0 packaging\windows.iss
; The auto-updater runs this installer with /SILENT; [Run] below relaunches
; the app after both silent and interactive installs.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7E4B2C1D-9F3A-4E8B-B6D0-3A55E1C90F42}
AppName=StellarPulse
AppVerName=StellarPulse {#AppVersion}
AppVersion={#AppVersion}
AppPublisher=StellarPulse
DefaultDirName={autopf}\StellarPulse
DefaultGroupName=StellarPulse
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=StellarPulse-{#AppVersion}-Windows-Setup
SetupIconFile=StellarPulse.ico
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
PrivilegesRequired=lowest
WizardStyle=modern

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\StellarPulse\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\StellarPulse"; Filename: "{app}\StellarPulse.exe"
Name: "{autodesktop}\StellarPulse"; Filename: "{app}\StellarPulse.exe"

[Run]
; Relaunch after install — including silent auto-update installs
Filename: "{app}\StellarPulse.exe"; Flags: nowait postinstall
