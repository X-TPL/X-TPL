# Fragen
- Current work in welche Richtung? Im Moment Richtung TPL Detection bei Android Apps, aber die Datensammlung ist auch ein grosser Teil der Arbeit => Auch dort Nachforschung notwendig?
=> nein, erklärung reicht

- Muss begründet werden, welche Suchparameter Beispielsweise bei Github verwendet werden, oder reicht es anzumerken was verwendet wurde?
=> nein, reicht anzumerken was verwendet wird

- Soll ein Fat APK gebuildet werden, oder nur eine plattform?
=> fat APK, sonst arm64. Wenn möglich splitten.



# Resultate
- Links zu Repos/Zips sollen persistiert werden, damit zurückverfolgt werden kann, woher Daten kommen
- Überprüfen ob bei Flutter Android builds ein android Folder zwingend vorhanden sein muss
- Überprüfen ob es effizienter ist, das pubspec in Github direkt zu suchen, oder ob es mit Ratelimit besser ist, es wie bisher zu machen
- Release oder debug build spielt keine Rolle, evtl. ist debug mode besser da kein Zertifikat nötig
- Logs persistieren, um am Ende kategorisieren zu können
- Evtl. List Command verwenden um Sicher zu sein, dass Versionen der Libraries korrekt sind.

# Tipps
- Codeberg und Gitlab als quellen für open source Repos
- Proguard/r8 als einzige Obfuscation. Überprüfen, dass nur diese verwendet wird. 2 APKs (einmal obfuscated, und einmal ohne)
- APK-Tool & Jadx zum überprüfen der APKs
- Wichtigstes Paper 2025_Revisiting_Third-Party_Library_Detection, lesen und anpassen
