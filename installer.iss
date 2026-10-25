; ============================================================================
; Inno Setup Script for pivitLABS ÖTSV Tool (Windows Native Installer)
; Creates: release/pivitLABS-OETSV-Tool-Windows-Setup.exe
; ============================================================================

#define MyAppName "pivitLABS ÖTSV Tool"
#define MyAppVersion "1.5.0"
#define MyAppPublisher "pivitlabs"
#define MyAppURL "https://pivitlabs.com"
#define MyAppExeName "pivitLABS OETSV Tool.exe"

[Setup]
AppId={{8D4F69C2-53A1-4B9E-8F19-6A2E30C47F11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\pivitLABS OETSV Tool
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=release
OutputBaseFilename=pivitLABS-OETSV-Tool-Windows-Setup
SetupIconFile=app\static\img\app-icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "dist\pivitLABS OETSV Tool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
