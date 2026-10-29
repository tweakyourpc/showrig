# Local setup and offline distribution

Showrig is an offline procedural video tool controlled from a local browser. It builds a FilmCraft timeline and exports an MP4 using native tools on the host computer. Rendering does not use a hosted service or download voice models. Browser fonts, title scripts, procedural music and the template catalog ship with Showrig.

The browser interface is portable. The host's Python packages, native executables and voice dependencies still have to match its operating system and processor. This source checkout does not contain FilmCraft, EffectCraft, FFmpeg, Blender or voice models. The Setup & extras page reports what is available and provides explicit installation steps.

## First launch

Install Python 3.11 or newer. From this source folder, Linux/macOS users run:

```sh
./scripts/setup.sh
./scripts/start-showrig.sh
```

Windows users run in PowerShell:

```powershell
./scripts/setup.ps1
./scripts/start-showrig.ps1
```

The setup scripts create an isolated `.venv`. Their first dependency installation needs a connection unless a complete platform-compatible wheelhouse is supplied. The startup scripts do not install anything. If local PowerShell execution policy prevents running scripts, follow your organization's policy or run the equivalent Python commands manually; no policy changes are made by Showrig.

On this homelab, the launcher obtains its port through `portbroker get --name showrig` or `portbroker alloc --name showrig`. On a standalone computer without portbroker it asks the OS for a free port and retains the bound socket. It prints and opens the actual URL. No fixed default port is required.

## Required native tools

Install FFmpeg (including FFprobe), FilmCraft CLI and EffectCraft CLI for your host. Put them on PATH or set `FILMCRAFT_CLI` and `EFFECTCRAFT_CLI` to their native executables. On Windows those normally end in `.exe`. Use the native builds supplied by the ArtCraft tools' distributor; a Linux executable cannot run on Windows or macOS.

The Setup & extras page has separate Windows, macOS and Ubuntu/Debian instructions. Other Linux distributions should use their own package manager. The instruction selector defaults to the **server's OS**, not the viewing browser's OS. Linux font packages are listed; on Windows/macOS install DejaVu/Inter fonts if a title/font check reports they are missing.

`showrig doctor --profile core --deep` performs functional probes. The browser's initial tool check only verifies availability/help responses, not a complete render.

## Optional voices

Install eSpeak NG for the host, as shown in Setup & extras. Use the official Windows MSI from [eSpeak NG releases](https://github.com/espeak-ng/espeak-ng/releases) on Windows, `brew install espeak-ng` on macOS, or your distribution's package on Linux. Windows phonemizer installations may require `PHONEMIZER_ESPEAK_LIBRARY` to point to the installed eSpeak NG DLL. Reopen the terminal after installing native libraries.

From an activated Showrig environment:

```sh
showrig setup --install-voices --dry-run
showrig setup --install-voices
showrig doctor --profile voice --deep
```

Without activation, use `.venv/bin/python -m showrig ...` on Linux/macOS or `.venv/Scripts/python.exe -m showrig ...` on Windows. The setup scripts also accept `--voices` (shell) or `-Voices` (PowerShell).

The explicit installer creates a separate per-user voice environment; it installs CPU PyTorch where supported, Kokoro, SoundFile, the English spaCy model, and five Kokoro voice files. A connection is needed during this setup. Installation ends with a **network-blocked synthesis check**. Failure is reported rather than silently declaring narration ready. Nothing installs during startup, capability checks or rendering. Text-only films, uploaded narration and procedural music do not need Kokoro.

Managed runtimes live under the user's normal application-data folder: Linux uses XDG data, macOS uses Application Support, Windows uses LOCALAPPDATA. `SHOWRIG_RUNTIME` overrides this location. Managed model files use `HF_HOME` if supplied, otherwise the runtime's `models` folder. Existing `SHOWRIG_TTS_PYTHON` and legacy Kokoro installations remain supported. A voice virtual environment is specific to its OS, CPU and Python installation; do not copy it between platforms.

Sources: [Kokoro](https://github.com/hexgrad/kokoro), [model and voice files](https://huggingface.co/hexgrad/Kokoro-82M), [spaCy model installation](https://spacy.io/usage/models).

## Building an offline kit

For distribution, prepare the kit **on each target OS/architecture**:

1. Include this application, its license and static assets.
2. Add matching native executables and required shared libraries in `runtime/<system>-<architecture>/bin`. The system name comes from Python `platform.system().lower()` and architecture from `platform.machine().lower()`. Showrig prepends this bin folder to PATH. `SHOWRIG_RUNTIME/bin` is another supported location. macOS signing, Windows DLLs and Linux shared libraries remain the distributor's responsibility.
3. Prepare a complete `runtime/wheels` wheelhouse for the target Python version, including Showrig's dependencies and setuptools/wheel build requirements. The setup scripts use `--no-index --find-links` when that directory exists; incomplete/incompatible kits fail visibly rather than fetching missing packages.
4. If voices are included, prepare and verify them on the target host. Preserve model/package/native-library licenses. Voice setup is optional and stays separate from the core application.
5. Disconnect networking, run `showrig doctor --profile core --deep`, optionally probe voice/3D profiles, then render a short film and reopen the extracted editable package in FilmCraft.

Only the browser/UI and launch paths have been exercised on Linux in this change. Windows/macOS branches need verification on their actual hosts before publishing a supported native kit. No untested cross-platform binary bundle is claimed.

## Keep the edit

The Export step provides a finished MP4, the `.fcproj` timeline and an editable ZIP containing the film folder, imported media and generated assets. Extract the ZIP as a whole, run `PREPARE-EDIT.py` with Python 3.11+, then open the project it prints in FilmCraft. Windows also has `Prepare edit.cmd`. The helper requires no installed Showrig package and changes only packaged media references, preserving timeline edits. Run it again if you move the extracted folder.

The ZIP stores relative media references plus a manifest. The preparation step binds those references to the extracted location because the tested FilmCraft CLI resolves relative paths against its working directory, not its project file. This was caught by a real relocation/export test. The original film and its projects are unchanged. A preview's project may live under `work/builds/<build>/out`; final exports also publish to `out`. Packages retain generated build assets, so they can be large.

Packaging refuses symlinked or external FilmCraft media rather than exporting a broken portable project. Import media into the film folder first. Native fonts and a matching FilmCraft installation are still needed on the editing host.

## Film history

Archive hides finished films from the Active view while preserving all files. Move to Trash moves the intact film folder to the library's `.trash` directory. Restore brings it back. Permanent deletion is offered only from Trash and requires explicit confirmation. Bulk archive/trash/restore is supported; cleanup is blocked while the library is rendering. No existing film is removed by this upgrade.
