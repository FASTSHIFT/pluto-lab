# pluto-lab

> SDR tools for the ADALM-PLUTO: spectrum scanning, FM/AM demodulation, ADS-B
> decoding and a tar1090 web frontend.

Windows friendly. Every decoder is hand-written in numpy instead of pulling in
dump1090 or GNU Radio, so each layer stays small enough to read, change and test.
For the map UI we reuse [tar1090](https://github.com/wiedehopf/tar1090) rather
than reinventing it.

```
PlutoSDR --+
HackRF   --+--> sdr/ (shared core) --> messages / IQ --> tools/<one tool> --> plot / audio / web
IQ file  --+
```

## Layout

```
sdr/                 shared core, no UI and no tool-specific logic
  modes.py             Mode S / ADS-B: CRC, PPM slicing, CPR, message parsing
  source.py            Pluto capture + realtime decode loop (only pyadi-iio user)
  geo.py               Web Mercator and WGS-84 <-> GCJ-02
  paths.py             libiio DLL / vendor package paths

tools/               one directory per tool; tools never import each other
  adsb/
    cli.py             command line ADS-B receiver
    web.py             HTTP backend that feeds tar1090
  spectrum/
    scan.py            band sweep + peak table + FM/AM demodulation

scripts/             environment and developer tooling
  setup_windows.py     download the libiio binaries
  fetch_tar1090.py     download tar1090 and apply local patches
  check_commit_msg.py  commit message rules (hooks and CI share this)
  check_no_chinese.py  reject CJK characters in sources
  check_file_lines.py  per-file line limit
  ci_local.sh          run every CI check locally
  install_hooks.sh/.ps1

tests/               unit tests, none of them need radio hardware
.githooks/           commit-msg / pre-commit
.github/workflows/   CI
```

### Boundaries

Tools multiply over time (satellite imagery, 433 MHz sensors, 2.4 GHz heatmaps).
These rules are enforced by `tests/test_architecture.py`, not by good intentions:

1. `tools/<a>` must not import `tools/<b>`
2. shared code lives in `sdr/`
3. `sdr/` must not import `tools/` or `scripts/`

Break any of them and CI fails.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate           # Windows; source .venv/bin/activate elsewhere
pip install -e ".[full]"
python scripts/setup_windows.py  # libiio.dll
python scripts/fetch_tar1090.py  # optional web UI

python tools/adsb/cli.py --selftest
sh scripts/install_hooks.sh      # once per clone
```

## Tools

### Spectrum and audio

```bash
python tools/spectrum/scan.py info
python tools/spectrum/scan.py scan --preset wide          # 85-180 MHz
python tools/spectrum/scan.py scan --start 118 --stop 137 # airband
python tools/spectrum/scan.py fm --freq 94.5 --seconds 12 --out station.wav
python tools/spectrum/scan.py am --freq 121.5 --seconds 10
```

Each sweep step keeps the middle 65% of its band and overlaps the next one by
35%, so filter roll-off and LO spurs at the edges never reach the stitched plot.

### ADS-B

```bash
python tools/adsb/cli.py --seconds 60
python tools/adsb/web.py --lat 40.0689 --lon 116.3072
# open http://127.0.0.1:8080/
```

Antenna: use 20.6 cm (3/4 lambda) or 6.9 cm (1/4 lambda) at 1090 MHz. A 1.2 m
whip is 4.4 wavelengths there and will not work.

## Development

### Commit messages

Conventional Commits, English only. Enforced by the `commit-msg` hook and again
by CI:

```
type(scope): summary

type   : feat | fix | test | refactor | chore | docs | style | perf | build | ci | revert
scope  : optional, lowercase, e.g. (adsb), (spectrum), (ci)
summary: imperative, no trailing period, <= 100 chars
text   : ASCII only - any non-ASCII character is rejected
```

### Before pushing

```bash
sh scripts/ci_local.sh
```

It runs: byte-compile, `ruff check`, `ruff format --check`, the CJK scanner, the
line-count limit, `pytest` with an 85% coverage gate, the workflow syntax check,
and the commit message validator.

### Windows: use Git Bash

The shell scripts and hooks are POSIX. PowerShell treats stderr from native
commands as errors and defaults to GBK, so the output is confusing there. The
hooks still work from PowerShell because git runs them with its own `sh`.

### Adding a tool

```bash
mkdir tools/satellite
# write tools/satellite/apt.py, importing only from sdr/
# add a section to this README
```

No other tool changes, and no change to `sdr/` unless a genuinely shared
capability is missing.

## Known issues

**1. Dependency pins matter**

```
pyadi-iio==0.0.21
pylibiio==0.25
```

`pylibiio` 1.0 targets the libiio v1.x API and fails against the 0.25 DLL with
`Could not find libiio C library`.

**2. Only DF17/DF18 are decoded**

DF11/DF4/DF5 checksums are XORed with the aircraft address; we do not do that,
so the frame rate is lower than dump1090. Callsign, altitude, velocity and
position all live in DF17, which is enough for the map.

**3. LO spurs look like signals**

The AD9361 fractional divider produces spurs at LO +/- 1 MHz. To tell a spur
from a real signal, retune and compare: a real emitter does not move with the LO.

**4. Map datum**

AMap tiles are GCJ-02 while ADS-B reports WGS-84. `tools/adsb/web.py` converts
by default (receiver position included, so distances stay correct). Pass
`--no-gcj` for WGS-84 basemaps such as OSM or ESRI.

## Verification

The decoder is checked against public reference frames, not against itself:

| Sample | Expected |
|---|---|
| `8D4840D6202CC371C32CE0576098` | callsign KLM1023 |
| `8D40621D58C382D690C8AC2863A7` | 38000 ft |
| that frame + odd pair `...86435CC412692AD6` | 52.25720, 3.91937 |

```bash
python -m pytest -q tests
```

## License

MIT. tar1090 is GPL-2.0 and is downloaded at runtime by
`scripts/fetch_tar1090.py`; it is not part of this repository.
