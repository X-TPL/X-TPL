# Errors
C/C++: CMake Error in /app/node_modules/react-native-screens/android/src/main/jni/CMakeLists.txt:
C/C++:   Imported target "ReactAndroid::reactnative" includes non-existent path
C/C++:     "/opt/gradle/caches/8.14.3/transforms/e7c5cf7bb7113a9cd8af3df63ab4ec8f/transformed/react-android-0.81.4-debu>
C/C++:   in its INTERFACE_INCLUDE_DIRECTORIES.  Possible reasons include:
C/C++:   * The path was deleted, renamed, or moved to another location.
C/C++:   * An install or uninstall procedure did not complete successfully.
C/C++:   * The installation package was faulty and references files it does not
C/C++:   provide.
C/C++: CMake Error in /app/node_modules/react-native-worklets/android/build/generated/source/codegen/jni/CMakeLists.txt:
C/C++:   Imported target "fbjni::fbjni" includes non-existent path
C/C++:     "/opt/gradle/caches/8.14.3/transforms/57eed124da95de5e0d0e6329b95f862e/transformed/fbjni-0.7.0/prefab/module>
C/C++:   in its INTERFACE_INCLUDE_DIRECTORIES.  Possible reasons include:
C/C++:   * The path was deleted, renamed, or moved to another location.
C/C++:   * An install or uninstall procedure did not complete successfully.
C/C++:   * The installation package was faulty and references files it does not
C/C++:   provide.
C/C++: CMake Generate step failed.  Build files cannot be regenerated correctly.
C/C++: ninja: error: rebuilding 'build.ninja': subcommand failed

Error: [android.dangerous]: withAndroidDangerousBaseMod: Cannot copy google-services.json from /app/google-services.json to /app/android/app/google-services.json. Ensure the source and destination paths exist.
Error: [android.dangerous]: withAndroidDangerousBaseMod: Cannot copy google-services.json from /app/google-services.json to /app/android/app/google-services.json. Ensure the source and destination paths exist.
at setGoogleServicesFile (/app/node_modules/@expo/config-plugins/build/android/GoogleServices.js:100:11)
at async /app/node_modules/@expo/config-plugins/build/android/GoogleServices.js:81:5
at async action (/app/node_modules/@expo/config-plugins/build/plugins/withMod.js:199:23)
at async interceptingMod (/app/node_modules/@expo/config-plugins/build/plugins/withMod.js:104:21)
at async interceptingMod (/app/node_modules/@expo/config-plugins/build/plugins/withMod.js:104:21)
at async interceptingMod (/app/node_modules/@expo/config-plugins/build/plugins/withMod.js:104:21)
at async action (/app/node_modules/@expo/config-plugins/build/plugins/createBaseMod.js:60:21)
at async interceptingMod (/app/node_modules/@expo/config-plugins/build/plugins/withMod.js:104:21)
at async evalModsAsync (/app/node_modules/@expo/config-plugins/build/plugins/mod-compiler.js:206:25)
at async compileModsAsync (/app/node_modules/@expo/config-plugins/build/plugins/mod-compiler.js:123:10)



FAILURE: Build failed with an exception.

* Where:
Settings file '/app/android/settings.gradle' line: 3

* What went wrong:
A problem occurred evaluating settings 'android'.
> Process 'command 'npx'' finished with non-zero exit value 1

# Values

directories: 483
built: 167

try2: 
directories: 327
built: 170

try3:
crawled: 1020
downloaded:
build entries: 490
built: 258

typescript:
crawled: 1020
downloaded: 
build entries:787
built: 315

# typescript

build entries: 566
apks: 1062
repos built: 213
split not working: 6

try2:
apks: 1329
repos built: 208
split not working: still 6
r8 not working: 73
1 FastComments-fastcomments-react-native-sdk/
1 Leogendra-Pixood/
1 callstack-react-native-pager-view/
1 funnyzak-react-native-v2ex/
1 uiwjs-react-native-uiw/
1 zhbhun-react-native-intersection-observer/

try3: 
apks: 1371
repos built: 211
split not working: 5
r8 not working: 69

try4:
apks: 1467
repos built: 224
