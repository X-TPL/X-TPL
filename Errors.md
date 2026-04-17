ERROR: R8: java.lang.IllegalArgumentException: Provided Metadata instance has version 2.1.0, while maximum supported ted version is 2.0.0. To support newer versions, update the kotlinx-metadata-jvm library.

> A failure occurred while executing com.android.build.gradle.tasks.PackageAndroidArtifact$IncrementalSplitterRunnab>
> SigningConfig "release" is missing required property "storeFile".

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

only build.log: grep -rl "SAXParseException" /path/to/folder --include="build.log" | wc -l


To delete dictionaries with a certain keyword: grep -rl "npm error" . | xargs -n1 dirname | sort -u |
 xargs rm -r

To delete all dictionaries with an apk: find . -type f -name "*.apk" -exec dirname {} \; | sort -u | xargs rm -rf

To find folders with less than 3 apks in the main dir: for d in */; do count=$(find "$d" -maxdepth 1 -name "*.apk" | wc -l); [ "$count" -gt 0 ] && [ "$count" -lt 3 ] && echo "$count $d"; done

To find folders with less than 9 apks (recursively): for d in */; do count=$(find "$d" -name "*.apk" | wc -l); [ "$count" -gt 0 ] && [ "$count" -lt 9 ] && echo "$count $d"; done


## values

25.02. 36/79
26.02. 43/79

Repos: 1020
downloaded: 901
entries: 897
built: 470