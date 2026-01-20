Check for these files/directories:

pubspec.yaml

android/

ios/

lib/main.dart

Outcomes:
Case A: You see android/ and lib/

→ Almost certainly a Flutter app

Case B: You see pubspec.yaml but no android/

→ Dart package or plugin → not directly buildable as APK

Case C: No pubspec.yaml

→ Not a Dart app in a buildable sense → stop

Sequence:
git clone <repo>
cd <repo>
flutter pub get
flutter build apk --debug