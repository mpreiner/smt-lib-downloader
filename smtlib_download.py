#!/usr/bin/env python3
"""Download SMT-LIB benchmark files from a Zenodo record.

SMT-LIB releases on Zenodo store one archive per logic, named
``<LOGIC>.tar.zst`` (e.g. ``QF_BV.tar.zst``).  This script can list the
available logics or download all / a selected subset of them.

Examples
--------
List the logics in a record::

    ./smtlib_download.py --list https://zenodo.org/records/16740866

Download every logic into ./benchmarks::

    ./smtlib_download.py -o benchmarks https://zenodo.org/records/16740866

Download only two logics::

    ./smtlib_download.py --logics QF_BV QF_LIA https://zenodo.org/records/16740866

Download and extract every logic::

    ./smtlib_download.py --extract -o benchmarks https://zenodo.org/records/16740866
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

API = "https://zenodo.org/api/records/{}"


def record_id(url):
    """Extract the numeric record id from a Zenodo URL (or a bare id)."""
    m = re.search(r"(\d+)", url)
    if not m:
        sys.exit(f"error: could not find a record id in {url!r}")
    return m.group(1)


def fetch_files(url):
    """Return the record's files as a dict {logic: file-metadata}."""
    api_url = API.format(record_id(url))
    try:
        with urllib.request.urlopen(api_url) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"error: failed to fetch {api_url}: {e}")

    files = {}
    for f in data.get("files", []):
        key = f["key"]
        logic = re.sub(r"\.tar\.zst$", "", key)
        files[logic] = f
    return files


def human(n):
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


def md5sum(path):
    """Return the hex MD5 digest of a file, read in chunks."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_md5(meta):
    """Return the record's MD5 hex digest, or None if not an md5 checksum."""
    checksum = meta.get("checksum", "")
    if checksum.startswith("md5:"):
        return checksum[len("md5:"):]
    return None


def verify(path, want_md5, key):
    """Compare a file's MD5 against the Zenodo checksum (if available)."""
    if want_md5 is None:
        print(f"       no md5 checksum published for {key}, skipping verification")
        return
    got = md5sum(path)
    if got == want_md5:
        print(f"       md5 ok  {got}")
    else:
        sys.exit(f"error: md5 mismatch for {key}\n"
                 f"       expected {want_md5}\n"
                 f"       got      {got}")


def extract(path, dest_dir):
    """Extract a .tar.zst archive into dest_dir using zstd + tar.

    Decompressing with the ``zstd`` program and piping the plain tar stream
    into ``tar`` avoids relying on tar's built-in zstd support, which varies
    between platforms.
    """
    name = os.path.basename(path)
    print(f"       extracting {name}")
    dec = subprocess.Popen(["zstd", "-dc", path], stdout=subprocess.PIPE)
    tar = subprocess.Popen(["tar", "-xf", "-", "-C", dest_dir], stdin=dec.stdout)
    dec.stdout.close()  # allow dec to get SIGPIPE if tar exits early
    tar.wait()
    dec.wait()
    if dec.returncode != 0 or tar.returncode != 0:
        sys.exit(f"error: extraction of {name} failed")


def download(meta, dest_dir):
    """Download one file, skipping it if it is already complete.

    Returns the path to the downloaded archive.
    """
    key = meta["key"]
    size = meta.get("size", 0)
    want_md5 = expected_md5(meta)
    # Zenodo exposes the download link under links.self.
    href = meta.get("links", {}).get("self")
    dest = os.path.join(dest_dir, key)

    if os.path.exists(dest) and size and os.path.getsize(dest) == size:
        print(f"  skip {key} (already downloaded)")
        verify(dest, want_md5, key)
        return dest

    print(f"  get  {key} ({human(size)})")
    tmp = dest + ".part"
    h = hashlib.md5()
    with urllib.request.urlopen(href) as resp, open(tmp, "wb") as out:
        downloaded = 0
        while True:
            chunk = resp.read(1 << 20)  # 1 MiB
            if not chunk:
                break
            out.write(chunk)
            h.update(chunk)
            downloaded += len(chunk)
            if size:
                pct = downloaded * 100 // size
                print(f"\r       {pct:3d}%  {human(downloaded)}", end="", flush=True)
        print()

    # Verify before committing the .part file to its final name.
    if want_md5 is None:
        print(f"       no md5 checksum published for {key}, skipping verification")
    elif h.hexdigest() == want_md5:
        print(f"       md5 ok  {h.hexdigest()}")
    else:
        os.remove(tmp)
        sys.exit(f"error: md5 mismatch for {key}\n"
                 f"       expected {want_md5}\n"
                 f"       got      {h.hexdigest()}")
    os.replace(tmp, dest)
    return dest


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url", help="Zenodo record URL, e.g. https://zenodo.org/records/16740866")
    p.add_argument("-l", "--list", action="store_true",
                   help="list available logics and exit")
    p.add_argument("--logics", nargs="+", metavar="LOGIC",
                   help="only download these logics (default: all)")
    p.add_argument("-o", "--output-dir", default=".",
                   help="directory to download into (default: current directory)")
    p.add_argument("-x", "--extract", action="store_true",
                   help="extract each archive after download (requires zstd and tar)")
    args = p.parse_args()

    if args.extract:
        for tool in ("zstd", "tar"):
            if shutil.which(tool) is None:
                sys.exit(f"error: --extract requires the {tool!r} program, "
                         f"which was not found on PATH")

    files = fetch_files(args.url)
    if not files:
        sys.exit("error: no files found in this record")

    if args.list:
        for logic in sorted(files):
            print(f"{logic:30s} {human(files[logic].get('size', 0)):>12s}")
        print(f"\n{len(files)} logics available")
        return

    if args.logics:
        selected = {}
        for logic in args.logics:
            if logic not in files:
                sys.exit(f"error: logic {logic!r} not in record "
                         f"(use --list to see available logics)")
            selected[logic] = files[logic]
    else:
        selected = files

    os.makedirs(args.output_dir, exist_ok=True)
    total = sum(f.get("size", 0) for f in selected.values())
    print(f"Downloading {len(selected)} logic(s), {human(total)} total, "
          f"into {args.output_dir!r}")
    for logic in sorted(selected):
        archive = download(selected[logic], args.output_dir)
        if args.extract and archive.endswith(".tar.zst"):
            extract(archive, args.output_dir)
    print("done")


if __name__ == "__main__":
    main()
