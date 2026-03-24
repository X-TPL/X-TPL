# syntax=docker/dockerfile:1.6
FROM ubuntu:22.04

# ---------- build args ----------
ARG NODE_VERSION=18
ARG JDK_VERSION=17
ARG DEBIAN_FRONTEND=noninteractive

# ---------- env ----------
ENV ANDROID_HOME=/opt/android
ENV ANDROID_SDK_ROOT=/opt/android
ENV GRADLE_USER_HOME=/tmp/gradle
ENV PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:/usr/local/bin:$PATH"

RUN mkdir -p /opt/gradle

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
ENV JAVA_HOME=/usr/lib/jvm/java-${JDK_VERSION}-openjdk-amd64
ENV PATH="$JAVA_HOME/bin:$PATH"
RUN java -version

# ---------- install node ----------
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - && \
    apt-get update && apt-get install -y nodejs && \
    npm install -g yarn cordova && \
    rm -rf /var/lib/apt/lists/*

RUN node -v && npm -v && yarn -v && cordova -v

# ---------- install modern gradle ----------
RUN curl -s "https://get.sdkman.io?ci=true&rcupdate=false" | bash
RUN bash -c " \
    source /root/.sdkman/bin/sdkman-init.sh && \
    sdk install gradle 8.5 && \
    ln -s /root/.sdkman/candidates/gradle/current/bin/gradle /usr/bin/gradle \
    "

RUN gradle -v
# ---------- android sdk ----------
RUN mkdir -p $ANDROID_HOME/cmdline-tools && \
    curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip \
    -o /tmp/cmdline-tools.zip && \
    unzip /tmp/cmdline-tools.zip -d $ANDROID_HOME/cmdline-tools && \
    mv $ANDROID_HOME/cmdline-tools/cmdline-tools $ANDROID_HOME/cmdline-tools/latest && \
    rm /tmp/cmdline-tools.zip

# ---------- accept licenses ----------
RUN yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses

# ---------- install android packages ----------
RUN $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager \
    "platform-tools" \
    "platforms;android-33" \
    "platforms;android-34" \
    "platforms;android-35" \
    "platforms;android-36" \
    "build-tools;33.0.2" \
    "build-tools;34.0.0" \
    "build-tools;35.0.0" \
    "build-tools;36.0.0"

ENV GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.parallel=false"

# ---------- workdir ----------
WORKDIR /app
