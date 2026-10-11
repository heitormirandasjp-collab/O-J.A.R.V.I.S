; ═══════════════════════════════════════════════════════════════
; JARVIS — Command Center
; Installer: Inno Setup 6
; Gera: dist-installer/JARVIS-Setup.exe
; ═══════════════════════════════════════════════════════════════
#define MyAppName "JARVIS"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Comandante"
#define MyAppURL "https://github.com/openjarvis"
#define MyAppExeName "JARVIS.exe"

[Setup]
AppId={{B8F3A9C4-5D2E-4DA1-9F67-3A1C8E2D5B00}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist-installer
OutputBaseFilename=JARVIS-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "portugues"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "English"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; ── JARVIS (backend + interface + voz) ──────────────────────────
; O JARVIS.exe (PyInstaller) já carrega tudo: backend, UI, Piper, onnxruntime.
; Copia a pasta inteira dist/JARVIS/ (inclui _internal e todas as dependências).
Source: "dist\JARVIS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\jarvis-settings.json"
Type: filesandordirs; Name: "{localappdata}\jarvis-events.json"