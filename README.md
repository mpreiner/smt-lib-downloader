# SMT-LIB Zenodo Downloader

A small, dependency-free Python script for downloading [SMT-LIB](https://smt-lib.org/)
benchmark archives from a [Zenodo](https://zenodo.org/) record.

SMT-LIB releases on Zenodo store one archive per logic, named
`<LOGIC>.tar.zst` (e.g. `QF_BV.tar.zst`). This script can list the available
logics or download all / a selected subset of them, verifying each file's MD5
checksum against the one published by Zenodo.

## Requirements

- Python 3.6+ (standard library only — nothing to install)
- For `--extract`: the `zstd` and `tar` programs on your `PATH`

## Usage

```
smtlib_download.py [-h] [-l] [--logics LOGIC [LOGIC ...]] [-o OUTPUT_DIR] [-x] url
```

The Zenodo record URL is the only required argument; a bare record id works too.

| Option | Description |
| --- | --- |
| `url` | Zenodo record URL, e.g. `https://zenodo.org/records/16740866` |
| `-l`, `--list` | List the available logics (with sizes) and exit |
| `--logics LOGIC [...]` | Only download these logics (default: all) |
| `-o`, `--output-dir DIR` | Directory to download into (default: current directory) |
| `-x`, `--extract` | Extract each archive after download (requires `zstd` and `tar`) |
| `-h`, `--help` | Show the help message and exit |

## Examples

List the logics in a record:

```sh
./smtlib_download.py --list https://zenodo.org/records/16740866
```

Download every logic into `./benchmarks`:

```sh
./smtlib_download.py -o benchmarks https://zenodo.org/records/16740866
```

Download only specific logics:

```sh
./smtlib_download.py --logics QF_BV QF_LIA -o benchmarks https://zenodo.org/records/16740866
```

Download and extract every logic:

```sh
./smtlib_download.py --extract -o benchmarks https://zenodo.org/records/16740866
```

## Behavior notes

- **Resumable runs.** Each file is streamed to a `.part` temporary file and
  atomically renamed once complete. Files that are already fully downloaded
  (matched by size) are skipped on a re-run.
- **Checksum verification.** When Zenodo publishes an `md5:` checksum, the MD5
  is computed while downloading and compared before the file is committed to its
  final name. Skipped (already-present) files are re-verified too. A mismatch
  aborts without overwriting so the next run retries cleanly. If no checksum is
  published for a file, verification is skipped with a notice.
- **Extraction.** With `--extract`, each `.tar.zst` archive is unpacked into the
  output directory after it is downloaded and verified. The archive is left in
  place (delete it yourself if you only want the extracted files). Extraction
  shells out to `zstd` piped into `tar`, so those programs must be installed;
  the archive is *not* decompressed in Python.
- **Errors.** An unknown logic name (see `--list`) or a failed API request exits
  with a non-zero status and a message on stderr.
