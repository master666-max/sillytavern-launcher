"""Generate the small GNU tar.gz fixture used by TarReaderTest (JVM unit test).

Contents: dir/, dir/file.txt, symlink dir/link -> file.txt,
hardlink dir/hard -> dir/file.txt, a >100-char longname file, binary blob.
"""
import io
import os
import tarfile

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "app", "src", "test", "resources", "fixture.tar.gz")


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    members = []

    d = tarfile.TarInfo("dir")
    d.type = tarfile.DIRTYPE
    d.mode = 0o755
    members.append(d)

    f = tarfile.TarInfo("dir/file.txt")
    f.size = 5
    f.mode = 0o644
    members.append((f, b"hello"))

    lnk = tarfile.TarInfo("dir/link")
    lnk.type = tarfile.SYMTYPE
    lnk.linkname = "file.txt"
    lnk.mode = 0o777
    members.append(lnk)

    hard = tarfile.TarInfo("dir/hard")
    hard.type = tarfile.LNKTYPE
    hard.linkname = "dir/file.txt"
    hard.mode = 0o644
    members.append(hard)

    longf = tarfile.TarInfo("dir/" + "long" * 40 + ".dat")
    longf.size = 16
    longf.mode = 0o600
    members.append((longf, bytes(range(16))))

    ex = tarfile.TarInfo("dir/run.sh")
    ex.size = 8
    ex.mode = 0o755
    members.append((ex, b"#!/bin/sh"))

    with tarfile.open(OUT, "w:gz", format=tarfile.GNU_FORMAT) as tf:
        for m in members:
            if isinstance(m, tuple):
                tf.addfile(m[0], io.BytesIO(m[1]))
            else:
                tf.addfile(m)
    print("written:", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
