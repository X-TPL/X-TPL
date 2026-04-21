// Injected at build time by the orchestrator.
// Placed in Assets/Editor/ so Unity compiles it as an Editor-only assembly.
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;

public static class BuildScript
{
    // ---- scene discovery ----

    static string[] GetScenes()
    {
        // 1. Use whatever is enabled in Build Settings
        var configured = EditorBuildSettings.scenes
            .Where(s => s.enabled)
            .Select(s => s.path)
            .ToArray();

        if (configured.Length > 0)
            return configured;

        // 2. Fallback: first .unity asset found in the project
        var fallback = AssetDatabase.FindAssets("t:Scene")
            .Select(guid => AssetDatabase.GUIDToAssetPath(guid))
            .Take(1)
            .ToArray();

        return fallback;
    }

    // ---- debug build (Mono, all common ABIs, no minification) ----

    public static void BuildDebug()
    {
        PlayerSettings.Android.useCustomKeystore = false;
        EditorUserBuildSettings.buildAppBundle = false;

        PlayerSettings.SetScriptingBackend(
            BuildTargetGroup.Android, ScriptingImplementation.Mono2x);
        PlayerSettings.Android.targetArchitectures =
            AndroidArchitecture.ARMv7 | AndroidArchitecture.ARM64;

        var opts = new BuildPlayerOptions
        {
            scenes            = GetScenes(),
            locationPathName  = "/output/app-debug.apk",
            target            = BuildTarget.Android,
            options           = BuildOptions.Development,
        };

        RunBuild(opts, "debug");
    }

    // ---- release builds (IL2CPP + R8, one APK per ABI) ----

    public static void BuildRelease()
    {
        PlayerSettings.Android.useCustomKeystore = true;
        PlayerSettings.Android.keystoreName  = "/root/.android/debug.keystore";
        PlayerSettings.Android.keystorePass  = "android";
        PlayerSettings.Android.keyaliasName  = "androiddebugkey";
        PlayerSettings.Android.keyaliasPass  = "android";
        EditorUserBuildSettings.buildAppBundle = false;

        PlayerSettings.SetScriptingBackend(
            BuildTargetGroup.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.SetManagedStrippingLevel(
            BuildTargetGroup.Android, ManagedStrippingLevel.Medium);

        BuildForArch(AndroidArchitecture.ARMv7,  "armeabi-v7a");
        BuildForArch(AndroidArchitecture.ARM64,  "arm64-v8a");
        BuildForArch(AndroidArchitecture.X86,    "x86");
        BuildForArch(AndroidArchitecture.X86_64, "x86_64");
    }

    static void BuildForArch(AndroidArchitecture arch, string abiLabel)
    {
        PlayerSettings.Android.targetArchitectures = arch;

        var opts = new BuildPlayerOptions
        {
            scenes           = GetScenes(),
            locationPathName = "/output/r8/app-release-" + abiLabel + ".apk",
            target           = BuildTarget.Android,
            options          = BuildOptions.None,
        };

        RunBuild(opts, "release-" + abiLabel);
    }

    // ---- shared runner ----

    static void RunBuild(BuildPlayerOptions opts, string label)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(opts.locationPathName)
                                  ?? "/output");

        Console.WriteLine("[BuildScript] starting " + label);
        BuildReport report = BuildPipeline.BuildPlayer(opts);

        if (report.summary.result == BuildResult.Succeeded)
        {
            Console.WriteLine("[BuildScript] " + label + " succeeded: "
                              + report.summary.outputPath);
        }
        else
        {
            Console.Error.WriteLine("[BuildScript] " + label + " FAILED: "
                                    + report.summary.result);
            EditorApplication.Exit(1);
        }
    }
}
