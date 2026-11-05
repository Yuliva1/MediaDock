#define AppName "MediaDock"
#define AppVersion "1.0.6"
#define AppExe "MediaDock.exe"

[Setup]
AppId={{B7E4C2A1-5D3F-4E8A-9C61-2F0A7D9E4B13}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Yuliva
AppPublisherURL=https://github.com/Yuliva1/MediaDock
AppSupportURL=https://github.com/Yuliva1/MediaDock
AppUpdatesURL=https://github.com/Yuliva1/MediaDock/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=MediaDock-Setup
SetupIconFile=assets\icons\mediadock.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
VersionInfoCompany=Yuliva
VersionInfoDescription=MediaDock - Universal Media Downloader
VersionInfoVersion={#AppVersion}
VersionInfoCopyright=Copyright (C) 2026 Yuliva
VersionInfoProductName=MediaDock
VersionInfoProductVersion={#AppVersion}

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\MediaDock\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
