# syntax=docker/dockerfile:1.6
FROM ubuntu:22.04

# ---------- build args ----------
ARG FLUTTER_VERSION
ARG ANDROID_SDK_VERSION=11076708
ARG JDK_VERSION=17               
ARG DEBIAN_FRONTEND=noninteractive

# ---------- env ----------
ENV ANDROID_HOME=/opt/android
ENV ANDROID_SDK_ROOT=/opt/android
ENV FLUTTER_HOME=/opt/flutter
ENV GRADLE_USER_HOME=/opt/gradle
RUN mkdir -p /opt/gradle

ENV PATH="$FLUTTER_HOME/bin:$FLUTTER_HOME/bin/cache/dart-sdk/bin:\
$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"

# ---------- base deps ----------
RUN apt-get update && apt-get install -y \
    curl \
    git \
    unzip \
    xz-utils \
    zip \
    libglu1-mesa \
    ca-certificates \
    openjdk-${JDK_VERSION}-jdk \
    && rm -rf /var/lib/apt/lists/*

# ---------- verify java ----------
RUN java -version

# ---------- android sdk ----------
RUN mkdir -p $ANDROID_HOME/cmdline-tools

# Conditional SDK tools depending on JDK version
RUN if [ "$JDK_VERSION" = "11" ]; then \
        SDK_URL="https://dl.google.com/android/repository/commandlinetools-linux-7583922_latest.zip"; \
    else \
        SDK_URL="https://dl.google.com/android/repository/commandlinetools-linux-${ANDROID_SDK_VERSION}_latest.zip"; \
    fi && \
    curl -4 -fsSL $SDK_URL -o /tmp/cmdline-tools.zip && \
    unzip /tmp/cmdline-tools.zip -d $ANDROID_HOME/cmdline-tools && \
    mv $ANDROID_HOME/cmdline-tools/cmdline-tools $ANDROID_HOME/cmdline-tools/latest && \
    rm /tmp/cmdline-tools.zip

# ---------- accept licenses ----------
RUN yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses

# ---------- install android packages ----------
RUN $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager \
    "platform-tools" \
    "platforms;android-34" \
    "build-tools;34.0.0"

# ---------- flutter ----------
RUN git clone https://github.com/flutter/flutter.git \
    -b ${FLUTTER_VERSION} \
    --depth 1 \
    $FLUTTER_HOME

# ---------- flutter doctor ----------
RUN flutter doctor --android-licenses && flutter doctor

# ---------- gradle sanity ----------
ENV GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.parallel=false -Xmx4g"
ENV ORG_GRADLE_PROJECT_org.gradle.jvmargs="-Xmx4g -XX:MaxMetaspaceSize=1g -Dkotlin.daemon.jvm.options=-Xmx2g"

# ---------- workdir ----------
WORKDIR /app

# create a .env in the workdir
RUN touch /app/.env