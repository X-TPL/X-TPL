# Versioning

Android 14 uses Java 17
Android 13 and 12 use Java 11
https://developer.android.com/build/jdks

# Flutter/Dart Version
https://docs.flutter.dev/install/archive
contains a table

# Splitting APKs

Removing the --split-per-abi flag results in a fat APK that contains your code compiled for all the target ABIs. Such APKs are larger in size than their split counterparts, causing the user to download native binaries that aren't applicable to their device's architecture. 

# Obfuscation

R8 is the new code shrinker from Google. It's enabled by default when you build a release APK or AAB. To disable R8, pass the --no-shrink flag to flutter build apk or flutter build appbundle.
Note

Obfuscation and minification can considerably extend the compile time of an Android application.

The --[no-]shrink flag has no effect. Code shrinking is always enabled in release builds. To learn more, check out Shrink, obfuscate, and optimize your app.

# Data
970 repos deemed buildable (not all got downloaded)
Generated 865 build entries.
3719 apks
436 folders with an apk
71 do not have obfuscated results

# prod 
Saved 1752 entries to repos.json
Collected 1663 buildable repos
downloaded: 1662 repos
analyzed: Generated 1522 build entries.