; Dönüştürücü — Windows kurulum sihirbazı (Inno Setup 6)
#define AppVer GetEnv("APP_VERSION")
#if AppVer == ""
  #define AppVer "1.0.0"
#endif

[Setup]
AppId={{8C3E2A51-6F0D-4B7E-9A51-2D7C9E1F4A10}
AppName=Dönüştürücü
AppVersion={#AppVer}
AppPublisher=Dönüştürücü
DefaultDirName={localappdata}\Programs\Donusturucu
DefaultGroupName=Dönüştürücü
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=DonusturucuKurulum
SetupIconFile=..\donusturucu\static\icon.ico
UninstallDisplayIcon={app}\Donusturucu.exe
UninstallDisplayName=Dönüştürücü
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Kısayollar:"

[Files]
Source: "..\dist\Donusturucu\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Dönüştürücü"; Filename: "{app}\Donusturucu.exe"
Name: "{autodesktop}\Dönüştürücü"; Filename: "{app}\Donusturucu.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Donusturucu.exe"; Description: "Dönüştürücü'yü şimdi aç"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
