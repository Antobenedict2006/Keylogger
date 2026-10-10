[Setup]
AppName=AI Keylogger Detection System
AppVersion=2.5
AppPublisher=KeyGuard AI
DefaultDirName={autopf}\KeyloggerDetector
DefaultGroupName=KeyGuard AI
OutputDir=..\installer_output
OutputBaseFilename=KeyloggerDetector_Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
WizardStyle=modern
LicenseFile=LICENSE.txt
UninstallDisplayIcon={app}\KeyloggerDetector.exe
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\KeyloggerDetector.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\AI Keylogger Detection System"; Filename: "{app}\KeyloggerDetector.exe"
Name: "{group}\Uninstall AI Keylogger Detection System"; Filename: "{uninstallexe}"
Name: "{autodesktop}\AI Keylogger Detection System"; Filename: "{app}\KeyloggerDetector.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KeyloggerDetector.exe"; Description: "Launch AI Keylogger Detection System now"; Flags: nowait postinstall skipifsilent unchecked
