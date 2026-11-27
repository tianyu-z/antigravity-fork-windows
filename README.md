# Antigravity Conversation Fork for Windows and macOS

Enable the existing conversation-forking interface in Antigravity by patching
two disabled UI flags in its locally installed language server. The Fork button
appears beside the copy and feedback buttons at the end of a response. Choose
**Fork in Current Workspace** to create a separate conversation; both
conversations share the same workspace files. The patch also enables the UI
option for forking from historical responses.

For macOS instructions in Chinese, see [macOS 安装与恢复指南（简体中文）](README-macos.zh-CN.md).

This is an unofficial project and is not affiliated with Antigravity or Google.
No Antigravity application binaries or bundled resources are distributed here.
The repository remains `antigravity-fork`; the original Windows patcher
is still `patch_antigravity.py`.

## Compatibility

### Windows

**Windows: Antigravity 2.35.2 only**, and only the Windows build whose
`language_server.exe` has this SHA-256:

```text
fcdf7454007c6edc8162e601628c28cc1e6f575be849f329bb864c41ba6e6b02
```

The patcher refuses any other input hash. An update can replace the patch; do
not apply this patch to another version. It has been tested on Windows with
Antigravity 2.35.2, including creating a fork through the application UI.

### macOS

**macOS: Antigravity 2.35.2, Apple Silicon arm64 only**, with this SHA-256 for
the original, unmodified `Contents/Resources/bin/language_server`:

```text
8b11ecde9d089ebbe4511871e75bd046e04f33865c27b617e29a3c237a2bd575
```

The macOS tools refuse Intel builds, other versions, and any other input hash.
Only the exact macOS 2.35.2 build above is supported.

Runtime behavior was verified on this exact Mac profile after a full application
restart: the app starts successfully, **Fork Conversation** appears on both the
latest and historical replies, and **Fork in Current Workspace** creates
independent conversations with the appropriate history while leaving the
original conversation history intact. Forks share workspace files and do not
create a new Git worktree.

## Get the scripts

Clone the entire repository, or download and extract its repository ZIP. Keep
all repository Python scripts together, including `macos_app.py` and
`patch_antigravity_macos.py` for macOS; downloading only the Windows script is
not sufficient for the Mac workflow.

```sh
git clone https://github.com/tianyu-z/antigravity-fork.git
cd antigravity-fork
```

Run the commands below from this repository directory, using PowerShell on
Windows or Terminal on macOS.

## Windows

### Requirements

- Windows and the exact Antigravity build above.
- Python 3.8 or newer; the script uses only the standard library.
- Enough free disk space for the original backup and patched copy.

### Install

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

### Restore

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

### How it works

The Windows language server contains a ZIP archive of UI assets. For the exact
verified binary, the patcher decompresses `main.js`, changes the defaults for
`conversationForkingEnabled` and `conversationForkingHistoricalStep`, and
recompresses it in place. It updates the ZIP checksums and keeps the executable
size unchanged. The source executable is never modified by the patcher itself.

## macOS

### Requirements

- The exact original Antigravity 2.35.2 Apple Silicon arm64 profile above.
- Python 3.8 or newer. The tools use only the Python standard library and the
  macOS built-in `codesign`, `ditto`, and `ps` commands.
- Enough free disk space for full original and patched application copies.
  These copies can require more than 2 GB; installation also keeps the previous
  target temporarily.
- Filesystem access to the application and its parent directory, plus macOS
  App Management access when required. The scripts use the current user's
  access and do not invoke `sudo` or ask for credentials.
- Antigravity and its language server must be fully closed before installation
  or restoration. Quit the application completely, not just its window.

The commands below use `/Applications/Antigravity.app` and a build folder in
your home directory. Keep the entire build folder for verification and restore.

### Install

1. Obtain all repository scripts as described above. Fully quit Antigravity and
   confirm that its language server is no longer running, for example in
   Activity Monitor.
2. Check the original language server:

   ```sh
   shasum -a 256 "/Applications/Antigravity.app/Contents/Resources/bin/language_server"
   ```

   Continue only if the hash matches the macOS hash in Compatibility and the
   application is version 2.35.2 for Apple Silicon arm64. An already-patched
   app is not valid original input.
3. Prepare a separate, verified application build:

   ```sh
   python3 macos_app.py prepare /Applications/Antigravity.app "$HOME/antigravity-fork-macos-2.35.2"
   ```

   The output directory must not already exist. If it does, choose a new build
   folder and use that same folder in the later install and restore commands.
   Preparation refuses unsupported input and creates:

   - `original/Antigravity.app`: a full, untouched backup.
   - `patched/Antigravity.app`: the locally signed and verified staged app.
   - `receipt.json`: the fingerprints used to check the original and patched
     applications.

   Preparation does not alter the installed application. Keep these files
   together and do not edit the receipt or either app copy.
4. With the app and server still fully closed, install the staged build:

   ```sh
   python3 macos_app.py install "$HOME/antigravity-fork-macos-2.35.2" /Applications/Antigravity.app
   ```

   Installation verifies the receipt, original backup and staged app signatures,
   and the exact fingerprint of the currently installed original app before
   replacing it. It refuses official updates or unexpected modifications.
   It preserves the previous target in a temporary sibling folder under
   `/Applications`, prints that folder's path, and never overwrites an existing
   backup. Replacement uses atomic directory renames and rolls back if
   replacement or verification fails. Keep the printed backup path and the
   build folder until you have verified the installed app.
5. Verify the installed signature, then open the installed app:

   ```sh
   codesign --verify --deep --strict "/Applications/Antigravity.app"
   open "/Applications/Antigravity.app"
   ```

   Follow any macOS security approval prompt for your own generated build;
   managed policies may prevent approval. Check that the app starts after this
   full restart. Use **Fork Conversation** on both the latest reply and a
   historical reply, then choose **Fork in Current Workspace**. Confirm that
   each fork is an independent conversation with the appropriate history and
   that the original conversation history remains intact. Workspace files
   remain shared; this action does not create a new Git worktree.

### Restore

Fully quit Antigravity and its language server, then run:

```sh
python3 macos_app.py restore "$HOME/antigravity-fork-macos-2.35.2" /Applications/Antigravity.app
```

Restoration proceeds only when the installed target matches that build's
generated patched fingerprint and the backup matches its original fingerprint.
It restores the **whole application**, including the original main signing and
resource seal and application-directory metadata, rather than just replacing
`language_server`. Once restoration
succeeds, reopen the app.

Restore refuses official updates and unknown changes. If Antigravity has
updated, do not overwrite it with an old backup. Recheck the version,
architecture, and original hash against the supported profile before preparing
another patch.

### What changes and how signing works

Only the defaults for `conversationForkingEnabled` and
`conversationForkingHistoricalStep` change in the embedded `main.js`.
The original vendor Electron frameworks and helpers are retained.

The modified language server is locally ad-hoc re-signed while preserving its
identifier, entitlements, and hardened-runtime flags. The main application is
also locally ad-hoc re-signed with its original entitlements and flags, plus
`com.apple.security.cs.disable-library-validation=true`. This permits the
locally signed main application to load the original Google-signed Electron
dependencies. All other hardened-runtime options remain.

This **replaces the application's official main signature with a local
signature and relaxes this app's library signature checks**. Local signatures
may trigger macOS security approval; follow the operating system prompt for
your own generated build. Managed device policies may prevent it.
`codesign --verify --deep --strict` above is a verification command; the
installer handles signing.

### Troubleshooting

- **Operation not permitted:** Open **System Settings > Privacy & Security >
  App Management** and enable the application executing the commands, such as
  Terminal or an AI desktop host such as ChatGPT. Complete any Touch ID or
  password approval in the macOS window. Do not enter passwords in the terminal
  or chat. Retry the command after granting access.
- **Build folder already exists:** Choose a new output directory; do not
  overwrite the existing backup, staged application, or receipt.
- **Unsupported or already-patched input:** Use an unmodified original backup
  or a matching vendor app. Recheck the version, architecture, and original
  hash. Installation still requires the target to match the original app
  fingerprint recorded during preparation.
- **App or server still running:** Quit both completely before retrying install
  or restore.
- **Fingerprint mismatch after an official update or other change:** Stop using
  that old build for installation or restore. Check the current app against the
  supported profile instead of replacing it with an old backup.

### Optional: patch a separate language server only

```sh
python3 patch_antigravity_macos.py SOURCE_SERVER NEW_OUTPUT_SERVER
```

This low-level command creates only a separate patched binary. It does not
install a complete app or fix application signatures. Use the `macos_app.py`
prepare/install workflow for the signed application described above.

## Tests

Run the standard-library tests from the repository directory:

```sh
python3 -m unittest discover -s tests -v
```

The tests cover ZIP integrity, build/backup path protection, running-server
refusal, update detection, rollback, and original-directory metadata. The BSD
directory-flags check runs on macOS. Preparation, installation, restoration,
and native startup were also tested on copies of the verified macOS app.

## License

The scripts in this repository are available under the [MIT License](LICENSE).
This license does not grant rights to Antigravity or its bundled assets.
