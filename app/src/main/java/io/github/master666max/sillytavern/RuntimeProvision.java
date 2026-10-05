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
        env.put("PROOT_NO_SECCOMP", "1");
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
}
