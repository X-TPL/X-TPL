# syntax=docker/dockerfile:1.6
FROM ubuntu:22.04

# ---------- build args ----------
ARG UNITY_VERSION=2022.3.54f1
ARG JDK_VERSION=17
ARG DEBIAN_FRONTEND=noninteractive

# ---------- env ----------
ENV ANDROID_HOME=/opt/android
ENV ANDROID_SDK_ROOT=/opt/android
ENV GRADLE_USER_HOME=/opt/gradle
ENV JAVA_HOME=/usr/lib/jvm/java-${JDK_VERSION}-openjdk-amd64
ENV PATH="$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"
ENV UNITY_VERSION=${UNITY_VERSION}

RUN mkdir -p /opt/gradle

# ---------- base deps ----------
# libglu1-mesa + friends are needed by some Unity Editor modules even with -nographics
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    unzip \
    ca-certificates \
    gnupg \
    openjdk-${JDK_VERSION}-jdk \
    libglu1-mesa \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libxi6 \
    libxrandr2 \
    libxcursor1 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# ---------- verify java ----------
RUN java -version

# ---------- android sdk ----------
RUN mkdir -p $ANDROID_HOME/cmdline-tools && \
    SDK_VERSION=11076708 && \
    curl -4 -fsSL \
      https://dl.google.com/android/repository/commandlinetools-linux-${SDK_VERSION}_latest.zip \
      -o /tmp/cmdline-tools.zip && \
    unzip /tmp/cmdline-tools.zip -d $ANDROID_HOME/cmdline-tools && \
    mv $ANDROID_HOME/cmdline-tools/cmdline-tools $ANDROID_HOME/cmdline-tools/latest && \
    rm /tmp/cmdline-tools.zip

# ---------- accept licenses ----------
RUN yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses

# ---------- install android packages ----------
RUN $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager \
    "platform-tools" \
    "platforms;android-34" \
    "platforms;android-35" \
    "build-tools;34.0.0" \
    "build-tools;35.0.0" \
    "cmake;3.22.1" \
    "ndk;25.2.9519653"

# ---------- Unity Hub (AppImage — avoids broken APT repo) ----------
# Extract the AppImage in-place; --appimage-extract does not need FUSE.
RUN curl -L "https://public-cdn.cloud.unity3d.com/hub/prod/UnityHub.AppImage" \
        -o /tmp/UnityHub.AppImage && \
    chmod +x /tmp/UnityHub.AppImage && \
    cd /tmp && ./UnityHub.AppImage --appimage-extract > /dev/null 2>&1 && \
    mv /tmp/squashfs-root /opt/unityhub && \
    rm /tmp/UnityHub.AppImage && \
    printf '#!/bin/sh\nexec /opt/unityhub/AppRun "$@"\n' > /usr/local/bin/unity-hub && \
    chmod +x /usr/local/bin/unity-hub

# ---------- Unity Editor with Android Build Support ----------
# Unity Hub 3.x headless syntax: unity-hub -- --headless <cmd>
# --childModules also pulls in OpenJDK + Android SDK bundled with Unity,
# but we use the system SDK via ANDROID_SDK_ROOT instead.
RUN unity-hub -- --headless install \
    --version ${UNITY_VERSION} \
    --module android \
    --childModules

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

# ---------- gradle stability ----------
ENV GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.parallel=false -Xmx4g"

# ---------- workdir ----------
WORKDIR /app
