# syntax=docker/dockerfile:1.6
#
# Uses unityci/editor as the base — maintained by the GameCI project and
# pre-installed with Unity Editor + Android Build Support for every LTS version.
# Unity Hub installation on Linux via APT/AppImage is broken in Docker contexts.
#
# Available tags:  https://hub.docker.com/r/unityci/editor/tags
# Tag format:      unityci/editor:ubuntu-{UNITY_VERSION}-android-{IMAGE_VERSION}
# IMAGE_VERSION:   check the tags page for the latest suffix for each Unity version.
#                  Typically 3 for 2022.3+, may differ for older or newer versions.

# ARG must appear before FROM to be usable in the base image reference
ARG UNITY_VERSION=2022.3.54f1
ARG UNITY_IMAGE_VERSION=3

FROM unityci/editor:ubuntu-${UNITY_VERSION}-android-${UNITY_IMAGE_VERSION}

# ---------- build args (re-declared after FROM) ----------
ARG DEBIAN_FRONTEND=noninteractive

# ---------- pre-generate debug keystore (used for release signing) ----------
RUN mkdir -p /root/.android && \
    keytool -genkeypair -v \
        -keystore /root/.android/debug.keystore \
        -alias androiddebugkey \
        -keyalg RSA -keysize 2048 \
        -validity 10000 \
        -storepass android -keypass android \
        -dname "CN=Android Debug,O=Android,C=US" 2>/dev/null || true

# ---------- bake in the build helper script ----------
COPY BuildScript.cs /opt/BuildScript.cs

# ---------- workdir ----------
WORKDIR /app
