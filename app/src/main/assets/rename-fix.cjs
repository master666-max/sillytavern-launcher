// Android's zygote seccomp policy (targetSdk 28) returns ENOSYS for the
// renameat2 syscall, which modern libuv uses to implement fs.rename.
// Loaded via NODE_OPTIONS=--require before SillyTavern boots: retry the
// native call once and, on ENOSYS, emulate it with copy + unlink.
// Additionally: fs.fsync is stubbed out. write-file-atomic fsyncs every chat
// save, which over proot's ptrace tax means a real flash-sync stall per
// message on top of the copy+unlink emulation. Durability is traded for
// responsiveness on purpose (single-user toy server, battery-powered device).
// .cjs on purpose: SillyTavern's package.json sets "type": "module".
"use strict";

const fs = require("fs");

function isEnosys(e) {
    return e && (e.code === "ENOSYS" || e.errno === -38);
}

// fsync/fdatasync: pretend the data hit the disk immediately.
fs.fsync = function (fd, cb) {
    if (typeof cb === "function") process.nextTick(cb, null);
};
fs.fsyncSync = function () {};

const origRenameSync = fs.renameSync;
fs.renameSync = function (src, dest) {
    try {
        return origRenameSync.call(fs, src, dest);
    } catch (e) {
        if (!isEnosys(e)) throw e;
        fs.copyFileSync(src, dest);
        fs.unlinkSync(src);
    }
};

const origRename = fs.rename;
fs.rename = function (src, dest, cb) {
    if (typeof cb !== "function") {
        return origRename.call(fs, src, dest, cb);
    }
    origRename.call(fs, src, dest, function (err) {
        if (!isEnosys(err)) return cb(err);
        fs.copyFile(src, dest, function (e2) {
            if (e2) return cb(e2);
            fs.unlink(src, function (e3) {
                cb(e3 && e3.code === "ENOENT" ? null : e3);
            });
        });
    });
};

const origPRename = fs.promises.rename;
fs.promises.rename = async function (src, dest) {
    try {
        return await origPRename.call(fs.promises, src, dest);
    } catch (e) {
        if (!isEnosys(e)) throw e;
        await fs.promises.copyFile(src, dest);
        await fs.promises.unlink(src);
    }
};
