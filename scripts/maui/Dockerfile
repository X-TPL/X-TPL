# syntax=docker/dockerfile:1.6
FROM ubuntu:22.04

# ---------- build args ----------
ARG DOTNET_VERSION=8
ARG JDK_VERSION=17
ARG ANDROID_SDK_VERSION=11076708
ARG DEBIAN_FRONTEND=noninteractive

# ---------- env ----------
ENV ANDROID_HOME=/opt/android
ENV ANDROID_SDK_ROOT=/opt/android
ENV GRADLE_USER_HOME=/opt/gradle
ENV DOTNET_ROOT=/opt/dotnet
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV DOTNET_NOLOGO=1
ENV PATH="/opt/dotnet:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"

RUN mkdir -p /opt/gradle

# ---------- base deps ----------
RUN apt-get update && apt-get install -y \
    curl \
    git \
    unzip \
    xz-utils \
    zip \
    ca-certificates \
    openjdk-${JDK_VERSION}-jdk \
    && rm -rf /var/lib/apt/lists/*

# ---------- verify java ----------
ENV JAVA_HOME=/usr/lib/jvm/java-${JDK_VERSION}-openjdk-amd64
ENV PATH="$JAVA_HOME/bin:$PATH"
RUN java -version

# ---------- .NET SDK ----------
RUN curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh && \
    chmod +x /tmp/dotnet-install.sh && \
    /tmp/dotnet-install.sh --channel ${DOTNET_VERSION}.0 --install-dir /opt/dotnet && \
    rm /tmp/dotnet-install.sh

RUN dotnet --version

# ---------- android sdk ----------
RUN mkdir -p $ANDROID_HOME/cmdline-tools && \
    if [ "$JDK_VERSION" = "11" ]; then \
        SDK_VERSION=9477386; \
    else \
        SDK_VERSION=${ANDROID_SDK_VERSION}; \
    fi && \
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
    "platforms;android-36" \
    "build-tools;34.0.0" \
    "build-tools;35.0.0" \
    "build-tools;36.0.0"

# ---------- .NET MAUI Android workload ----------
RUN dotnet workload install maui-android --skip-sign-check

# ---------- pre-generate debug keystore (used for release signing) ----------
RUN mkdir -p /root/.android && \
    keytool -genkeypair -v \
        -keystore /root/.android/debug.keystore \
        -alias androiddebugkey \
        -keyalg RSA -keysize 2048 \
        -validity 10000 \
        -storepass android -keypass android \
        -dname "CN=Android Debug,O=Android,C=US" 2>/dev/null || true

# ---------- gradle stability ----------
ENV GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.parallel=false -Xmx4g"
ENV ORG_GRADLE_PROJECT_org.gradle.jvmargs="-Xmx4g -XX:MaxMetaspaceSize=1g"

# ---------- workdir ----------
WORKDIR /app
