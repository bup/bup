Name "Bupdate NSIS Example"
OutFile "nsis-example-new.exe"
;SilentInstall silent

InstallDir "$PROGRAMFILES\Bupdate Example"

!addplugindir "."

; When someone presses cancel, add a confirmation dialog just in case.
!define MUI_ABORTWARNING
!define MUI_ABORTWARNING_TEXT "Cancel program installation?"

; Enable the Cancel button, which is normally disabled during installation.
Function EnableCancelButton
    GetDlgItem $0 $HWNDPARENT 2
    EnableWindow $0 1
FunctionEnd

; Set up MUI (the "Modern" user interface pages)
!include "MUI.nsh"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_COMPONENTS
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; Installer for the "main program" (not downloaded)
Section "Main Program"
    SetDetailsPrint textonly
    DetailPrint "wooga wooga!"
    SetDetailsPrint both
    
    SetOutPath $INSTDIR
    WriteUninstaller uninstall.exe
    File bupdate.dll
SectionEnd

; Installer for the downloaded sections
Section "Downloaded Bits"
    call EnableCancelButton

    ; Use this to let nsis ensure there's enough disk space available before
    ; starting the installation process at all.
    AddSize 6000000 ; kbytes
    
    SetOutPath $INSTDIR\downloaded
    
    ; Parameters: [/test] <url> <progbar-startpercent> <progbar-endpercent>
    bupdate::nsis /test no-url-needed 0 50
;    bupdate::nsis http://afterlife/~apenwarr/tmp/userful/debian.img.fidx 50 75
;    bupdate::nsis http://afterlife/~apenwarr/tmp/userful/debian.old.fidx 75 100
;    bupdate::nsis http://afterlife/~apenwarr/music/ 50 100

    DetailPrint "Doing stuff..."
    Sleep 500
    Sleep 500
    Sleep 500
    Sleep 500
    Sleep 500
    Sleep 500
    Sleep 500
    Sleep 500
    Sleep 500
    Sleep 500
    Sleep 500
SectionEnd

; Uninstaller for the main program
Section "un.Main Program" unMain
    SectionSetText $unMain "The stuff that goes in the main program."
    Delete $INSTDIR\bupdate.dll
    Delete $INSTDIR\uninstall.exe
SectionEnd

; Uninstaller for the downloaded bits: /o means unselected by default,
; because the download might have been really slow.  And reinstalling can
; use bupdate to update the already-downloaded files without re-downloading,
; which is the whole point.
Section /o "un.Downloaded Bits" unDown
    SectionSetText $unDown "The stuff that got downloaded automatically."
    RmDir /r $INSTDIR\downloaded
SectionEnd

; A non-optional uninstaller section for final cleanup.
Section "-un.Post"
    RmDir $INSTDIR
SectionEnd

