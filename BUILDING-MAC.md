# Building sioyek on this Mac

Notes for the local arm64 setup (MacBook Air M4, macOS 26.5, Xcode 26.5).
Verified working on 2026-09-01. See `README.md` for the generic instructions.

## Prerequisites

Already installed here — listed so they can be restored if the machine is rebuilt.

| Component | Where |
| --- | --- |
| Qt 6.8.2 | `~/Library/Developer/Qt/6.8.2/macos` (via `aqtinstall`) |
| Xcode + command line tools | `/Applications/Xcode.app` |
| freeglut, mesa, harfbuzz | Homebrew |
| mupdf | `mupdf/` submodule, built into `mupdf/build/release` |

`zlib` is *not* needed from Homebrew: the repo bundles `zlib/` on the include
path and macOS supplies the system `libz`.

## Qt 6 must come first on PATH

This is the one thing that reliably breaks the build.

Homebrew's `qt@5` is installed and owns `qmake` in the default PATH:

```
$ which qmake
/opt/homebrew/opt/qt@5/bin/qmake   # <- Qt 5.15.18, wrong
```

The development branch needs Qt 6.7 or 6.8, and the `-include arm_acle.h`
workaround in `pdf_viewer_build_config.pro` exists specifically for Qt 6.8.x on
arm64. Building with `qt@5` regenerates the `Makefile` against the wrong Qt and
also picks the wrong `macdeployqt` for bundling.

Always export this first:

```bash
export PATH="$HOME/Library/Developer/Qt/6.8.2/macos/bin:$PATH"
```

Confirm before building:

```bash
qmake -v   # must report Qt 6.8.2
```

## Full build

```bash
export PATH="$HOME/Library/Developer/Qt/6.8.2/macos/bin:$PATH"
MAKE_PARALLEL=8 ./build_mac.sh
```

Produces `build/sioyek.app` and `build/sioyek.dmg`. To install:

```bash
mv build/sioyek.app /Applications/
sudo codesign --force --sign - --deep /Applications/sioyek.app
```

Note that `build_mac.sh` rebuilds mupdf. It is already built, so a full run is
only necessary after changing the `.pro` file, adding source files, or editing
`resources.qrc`.

## Incremental build (the usual case)

For iterating on source changes:

```bash
make -j8
```

This writes the binary straight to `sioyek.app/Contents/MacOS/sioyek`. mupdf is
not touched.

**`make` alone does not produce a runnable app.** It only relinks the
executable. Everything else that makes the bundle work is done by `build_mac.sh`
*after* `make`: the shaders, the config files, `tutorial.pdf`, and the Qt
frameworks. Launching a bundle that has only the binary gives a window with no
rendered page, no table of contents, and no working file open — the app starts,
but has nothing to draw with and no keybindings.

So after the first `make` into a fresh bundle, do the bundling once:

```bash
export PATH="$HOME/Library/Developer/Qt/6.8.2/macos/bin:$PATH"

cp -r pdf_viewer/shaders sioyek.app/Contents/MacOS/shaders
cp pdf_viewer/prefs.config pdf_viewer/prefs_user.config \
   pdf_viewer/keys.config pdf_viewer/keys_user.config \
   tutorial.pdf sioyek.app/Contents/MacOS/

macdeployqt sioyek.app
codesign --force --deep --sign - sioyek.app
```

After that, plain `make -j8` is genuinely enough for source-only edits — it
overwrites just the executable and leaves the bundled resources in place. Redo
the `cp` of `shaders/` when you add or edit a shader, since `make` does not copy
them.

## Gotcha: `-framework AGL` link failure

The macOS 26 SDK dropped `AGL.framework`, but Qt 6.8.x still asks the linker for
it. The symptom is a failed link at the very end of the build, leaving an empty
`sioyek.app/Contents/MacOS/` directory.

`build_mac.sh` strips the flag automatically, so a full run is fine. But running
bare `qmake` regenerates the `Makefile` with `-framework AGL` back in it. After
any manual `qmake`, reapply the same fix before `make`:

```bash
sed -i '' 's/ -framework AGL//g' Makefile
```

`Makefile` is generated and gitignored, so editing it is safe.
