"""Push local commits to GitHub via the gh API (bypasses git/443 blocking).

Walks `git diff --name-only origin/main HEAD`, uploads blobs, builds a tree,
creates a commit, and fast-forwards refs/heads/main.
"""
import base64
import json
import subprocess
import sys

REPO = "master666-max/sillytavern-launcher"


def gh(*args, input_bytes=None):
    cmd = ["gh", "api", *args, "--input", "-"]
    r = subprocess.run(cmd, capture_output=True, check=False,
                       input=input_bytes)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {args[:3]} failed: {r.stderr.decode(errors='replace')[:400]}")
    return json.loads(r.stdout)


def main():
    remote_ref = gh(f"repos/{REPO}/git/ref/heads/main")
    base_sha = remote_ref["object"]["sha"]
    base_commit = gh(f"repos/{REPO}/git/commits/{base_sha}")
    base_tree = base_commit["tree"]["sha"]
    print(f"remote main @ {base_sha[:10]} tree {base_tree[:10]}")

    diff = subprocess.run(["git", "diff", "--name-only", "origin/main", "HEAD"],
                          capture_output=True, check=True, text=True).stdout.split()
    if not diff:
        print("nothing to push")
        return

    tree_items = []
    for path in diff:
        with open(path, "rb") as f:
            content = f.read()
        blob = gh(f"repos/{REPO}/git/blobs", "-X", "POST",
                  input_bytes=json.dumps({
                      "content": base64.b64encode(content).decode(),
                      "encoding": "base64"}).encode())
        tree_items.append({"path": path, "mode": "100644",
                           "type": "blob", "sha": blob["sha"]})
        print(f"blob {path} ({len(content)} B)")

    tree = gh(f"repos/{REPO}/git/trees", "-X", "POST",
              input_bytes=json.dumps({"base_tree": base_tree,
                                      "tree": tree_items}).encode())
    msg = subprocess.run(["git", "log", "-1", "--pretty=%B", "HEAD"],
                         capture_output=True, check=True, text=True).stdout.strip()
    local_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                               check=True, text=True).stdout.strip()
    commit = gh(f"repos/{REPO}/git/commits", "-X", "POST",
                input_bytes=json.dumps({
                    "message": f"{msg}\n(local commit {local_sha[:10]})",
                    "tree": tree["sha"], "parents": [base_sha]}).encode())
    gh(f"repos/{REPO}/git/refs/heads/main", "-X", "PATCH",
       input_bytes=json.dumps({"sha": commit["sha"], "force": False}).encode())
    print(f"pushed {commit['sha'][:10]} -> main")


if __name__ == "__main__":
    sys.exit(main())
