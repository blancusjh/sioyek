# Building the personal Sioyek source on Linux

This saves the current local source, including grayscale rendering and highlight
blending. It does not identify the exact source revision used for the older
installed Mac binary. The merged source was compiled on 2026-10-05 in a Debian 13
(trixie) ARM64 container with GCC 14 and Qt 6.8.2. Other distributions and x86_64
machines were initially untested. The same application source was also built
and tested on PHANEX (Arch Linux x86_64, GCC 16.2.1, Qt 6.11.2) on 2026-10-05.
Use [RELEASES.md](RELEASES.md) to install matching release builds on both machines.

## Get the source

```bash
git clone --recurse-submodules --branch personal-build https://github.com/blancusjh/sioyek.git
cd sioyek
```

The recursive clone is required: MuPDF and zlib are pinned Git submodules.
For an existing clone, run `git submodule update --init --recursive`.

## Dependencies

Use Qt **6**, a C++20 compiler, make, pkg-config, HarfBuzz and OpenGL
development libraries. Required Qt modules include Core, GUI, Widgets, Network,
OpenGL, OpenGLWidgets, QuickWidgets, SVG and TextToSpeech.
Qt 6.8.2 was tested on Debian 13; Qt 6.11.2 was tested on PHANEX's Arch Linux.

For Ubuntu/Debian, start with:

```bash
sudo apt update
sudo apt install build-essential git pkg-config python3-venv unzip \
    libharfbuzz-dev libgl1-mesa-dev libglu1-mesa-dev \
    libxrandr-dev libxi-dev libxcb-cursor0 libxkbcommon-x11-0 libspeechd2
```

On Debian 13, the distribution's Qt 6.8.2 development packages were used:

```bash
sudo apt install freeglut3-dev qt6-base-dev qt6-declarative-dev \
    qt6-svg-dev qt6-speech-dev libqt6opengl6-dev
export QMAKE=/usr/bin/qmake6
```

If the distribution supplies a tested Qt version with the required modules, use its
development packages. Otherwise, on an **x86_64** machine, install Qt 6.8.2
in your home directory with [aqtinstall](https://aqtinstall.readthedocs.io/en/latest/getting_started.html):

```bash
python3 -m venv "$HOME/.venvs/sioyek-qt"
"$HOME/.venvs/sioyek-qt/bin/pip" install aqtinstall
"$HOME/.venvs/sioyek-qt/bin/aqt" install-qt linux desktop 6.8.2 linux_gcc_64 \
    -O "$HOME/Qt" -m qtdeclarative qtsvg qtspeech
export QMAKE="$HOME/Qt/6.8.2/gcc_64/bin/qmake"
export PATH="$HOME/Qt/6.8.2/gcc_64/bin:$PATH"
export LD_LIBRARY_PATH="$HOME/Qt/6.8.2/gcc_64/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

The downloaded Qt binaries also require a compatible Linux system. For ARM64,
use the appropriate ARM64 Qt packages; the x86_64 command above does not apply.

## Build and run

Set `QMAKE` to your Qt 6 qmake executable even if Qt 5 is also installed:

```bash
"$QMAKE" --version
./build_linux.sh
./build/sioyek
```

If using distribution Qt, for example `export QMAKE=/usr/bin/qmake6`, verify
that its reported version matches your tested Qt setup first. The build script compiles bundled
MuPDF and copies the executable, shaders, configs and tutorial into `build/`.
Keep those files together. This is a runnable directory, not an AppImage;
the machine still needs the matching Qt runtime libraries.

## Update on another machine

```bash
git pull --ff-only
git submodule update --init --recursive
./build_linux.sh
```

The source defaults are included. Personal reading databases, annotations and
machine-specific user settings are separate and are not transferred by cloning.
