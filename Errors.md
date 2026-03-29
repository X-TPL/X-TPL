AppFlowy : Groovy Version (Probably) => cant find pubspec ??
abuanwarDashboard : The current Dart SDK version is 3.4.0. Because admin requires SDK version >=3.5.0 <4.0.0, version solving failed.  

fluffychat: The current Dart SDK version is 3.4.0. Because fluffychat requires SDK version >=3.10.0 <4.0.0, version solving failed.

CarGuo-gsy: The current Dart SDK version is 3.4.0. Because gsy_github_app_flutter requires SDK version >=3.8.0 <4.0.0, version solving failed. => need Dart 3.9.0

abuanwarShopToolkit: The current Dart SDK version is 2.15.0.Because stylish requires SDK version >=2.15.1 <3.0.0, version solving failed. => wrong gradle version

maxkrieger: The current Dart SDK version is 2.12.0. Because voice_outliner depends on flutter_launcher_icons >=0.12.0 which requires SDK version >=2.18.0 <3.0.0 or >=3.0.0 <4.0.0, => still the same


abuanwar072-Responsive-and-Animated-Portfolio-Flutter: Gradle Arguments dont match, perhaps gradle Version => still the same

miru_app: The current Dart SDK version is 3.0.0.Because miru_app requires SDK version >=3.0.3 <4.0.0, version solving failed. => needs 3.2

JideSocial: Gradle Version (confirmed)

bagisto_app: The current Dart SDK version is 3.0.0.Because bagisto_app_demo requires SDK version >=3.0.1 <4.0.0, version solving failed. needs 3.5

Flutter-tiktok: The current Dart SDK version is 3.0.0.Because flutter_tiktok depends on video_player >=2.8.1 which requires SDK version >=3.1.0 <4.0.0, version solving failed. => needs 3.2.3

KRito: Unable to find image 'flutter-android:3.29.0-jdk17' locally
docker: Error response from daemon: pull access denied for flutter-android, repository does not exist or may require 'docker login'

nisrulz: Gradle Task doesnt exist => worked but produced error

liso-Vault:Because liso depends on secrets from path which doesn't exist (could not find package secrets at "../secrets"), version solving failed. => still the same

polkawallet: The current Dart SDK version is 2.9.0.Because app requires SDK version >=2.10.0 <3.0.0, version solving failed. => same

evan930923: Git error => same

grocery_app: The current Dart SDK version is 2.12.0. Because grocery_app depends on url_launcher >=6.0.11 which requires SDK version >=2.14.0 <4.0.0, version solving failed. => same

shinuchlei: The current Dart SDK version is 2.9.0.Because flutter_app requires SDK version >=2.10.0 <3.0.0, version solving failed. => same



badgemagic: file missing => same

tankste: The current Dart SDK version is 3.0.0. Because no versions of flutter_lints match >6.0.0 <7.0.0 and flutter_lints 6.0.0 requires SDK version ^3.8.0, flutter_lints ^6.0.0 is f => same

toly9o32i490: incorrect pubspec? => needs 3.6.1 (instead of 3.5.0)

abu-E-Commerce-UI: The current Dart SDK version is 3.4.0. Because shop_app requires SDK version >=3.5.0 <4.0.0, version solving failed. => gradle/ parent folder

humhub: The current Dart SDK version is 3.4.0.Because humhub requires SDK version >=3.6.0 <4.0.0, version solving failed. => pull access denied

venera: The current Dart SDK version is 3.4.0.Because venera requires SDK version >=3.8.0 <4.0.0, version solving failed. => needs flutter 3.38.5   

## fixed
jon-fritter: The current Flutter SDK version is 3.3.0.  Because fritter depends on extended_nested_scroll_view >=6.0.0 which requires Flutter SDK version >=3.7.0, version solving failed.

dwyl-app: gradle Version (probably)

UploadGram-app: built successfully

## fixed with upper bound
TheAlphamerc: docker pull Access denied => same


## with retry
citizenwallet: The current Dart SDK version is 3.0.0. Because flutter_lints 5.0.0 requires SDK version ^3.5.0 and no versions of flutter_lints match >5.0.0 <6.0.0, flutter_lints ^5.0.0 is forbidden. => still the same => requires .env

olmps-memo: The current Flutter SDK version is 2.10.0. Because memo requires Flutter SDK version >=2.10.3, version solving failed. => still the same => incompatible gradle version

JideEbook: The current Flutter SDK version is 3.10.0. Because flutter_ebook_app depends on auto_route >=7.8.2 which requires Flutter SDK version >=3.13.0, version solving failed. =>requires parent directory => still same

WHO: .apk created but couldnt be found => same => same

firebase: The current Dart SDK version is 3.2.0.Because firebase_core >=4.4.0 depends on firebase_core_web >=2.18.0 which requires SDK version >=3.4.0 <4.0.0, firebase_core >=4.4.0 is => needs 3.3 now => Could not read script '/android/local-config.gradle' as it does not exist.

hiddify: Probably gradle Version => same => pinned version that doesnt work



## failing Docker builds
3.26 & 3.29 & 3.38

## bad pubspecs
vyuh-tech-vyuh: declares workspace but workspace doesnt exist
trufi-association
## wrong flutter versions

mo7amedaliEbaid-flutter_webview_template
PSDTools-app
Dragon863-myrunshaw
zapstore
fahim

## Tools

To count apks: find . -name *.apk | wc -l
To count directories: ls -l | grep -c ^d
To count directories with apks: for d in */; do
  find "$d" -name "*.apk" -print -quit | grep -q . && echo "$d"
done | wc -l
To find directories without apk: for d in */; do
  ls "$d"*.apk >/dev/null 2>&1 || echo "$d"
done

To count files with a certain word: grep -rl "SAXParseException" /path/to/folder | wc -l

To delete dictionaries with a certain keyword: grep -rl "npm error" . | xargs -n1 dirname | sort -u |
 xargs rm -r

To delete all dictionaries with an apk: find . -type f -name "*.apk" -exec dirname {} \; | sort -u | xargs rm -rf

## values

25.02. 36/79
26.02. 43/79

Repos: 1020
downloaded: 901
entries: 897
built: 470