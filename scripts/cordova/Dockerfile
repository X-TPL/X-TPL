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
    if [ \"$JDK_VERSION\" = \"8\" ]; then \
    echo 'Installing Gradle 6.5 for JDK 8'; \
    sdk install gradle 6.5; \
    else \
    echo 'Installing Gradle 8.5 for modern JDK'; \
    sdk install gradle 8.5; \
    fi && \
    ln -sf /root/.sdkman/candidates/gradle/current/bin/gradle /usr/bin/gradle \
    "

RUN gradle -v
# ---------- android sdk ----------
RUN mkdir -p $ANDROID_HOME/cmdline-tools && \
    if [ "$JDK_VERSION" = "8" ]; then \
    SDK_VERSION=6609375; \
    elif [ "$JDK_VERSION" = "11" ]; then \
    SDK_VERSION=9477386; \
    else \
    SDK_VERSION=11076708; \
    fi && \
    echo "Using Android cmdline-tools $SDK_VERSION for JDK $JDK_VERSION" && \
    curl -4 -fsSL \
    https://dl.google.com/android/repository/commandlinetools-linux-${SDK_VERSION}_latest.zip \
    -o /tmp/cmdline-tools.zip && \
    unzip /tmp/cmdline-tools.zip -d $ANDROID_HOME/cmdline-tools && \
    \
    if [ -d "$ANDROID_HOME/cmdline-tools/cmdline-tools" ]; then \
    mv $ANDROID_HOME/cmdline-tools/cmdline-tools $ANDROID_HOME/cmdline-tools/latest; \
    elif [ -d "$ANDROID_HOME/cmdline-tools/tools" ]; then \
    mv $ANDROID_HOME/cmdline-tools/tools $ANDROID_HOME/cmdline-tools/latest; \
    else \
    echo "Unexpected cmdline-tools structure" && exit 1; \
    fi && \
    rm /tmp/cmdline-tools.zip

# ---------- accept licenses ----------
RUN yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses

# ---------- install android packages ----------
RUN echo "Installing full Android SDK (modern)"; \
    $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager \
    "platform-tools" \
    "platforms;android-29" \
    "platforms;android-30" \
    "platforms;android-31" \
    "platforms;android-32" \
    "platforms;android-33" \
    "platforms;android-34" \
    "platforms;android-35" \
    "platforms;android-36" \
    "build-tools;29.0.3" \
    "build-tools;30.0.3" \
    "build-tools;31.0.0" \
    "build-tools;32.0.0" \
    "build-tools;33.0.2" \
    "build-tools;34.0.0" \
    "build-tools;35.0.0" \
    "build-tools;36.0.0";

ENV GRADLE_OPTS="-Dorg.gradle.daemon=false -Dorg.gradle.parallel=false"
ENV ORG_GRADLE_PROJECT_org.gradle.jvmargs="-Xmx2g -XX:MaxMetaspaceSize=512m -Dfile.encoding=UTF-8"

# ---------- workdir ----------
WORKDIR /app
