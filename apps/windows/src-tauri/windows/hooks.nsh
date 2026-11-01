!define PL_HOOK_DIR "${__FILEDIR__}"
!macro NSIS_HOOK_PREINSTALL
  ; A privileged service must never run from a user-writable custom directory.
  ${If} $INSTDIR != "$PROGRAMFILES64\PrettyLisaVPN"
    MessageBox MB_ICONSTOP "PrettyLisaVPN must be installed in $PROGRAMFILES64\PrettyLisaVPN." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  InitPluginsDir
  File /oname=$PLUGINSDIR\installer-service.ps1 "${PL_HOOK_DIR}\installer-service.ps1"
  ${DisableX64FSRedirection}
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\installer-service.ps1" -Action prepare'
  ${EnableX64FSRedirection}
  Pop $0
  Pop $1
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "PrettyLisaVPN could not prepare its VPN service. Installation stopped." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTINSTALL
  CopyFiles /SILENT "$PLUGINSDIR\installer-service.ps1" "$INSTDIR\installer-service.ps1"
  ExecWait '"$INSTDIR\prettylisavpn-windows.exe" --install-service' $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "PrettyLisaVPN could not start its VPN service. Please run the installer again." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  ${DisableX64FSRedirection}
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\installer-service.ps1" -Action remove'
  ${EnableX64FSRedirection}
  Pop $0
  Pop $1
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "PrettyLisaVPN could not stop its VPN service. Uninstallation stopped." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  Delete "$INSTDIR\installer-service.ps1"
  RMDir "$INSTDIR"
!macroend
