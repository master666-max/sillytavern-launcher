package io.github.master666max.sillytavern;

import android.content.Context;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.HashMap;
import java.util.Map;

/**
 * Materializes the proot runtime from APK assets into app-private storage and
 * builds the proot command line / environment for the bundled Node server.
 */
public final class RuntimeProvision {

    static final String[] RUNTIME_ASSETS = {
            "proot", "loader", "loader32", "libtalloc.so.2", "libandroid-shmem.so"};
    static final int ST_PORT = 8000;

    private RuntimeProvision() {
    }

    public static File runtimeDir(Context ctx) {
        return new File(ctx.getFilesDir(), "runtime");
    }

    public static File rootfsDir(Context ctx) {
        return new File(ctx.getFilesDir(), "rootfs");
    }

    public static File logFile(Context ctx) {
        return new File(ctx.getFilesDir(), "st.log");
    }

    /** Extracts runtime binaries from assets/runtime/* on first run. */
    public static void provision(Context ctx) throws IOException {
        File dir = runtimeDir(ctx);
        if (!dir.isDirectory() && !dir.mkdirs() && !dir.isDirectory()) {
            throw new IOException("cannot create runtime dir: " + dir);
        }
        for (String asset : RUNTIME_ASSETS) {
            File target = new File(dir, asset);
            if (target.isFile() && target.length() > 0) {
                continue;
            }
            try (InputStream in = ctx.getAssets().open("runtime/" + asset);
                    OutputStream out = new FileOutputStream(target)) {
                byte[] buf = new byte[16384];
                int n;
                while ((n = in.read(buf)) > 0) {
                    out.write(buf, 0, n);
                }
            }
            if (!target.setExecutable(true, false) || !target.setReadable(true, false)
                    || !target.setWritable(true, false)) {
                throw new IOException("cannot chmod runtime binary " + target);
            }
        }
        // rename shim lives inside the rootfs tree, referenced by NODE_OPTIONS;
        // .cjs because SillyTavern's package.json sets "type": "module"
        File fix = new File(new File(rootfsDir(ctx), "opt/st"), "rename-fix.cjs");
        if (!fix.isFile()) {
            try (InputStream in = ctx.getAssets().open("rename-fix.cjs");
                    OutputStream out = new FileOutputStream(fix)) {
                byte[] buf = new byte[16384];
                int n;
                while ((n = in.read(buf)) > 0) {
                    out.write(buf, 0, n);
                }
            }
        }
    }

    /** Pure builder, unit-testable without an Android device.
     *  Note: termux proot 5.1 has no "--" end-of-options separator.
     *  node runs niced so a weak host's UI thread never starves (ANR). */
    public static String[] prootCommand(File rootfsDir, File runtimeDir) {
        return new String[]{
                new File(runtimeDir, "proot").getAbsolutePath(),
                "-r", rootfsDir.getAbsolutePath(),
                "-0",
                "-w", "/opt/st",
                "--kill-on-exit",
                "-b", "/dev",
                "-b", "/proc",
                "-b", "/sys",
                "/usr/bin/nice", "-n", "10",
                "/usr/local/bin/node", "/opt/st/server.js",
        };
    }

    /** Pure builder, unit-testable without an Android device. */
    public static Map<String, String> prootEnv(File runtimeDir, File cacheDir) {
        Map<String, String> env = new HashMap<>();
        env.put("PROOT_LOADER", new File(runtimeDir, "loader").getAbsolutePath());
        env.put("PROOT_LOADER_32", new File(runtimeDir, "loader32").getAbsolutePath());
        env.put("PROOT_TMP_DIR", cacheDir.getAbsolutePath());
        // PROOT_NO_SECCOMP is deliberately NOT set: proot's seccomp fast path
        // lets non-path syscalls skip the ptrace stop entirely, which matters
        // a lot for the chat-save I/O chain. If a device rejects filter
        // installation proot logs a warning and still runs.
        env.put("LD_LIBRARY_PATH", runtimeDir.getAbsolutePath());
        env.put("HOME", "/opt/st");
        env.put("TMPDIR", cacheDir.getAbsolutePath());
        env.put("PATH", "/usr/local/bin:/usr/bin:/bin");
        env.put("LANG", "C.UTF-8");
        // zygote seccomp (targetSdk 28) denies renameat2; shim it for node
        env.put("NODE_OPTIONS", "--require /opt/st/rename-fix.cjs");
        // server plugins installed on-device hit the npm mirror
        env.put("NPM_CONFIG_REGISTRY", "https://registry.npmmirror.com");
        return env;
    }

    // ── v1.2 experimental track: bionic (termux-node) runtime, no proot ──

    public static File bionicDir(Context ctx) {
        return new File(rootfsDir(ctx), "opt/bionic");
    }

    public static boolean bionicAvailable(Context ctx) {
        File node = new File(bionicDir(ctx), "bin/node");
        return node.isFile() && node.canExecute();
    }

    /** Pure builder for the no-proot launch: node runs directly on bionic. */
    public static String[] bionicCommand(File rootfsDir, File bionicDir) {
        return new String[]{
                new File(bionicDir, "bin/node").getAbsolutePath(),
                new File(new File(rootfsDir, "opt/st"), "server.js").getAbsolutePath(),
        };
    }

    /** Pure builder, unit-testable without an Android device. */
    public static Map<String, String> bionicEnv(File rootfsDir, File bionicDir, File cacheDir) {
        Map<String, String> env = new HashMap<>();
        File st = new File(rootfsDir, "opt/st");
        env.put("LD_LIBRARY_PATH", new File(bionicDir, "lib").getAbsolutePath());
        env.put("PATH", new File(bionicDir, "bin").getAbsolutePath() + ":/system/bin");
        env.put("HOME", st.getAbsolutePath());
        env.put("TMPDIR", cacheDir.getAbsolutePath());
        env.put("LANG", "C.UTF-8");
        // same renameat2/fsync shim, now addressed by its real path
        env.put("NODE_OPTIONS", "--require " + new File(st, "rename-fix.cjs").getAbsolutePath());
        env.put("NPM_CONFIG_REGISTRY", "https://registry.npmmirror.com");
        // V8 compile cache: ST's server module graph is re-parsed on every
        // boot; the on-disk cache (populated on first run) skips that work.
        env.put("NODE_COMPILE_CACHE", new File(cacheDir, "v8-compile-cache").getAbsolutePath());
        // the frontend bundle ships prebuilt; skip the per-boot webpack run
        env.put("ST_SKIP_WEBPACK", "1");
        return env;
    }
}
