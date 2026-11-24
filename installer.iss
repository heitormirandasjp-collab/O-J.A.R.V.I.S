; ═══════════════════════════════════════════════════════════════
; JARVIS — Command Center
; Installer: Inno Setup 6
; Gera: dist-installer/JARVIS-Setup.exe
; ═══════════════════════════════════════════════════════════════
#define MyAppName "JARVIS"
#define MyAppVersion "1.0.25"
#define MyAppPublisher "Comandante"
#define MyAppURL "https://github.com/openjarvis"
#define MyAppExeName "JARVIS.exe"

; Pasta com o resultado do PyInstaller. Permite build paralelo sem tocar em
; dist\ (que fica travada quando o JARVIS está aberto):
;   ISCC.exe /DSourceDir=.build\dist installer.iss
#ifndef SourceDir
  #define SourceDir "dist"
#endif

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
SetupIconFile=assets\jarvis.ico
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
Source: "{#SourceDir}\JARVIS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\jarvis-settings.json"
Type: filesandordirs; Name: "{localappdata}\jarvis-events.json"