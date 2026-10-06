#!/usr/bin/env bash
set -e
# Prerequisites: Qt 6.8.x, Xcode, freeglut, mesa, and harfbuzz.
# On Apple Silicon, the Qt 6.8.x host tools shipped by aqtinstall need to
# run under Rosetta, while the application itself must be built for arm64.

#sys_glut_clfags=`pkg-config --cflags glut gl`
#sys_glut_libs=`pkg-config --libs glut gl`
#sys_harfbuzz_clfags=`pkg-config --cflags harfbuzz`
#sys_harfbuzz_libs=`pkg-config --libs harfbuzz`

if [ -z ${MAKE_PARALLEL+x} ]; then export MAKE_PARALLEL=1; else echo "MAKE_PARALLEL defined"; fi
echo "MAKE_PARALLEL set to $MAKE_PARALLEL"

QMAKE_CMD=(qmake)
MACDEPLOYQT_CMD=(macdeployqt)
QT_HOST_TOOLS_PREFIX=""
QMAKE_TARGET_ARCH=""

if [[ "$(uname -m)" == "arm64" ]]; then
	QMAKE_CMD=(arch -x86_64 qmake)
	MACDEPLOYQT_CMD=(arch -x86_64 macdeployqt)
	QT_HOST_TOOLS_PREFIX="arch -x86_64 "
	QMAKE_TARGET_ARCH=" QMAKE_APPLE_DEVICE_ARCHS=arm64"
fi

cd mupdf
#make USE_SYSTEM_HARFBUZZ=yes USE_SYSTEM_GLUT=yes SYS_GLUT_CFLAGS="${sys_glut_clfags}" SYS_GLUT_LIBS="${sys_glut_libs}" SYS_HARFBUZZ_CFLAGS="${sys_harfbuzz_clfags}" SYS_HARFBUZZ_LIBS="${sys_harfbuzz_libs}" -j 4
make HAVE_GLUT=no -j$MAKE_PARALLEL
cd ..

sed -Ei '' "s/QMAKE_MACOSX_DEPLOYMENT_TARGET.=.[0-9]+/QMAKE_MACOSX_DEPLOYMENT_TARGET = $(sw_vers -productVersion | cut -d. -f1)/" pdf_viewer_build_config.pro

if [[ $1 == portable ]]; then
	# shellcheck disable=SC2086
	"${QMAKE_CMD[@]}" $QMAKE_TARGET_ARCH pdf_viewer_build_config.pro
else
	# shellcheck disable=SC2086
	"${QMAKE_CMD[@]}" $QMAKE_TARGET_ARCH "CONFIG+=non_portable" pdf_viewer_build_config.pro
fi

# qmake sees the x86_64 host tool on Apple Silicon, so the project file's
# host-architecture test cannot add this arm64/Xcode 26 compatibility flag.
if [[ "$(uname -m)" == "arm64" ]]; then
	sed -i '' 's/^CXXFLAGS      = /CXXFLAGS      = -include arm_acle.h /' Makefile
	# Use Rosetta for Qt's code generators; clang still compiles arm64 objects.
	sed -i '' \
		-e "s#$(command -v moc)#${QT_HOST_TOOLS_PREFIX}$(command -v moc)#g" \
		-e "s#$(command -v rcc)#${QT_HOST_TOOLS_PREFIX}$(command -v rcc)#g" \
		Makefile
fi

# Qt 6.8.x still links the legacy AGL framework, which is absent from the
# macOS 26 SDK. OpenGL.framework provides the APIs used by sioyek.
MACOS_SDK_PATH="$(xcrun --sdk macosx --show-sdk-path)"
if [[ ! -d "$MACOS_SDK_PATH/System/Library/Frameworks/AGL.framework" ]]; then
	sed -i '' 's/ -framework AGL//g' Makefile
fi

make -j$MAKE_PARALLEL

rm -rf build 2> /dev/null
mkdir build
mv sioyek.app build/
cp -r pdf_viewer/shaders build/sioyek.app/Contents/Resources/shaders

cp pdf_viewer/prefs.config build/sioyek.app/Contents/Resources/prefs.config
cp pdf_viewer/prefs_user.config build/sioyek.app/Contents/Resources/prefs_user.config
cp pdf_viewer/keys.config build/sioyek.app/Contents/Resources/keys.config
cp pdf_viewer/keys_user.config build/sioyek.app/Contents/Resources/keys_user.config
cp tutorial.pdf build/sioyek.app/Contents/Resources/tutorial.pdf

# Capture the current PATH
CURRENT_PATH=$(echo $PATH)

# Define the path to the Info.plist file inside the app bundle
INFO_PLIST="build/sioyek.app/Contents/Info.plist"

# Add LSEnvironment key with PATH to Info.plist
/usr/libexec/PlistBuddy -c "Add :LSEnvironment dict" "$INFO_PLIST" || echo "LSEnvironment already exists"
/usr/libexec/PlistBuddy -c "Add :LSEnvironment:PATH string $CURRENT_PATH" "$INFO_PLIST" || /usr/libexec/PlistBuddy -c "Set :LSEnvironment:PATH $CURRENT_PATH" "$INFO_PLIST"

# Hack is required to avoid race condition in macos in CI
# See https://github.com/actions/runner-images/issues/7522
if [[ -n "$GITHUB_ACTIONS" ]]; then
  echo killing...; sudo pkill -9 XProtect >/dev/null || true;
  echo waiting...; while pgrep XProtect; do sleep 3; done;
fi

sleep 5

# macdeployqt can bundle the application even when this environment cannot
# create a DMG (for example, when hdiutil is unavailable in a sandbox).
# Set MAKE_DMG=0 for a faster app-only build.
if [[ ${MAKE_DMG:-1} == 0 ]]; then
	"${MACDEPLOYQT_CMD[@]}" build/sioyek.app
else
	if ! "${MACDEPLOYQT_CMD[@]}" build/sioyek.app -dmg; then
		echo "WARNING: DMG creation failed; keeping the application bundle." >&2
	fi
fi

codesign --force --deep --sign - build/sioyek.app

if [[ -f build/sioyek.dmg ]]; then
	zip -r sioyek-release-mac.zip build/sioyek.dmg
else
	echo "DMG not created; build/sioyek.app is ready to use."
fi
