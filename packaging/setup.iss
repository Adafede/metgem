; Script generated by the Inno Script Studio Wizard.
; SEE THE DOCUMENTATION FOR DETAILS ON CREATING INNO SETUP SCRIPT FILES!

#define AppName "MetGem"
#define AppVersion "1.2.0"
#define AppPublisher "CNRS/ICSN"
#define AppURL "https://metgem.github.io"
#define AppExeName "MetGem.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{15225AA3-EFDB-4261-A26D-138260F4B3D2}
AppName={#AppName}
AppVersion={#AppVersion}
;AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={pf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputBaseFilename=setup_{#AppName}
Compression=lzma
SolidCompression=yes
OutputDir=.
SetupIconFile=main.ico
WizardImageFile=compiler:WizModernImage-IS.bmp
WizardSmallImageFile=compiler:WizModernSmallImage-IS.bmp
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
ChangesAssociations=True
LicenseFile=dist\MetGem\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\MetGem\MetGem.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\MetGem\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCR; SubKey: ".mnz"; ValueType: string; ValueData: "Molecular Network"; Flags: uninsdeletekey
Root: HKCR; SubKey: "Molecular Network"; ValueType: string; ValueData: "Molecular Network"; Flags: uninsdeletekey
Root: HKCR; SubKey: "Molecular Network\Shell\Open\Command"; ValueType: string; ValueData: """{app}\MetGem.exe"" ""%1"""; Flags: uninsdeletekey
Root: HKCR; Subkey: "Molecular Network\DefaultIcon"; ValueType: string; ValueData: "{app}\MetGem.exe,0"; Flags: uninsdeletevalue
