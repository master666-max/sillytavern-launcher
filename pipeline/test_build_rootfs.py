import io
import os
import tarfile
import tempfile
import unittest


def _make_members():
    members = []

    d = tarfile.TarInfo("dir")
    d.type = tarfile.DIRTYPE
    d.mode = 0o755
    members.append(d)

    f = tarfile.TarInfo("dir/file.txt")
    payload = b"hello rootfs"
    f.size = len(payload)
    f.mode = 0o644
    members.append((f, payload))

    link = tarfile.TarInfo("dir/link")
    link.type = tarfile.SYMTYPE
    link.linkname = "file.txt"
    link.mode = 0o777
    members.append(link)

    hard = tarfile.TarInfo("dir/hard")
    hard.type = tarfile.LNKTYPE
    hard.linkname = "dir/file.txt"  # tar 根相对
    hard.mode = 0o644
    members.append(hard)

    longname = tarfile.TarInfo("dir/" + "l" * 150 + ".txt")
    longname.size = 3
    longname.mode = 0o644
    members.append((longname, b"abc"))
    return members


def _write_tar(path, members, mode="w:gz"):
    with tarfile.open(path, mode, format=tarfile.GNU_FORMAT) as tf:
        for m in members:
            if isinstance(m, tuple):
                tf.addfile(m[0], io.BytesIO(m[1]))
            else:
                tf.addfile(m)


class TarMergerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tar_a = os.path.join(self.tmp, "a.tar.gz")
        self.tar_b = os.path.join(self.tmp, "b.tar.xz")
        _write_tar(self.tar_a, _make_members(), "w:gz")
        b = tarfile.TarInfo("pkg/bin/app")
        b.size = 4
        b.mode = 0o755
        with tarfile.open(self.tar_b, "w:xz", format=tarfile.GNU_FORMAT) as tf:
            tf.addfile(b, io.BytesIO(b"exec"))

    def _merged_names(self):
        from pipeline.build_rootfs import TarMerger

        out = os.path.join(self.tmp, "out.tar.gz")
        merger = TarMerger(out)
        merger.add_tarball(self.tar_a, strip_components=0, prefix="opt/x")
        merger.add_tarball(self.tar_b, strip_components=1, prefix="opt/y")
        merger.close()

        import gzip

        raw = gzip.decompress(open(out, "rb").read())
        assert raw[257:265] == b"ustar  \x00", "output must be GNU tar format"
        with tarfile.open(out, "r:gz") as tf:
            return {m.name: m for m in tf.getmembers()}, out

    def test_names_and_prefixes(self):
        byname, out = self._merged_names()
        self.assertIn("opt/x/dir/file.txt", byname)
        self.assertIn("opt/y/bin/app", byname)
        self.assertIn("opt/x/dir/" + "l" * 150 + ".txt", byname)

    def test_symlink_and_hardlink_rewritten(self):
        byname, _ = self._merged_names()
        self.assertEqual(byname["opt/x/dir/link"].type, tarfile.SYMTYPE)
        self.assertEqual(byname["opt/x/dir/link"].linkname, "file.txt")
        self.assertEqual(byname["opt/x/dir/hard"].type, tarfile.LNKTYPE)
        self.assertEqual(byname["opt/x/dir/hard"].linkname, "opt/x/dir/file.txt")

    def test_metadata_normalized(self):
        byname, _ = self._merged_names()
        for name in ("opt/x/dir/file.txt", "opt/y/bin/app"):
            self.assertEqual(byname[name].uid, 0)
            self.assertEqual(byname[name].gid, 0)
            self.assertEqual(byname[name].mtime, 0)
        self.assertEqual(byname["opt/y/bin/app"].mode & 0o777, 0o755)

    def test_dev_nodes_skipped(self):
        from pipeline.build_rootfs import TarMerger

        chrdev = tarfile.TarInfo("dev/nullish")
        chrdev.type = tarfile.CHRTYPE
        chrdev.devmajor, chrdev.devminor = 1, 3
        out = os.path.join(self.tmp, "out2.tar.gz")
        merger = TarMerger(out)
        merger.add_tarball(self.tar_a, strip_components=0, prefix="opt/x")
        merger.add_dir("dev", mode=0o755)
        merger.close()
        with tarfile.open(out, "r:gz") as tf:
            names = [m.name for m in tf.getmembers()]
        self.assertNotIn("dev/nullish", names)
        self.assertIn("dev", names)


if __name__ == "__main__":
    unittest.main()
