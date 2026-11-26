# Antigravity Conversation Fork for Windows

Enable the existing conversation-forking interface in Antigravity by patching
two disabled UI flags in its locally installed language server. The Fork button
appears beside the copy and feedback buttons at the end of a response. Choose
**Fork in Current Workspace** to create a separate conversation; both
conversations share the same workspace files. The patch also enables the UI
option for forking from historical responses.

## Compatibility

**Windows only. Antigravity 2.35.2 only**, and only the Windows build whose
`language_server.exe` has this SHA-256:

```text
fcdf7454007c6edc8162e601628c28cc1e6f575be849f329bb864c41ba6e6b02
```

The patcher refuses any other input hash. An update can replace the patch; do
not apply this patch to another version. It has been tested on Windows with
Antigravity 2.35.2, including creating a fork through the application UI.
This is an unofficial project and is not affiliated with Antigravity or Google.
No Antigravity executable or bundled resources are distributed here.

## Requirements

- Windows and the exact Antigravity build above.
- Python 3.8 or newer; the script uses only the standard library.
- Enough free disk space for the original backup and patched copy.

## Install

1. Quit Antigravity completely and make sure `language_server.exe` is no
   longer running (for example, using Task Manager).
2. Open PowerShell in the directory containing `patch_antigravity.py` and run:

   ```powershell
   $server = "$env:LOCALAPPDATA\Programs\Antigravity\resources\bin\language_server.exe"
   Get-FileHash -Algorithm SHA256 -LiteralPath $server
   ```

   Continue only if the hash matches the one in Compatibility. If your
   installation is elsewhere, change `$server` to its actual path.
3. Create a backup and generate a separate patched executable:

   ```powershell
   if (Test-Path -LiteralPath .\language_server-original-2.35.2.exe) { throw 'Backup already exists; choose a new directory.' }
   Copy-Item -LiteralPath $server -Destination .\language_server-original-2.35.2.exe
   python .\patch_antigravity.py .\language_server-original-2.35.2.exe .\language_server-patched-2.35.2.exe
   ```

   The patcher checks the original hash, validates the embedded ZIP, checks the
   two flag patterns, and verifies all ZIP entries after modification. It will
   not overwrite an existing output file.
4. With Antigravity still closed, install the generated copy and check it:

   ```powershell
   if (Get-Process -Name language_server -ErrorAction SilentlyContinue) { throw 'Quit Antigravity first.' }
   $expected = 'FCDF7454007C6EDC8162E601628C28CC1E6F575BE849F329BB864C41BA6E6B02'
   if ((Get-FileHash -LiteralPath $server).Hash -ne $expected -or (Get-FileHash -LiteralPath .\language_server-original-2.35.2.exe).Hash -ne $expected) { throw 'Original or backup hash mismatch.' }
   Copy-Item -LiteralPath .\language_server-patched-2.35.2.exe -Destination $server -Force
   (Get-FileHash -Algorithm SHA256 -LiteralPath $server).Hash -eq (Get-FileHash -Algorithm SHA256 -LiteralPath .\language_server-patched-2.35.2.exe).Hash
   ```

   The final command must return `True`. Keep the original backup, then start
   Antigravity. If the app fails to start, restore the backup as described below.

## Restore

Quit Antigravity and make sure `language_server.exe` has exited. Compare the
installed file's SHA-256 with your generated patched copy, and the backup's
SHA-256 with the original hash in Compatibility. Restore only if both match:

```powershell
$server = "$env:LOCALAPPDATA\Programs\Antigravity\resources\bin\language_server.exe"
if (Get-Process -Name language_server -ErrorAction SilentlyContinue) { throw 'Quit Antigravity first.' }
$expected = 'FCDF7454007C6EDC8162E601628C28CC1E6F575BE849F329BB864C41BA6E6B02'
if ((Get-FileHash -LiteralPath $server).Hash -ne (Get-FileHash -LiteralPath .\language_server-patched-2.35.2.exe).Hash -or (Get-FileHash -LiteralPath .\language_server-original-2.35.2.exe).Hash -ne $expected) { throw 'Installed file or backup hash mismatch.' }
Copy-Item -LiteralPath .\language_server-original-2.35.2.exe -Destination $server -Force
```

If the installed hash differs from your patched copy, the app may have updated;
do not overwrite it with the old backup. Adjust `$server` if you installed
Antigravity in a different location.

## How it works

The Windows language server contains a ZIP archive of UI assets. For the exact
verified binary, the patcher decompresses `main.js`, changes the defaults for
`conversationForkingEnabled` and `conversationForkingHistoricalStep`, and
recompresses it in place. It updates the ZIP checksums and keeps the executable
size unchanged. The source executable is never modified by the patcher itself.

## License

The code in this repository is available under the [MIT License](LICENSE). This
license does not grant rights to Antigravity or its bundled assets.
