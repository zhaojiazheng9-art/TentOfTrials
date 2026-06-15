#!/usr/bin/env python3

import argparse
import datetime
import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent

@dataclass
class Module:
    name: str
    language: str
    dir: Path
    build_cmd: list[str]
    clean_cmd: list[str]
    build_dir: Optional[Path] = None
    env: Optional[dict[str, str]] = None

MODULES = [
    Module(
        name="backend",
        language="Rust",
        dir=ROOT / "backend",
        build_cmd=["cargo", "build"],
        clean_cmd=["cargo", "clean"],
        build_dir=ROOT / "backend" / "target",
        env={"CARGO_TERM_COLOR": "always"},
    ),
    Module(
        name="frontend",
        language="TypeScript",
        dir=ROOT / "frontend",
        build_cmd=["npm", "run", "build"],
        clean_cmd=["rm", "-rf", "node_modules", "dist"],
        build_dir=ROOT / "frontend" / "dist",
        env={"NODE_ENV": "production"},
    ),
    Module(
        name="market",
        language="Go",
        dir=ROOT / "market",
        build_cmd=["go", "build", "-o", "market", "."],
        clean_cmd=["rm", "-f", "market"],
        build_dir=ROOT / "market" / "market",
    ),
    Module(
        name="frailbox",
        language="C",
        dir=ROOT / "frailbox",
        build_cmd=["make"],
        clean_cmd=["make", "distclean"],
        build_dir=ROOT / "frailbox" / "frailbox",
    ),
    Module(
        name="engine",
        language="C++",
        dir=ROOT / "frailbox" / "engine",
        build_cmd=["cmake", "--build", "build"],
        clean_cmd=["rm", "-rf", "build"],
        build_dir=ROOT / "frailbox" / "engine" / "build" / "trial-engine",
    ),
    Module(
        name="compliance",
        language="Java",
        dir=ROOT / "compliance",
        build_cmd=["javac", "-d", "build", "ComplianceAuditor.java"],
        clean_cmd=["rm", "-rf", "build"],
        build_dir=ROOT / "compliance" / "build",
    ),
    Module(
        name="v2-market-stream",
        language="Ruby",
        dir=ROOT / "v2" / "services",
        build_cmd=["ruby", "-c", "market_stream.rb"],
        clean_cmd=["echo", "Ruby has no build artifacts to clean"],
        build_dir=None,
    ),
    Module(
        name="nfc-scanner",
        language="Lua",
        dir=ROOT / "frailbox" / "nfc",
        build_cmd=["luac", "-p", "scanner.lua"],
        clean_cmd=["echo", "Lua has no build artifacts to clean"],
        build_dir=None,
    ),
    Module(
        name="openapi-haskell",
        language="Haskell",
        dir=ROOT / "docs" / "openapi",
        build_cmd=["ghc", "-fno-code", "Types.hs", "Server.hs", "Validate.hs", "Generate.hs"],
        clean_cmd=["rm", "-f", "*.hi", "*.o", "*.hie"],
        build_dir=None,
    ),
    Module(
        name="openapi-tools",
        language="Lua",
        dir=ROOT / "tools",
        build_cmd=["luac", "-p", "openapi_diff.lua", "openapi_mock.lua", "openapi_pact.lua"],
        clean_cmd=["echo", "Nothing to clean"],
        build_dir=None,
    ),
]

ENCRYPTLY_BIN = ROOT / "tools" / "encryptly" / "encryptly"

class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    GRAY = "\033[90m"

def color(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{code}{text}{Colors.RESET}"

def check_prerequisites() -> list[str]:
    required = {
        "cargo": "Rust",
        "npm": "Node.js",
        "go": "Go",
        "gcc": "C (GCC)",
        "g++": "C++ (GCC)",
        "cmake": "CMake",
        "make": "Make",
        "python3": "Python",
        "javac": "Java (JDK)",
        "ruby": "Ruby",
        "luac": "Lua",
        "ghc": "GHC (Haskell)",
    }

    missing = []
    for cmd, label in required.items():
        if shutil.which(cmd) is None:
            missing.append(f"{label} ({cmd})")

    return missing

def build_module(
    module: Module,
    release: bool = False,
    verbose: bool = False,
) -> tuple[bool, float, str]:

    print(f"\n  {color('▸', Colors.CYAN)} Building {color(module.name, Colors.BOLD)} ({module.language})...")

    env = os.environ.copy()
    if module.env:
        env.update(module.env)

    start = time.time()

    if module.name == "frontend":
        node_modules = module.dir / "node_modules"
        if not node_modules.exists():
            print(f"       {color('npm install...', Colors.GRAY)}")
            try:
                install_result = subprocess.run(
                    ["npm", "install"],
                    cwd=str(module.dir),
                    capture_output=not verbose,
                    text=True,
                    timeout=120,
                    env={k: v for k, v in env.items() if k != "NODE_ENV"},
                )
                if install_result.returncode != 0:
                    return False, time.time() - start, f"npm install failed:\n{install_result.stderr}"
            except subprocess.TimeoutExpired:
                return False, time.time() - start, "npm install TIMEOUT (120s)"

    if module.name == "engine":

        build_type = "Release" if release else "Debug"
        cfg_result = subprocess.run(
            ["cmake", "-S", ".", "-B", "build",
             f"-DCMAKE_BUILD_TYPE={build_type}"],
            cwd=str(module.dir),
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if cfg_result.returncode != 0:
            return False, time.time() - start, (
                f"CMake configure failed:\n{cfg_result.stderr}")
        if verbose:
            print(f"       {color('cmake configured', Colors.GRAY)}")
        cmd = ["cmake", "--build", "build"]
        if release:
            cmd.append("--config")
            cmd.append("Release")
    else:
        cmd = list(module.build_cmd)
        if release and module.name == "backend":
            cmd.append("--release")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(module.dir),
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return False, time.time() - start, "BUILD TIMEOUT (300s)"
    except FileNotFoundError as e:
        return False, 0, f"Command not found: {e}"

    elapsed = time.time() - start
    output_lines = []

    if result.stdout:
        output_lines.append(result.stdout.strip())
    if result.stderr:
        output_lines.append(result.stderr.strip())

    output = "\n".join(output_lines)
    success = result.returncode == 0

    return success, elapsed, output

def clean_module(module: Module, verbose: bool = False) -> bool:
    print(f"  {color('▸', Colors.YELLOW)} Cleaning {module.name}...")
    try:
        subprocess.run(
            module.clean_cmd,
            cwd=str(module.dir),
            capture_output=not verbose,
            text=True,
            timeout=60,
            env=os.environ.copy(),
        )
        return True
    except Exception as e:
        print(f"    {color('✗', Colors.RED)} Clean failed: {e}")
        return False

def verify_binary(module: Module) -> Optional[str]:
    if module.build_dir is None:
        return None
    path = module.build_dir
    if module.name == "backend":

        target = path / "debug" / module.name
        if not target.exists():
            target = path / "release" / module.name
        if target.exists():
            return str(target)
    if path.exists():
        return str(path)
    return None

def run_cmd(cmd: list[str], **kwargs) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, **kwargs
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return result.returncode == 0, output.strip()
    except Exception as e:
        return False, str(e)


def collect_system_info() -> str:
    lines = [
        "Tent of Trials - System Diagnostic Snapshot",
        "=" * 50,
        f"generated_at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        f"hostname: {platform.node()}",
        f"user: {getpass.getuser()}",
        f"python: {sys.version}",
        f"platform: {platform.platform()}",
        f"processor: {platform.processor() or 'unknown'}",
        f"cpu_count: {os.cpu_count()}",
        "",
        "--- uname ---",
    ]
    ok, out = run_cmd(["uname", "-a"])
    lines.append(out if ok else "unavailable")

    lines.extend(["", "--- /etc/os-release ---"])
    try:
        lines.append((Path("/etc/os-release")).read_text(encoding="utf-8", errors="replace").strip())
    except Exception as e:
        lines.append(f"unavailable: {e}")

    lines.extend(["", "--- memory ---"])
    ok, out = run_cmd(["free", "-h"])
    lines.append(out if ok else "unavailable")

    lines.extend(["", "--- disk ---"])
    ok, out = run_cmd(["df", "-h"])
    lines.append(out if ok else "unavailable")

    lines.extend(["", "--- build environment ---"])
    for key in ["SHELL", "LANG", "TERM", "XDG_SESSION_TYPE", "DISPLAY", "EDITOR"]:
        value = os.environ.get(key)
        if value:
            lines.append(f"{key}={value}")

    lines.append("")
    return "\n".join(lines)


def generate_logd(
    results: list[tuple[str, bool, float, str, Optional[str]]],
    verbose: bool = False,
) -> bool:
    print(f"\n  {color('▸', Colors.CYAN)} Generating {color('build.logd', Colors.BOLD)}...")

    if not ENCRYPTLY_BIN.exists():
        print(f"    {color('✗', Colors.RED)} encryptly binary not found at {ENCRYPTLY_BIN}; cannot create build.logd")
        return False

    # Workspace must live under $HOME because encryptly refuses paths outside home.
    home = Path.home()
    workspace = home / ".cache" / "tent-of-trials" / "logd-workspace"
    safe_dir = workspace / "safe"
    logd_path = ROOT / "build.logd"

    try:
        shutil.rmtree(workspace, ignore_errors=True)
        safe_dir.mkdir(parents=True, exist_ok=True)

        (safe_dir / "system-info.txt").write_text(
            collect_system_info(), encoding="utf-8"
        )

        summary_lines = [
            "Tent of Trials - Build Summary",
            "=" * 50,
            f"generated_at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
            f"total_modules: {len(results)}",
            f"passed: {sum(1 for _, s, _, _, _ in results if s)}",
            f"failed: {sum(1 for _, s, _, _, _ in results if not s)}",
            "",
            "module results:",
        ]
        for name, success, elapsed, _, binary in results:
            summary_lines.append(
                f"  {name}: {'PASS' if success else 'FAIL'} ({elapsed:.2f}s)"
                f"{f' [{binary}]' if binary else ''}"
            )
        (safe_dir / "build-summary.txt").write_text(
            "\n".join(summary_lines), encoding="utf-8"
        )

        log_lines = []
        for name, success, elapsed, output, binary in results:
            log_lines.append(
                f"\n{'=' * 50}\n{name} ({'PASS' if success else 'FAIL'}, {elapsed:.2f}s)\n"
                f"{'=' * 50}"
            )
            if binary:
                log_lines.append(f"artifact: {binary}")
            if output:
                log_lines.append(output)
        (safe_dir / "build.log").write_text("\n".join(log_lines), encoding="utf-8")

        # Single encryptly call — auto-generates safe_pw, creates sensitive.enc
        # internally with HMAC-SHA256("Lobster$4R", safe_pw), then packs
        # workspace + sensitive.enc into build.logd using safe_pw.
        sr = subprocess.run(
            [
                str(ENCRYPTLY_BIN),
                "pack",
                str(logd_path),
                "--include",
                str(workspace),
                "--max-file-size",
                "0",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if sr.returncode != 0:
            print(
                f"    {color('✗', Colors.RED)} build.logd creation failed: "
                f"{sr.stderr.strip() or sr.stdout.strip()}"
            )
            if logd_path.exists():
                logd_path.unlink()
            return False

        safe_pw = sr.stdout.strip()
        size_kb = logd_path.stat().st_size / 1024.0
        print(
            f"    {color('✓', Colors.GREEN)} {logd_path.name} created "
            f"({size_kb:.1f} KiB)"
        )
        if safe_pw:
            print()
            print(f"  {color('═' * 60, Colors.GRAY)}")
            print(f"  {color('PASSWORD', Colors.BOLD)}  —  copy this to decrypt:")
            print(f"  {color(safe_pw, Colors.CYAN)}")
            print(f"  {color('═' * 60, Colors.GRAY)}")
            print()
            print(f"  {color(f'encryptly unpack {logd_path} <outdir> --password {safe_pw}', Colors.GRAY)}")
        return True

    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def print_summary(results: list[tuple[str, bool, float, str, Optional[str]]]):
    print(f"\n{color('═' * 60, Colors.GRAY)}")
    print(f"  {color('BUILD SUMMARY', Colors.BOLD)}")
    print(f"{color('═' * 60, Colors.GRAY)}")

    total = len(results)
    passed = sum(1 for _, s, _, _, _ in results if s)
    failed = total - passed
    total_time = sum(t for _, _, t, _, _ in results)

    for name, success, elapsed, output, binary in results:
        status_icon = color("✓", Colors.GREEN) if success else color("✗", Colors.RED)
        status_text = color("PASS", Colors.GREEN) if success else color("FAIL", Colors.RED)
        time_str = f"{elapsed:.1f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"

        print(f"\n  {status_icon}  {color(name + ':', Colors.BOLD)} {status_text}  ({time_str})")
        if binary:
            print(f"       artifact: {color(binary, Colors.GRAY)}")
        if not success and output:

            lines = output.strip().split("\n")
            print(f"       {color('last output:', Colors.RED)}")
            for line in lines[-5:]:
                print(f"       {color(line, Colors.GRAY)}")

    print(f"\n  {color('─' * 40, Colors.GRAY)}")
    print(f"  {color('Total:', Colors.BOLD)} {total} modules, "
          f"{color(str(passed) + ' passed', Colors.GREEN)}, "
          f"{color(str(failed) + ' failed', Colors.RED)}, "
          f"{total_time:.1f}s total")

def main():
    parser = argparse.ArgumentParser(
        description="Tent of Trials  -  Multi-Language Build System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 build.py                    Build all modules
  python3 build.py -m backend         Build only backend
  python3 build.py -m frontend,market Build frontend and market
  python3 build.py --clean            Clean all artifacts
  python3 build.py --release          Release build (Rust only)
  python3 build.py --verbose          Verbose output

Diagnostic bundle:
  python3 build.py
        """,
    )
    parser.add_argument(
        "-m", "--module",
        help="Module(s) to build (comma-separated, or 'all')",
        default="all",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Clean build artifacts instead of building",
    )
    parser.add_argument(
        "--release", action="store_true",
        help="Build in release mode (Rust backend)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show detailed build output",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List available modules and exit",
    )

    args = parser.parse_args()

    print(f"\n  {color('TENT OF TRIALS  -  Build System', Colors.CYAN)}")
    print(f"  {color(f'v0.1.0 | Python {sys.version.split()[0]}', Colors.GRAY)}")
    print(f"  Working directory: {ROOT}")
    print()

    if args.list:
        print(f"  {color('Available modules:', Colors.BOLD)}")
        for m in MODULES:
            print(f"    {color(m.name, Colors.CYAN)} ({m.language})")
            print(f"      dir: {m.dir.relative_to(ROOT)}")
            print(f"      build: {' '.join(m.build_cmd)}")
        return 0

    print(f"  {color('Checking prerequisites...', Colors.GRAY)}")
    missing = check_prerequisites()
    if missing:
        print(f"\n  {color('⚠ Some tools missing  -  will try anyway:', Colors.YELLOW)}")
        for m in missing:
            print(f"    {m}")
        print(f"  {color('Not all modules will build. That\'s fine. We note the failures.', Colors.GRAY)}")
    else:
        print(f"  {color('✓ All prerequisites found', Colors.GREEN)}")

    if args.module == "all":
        selected = MODULES
    else:
        names = [n.strip() for n in args.module.split(",")]
        selected = [m for m in MODULES if m.name in names]
        not_found = set(names) - {m.name for m in MODULES}
        if not_found:
            print(f"  {color('✗ Unknown modules:', Colors.RED)} {', '.join(not_found)}")
            print(f"    Available: {', '.join(m.name for m in MODULES)}")
            return 1

    if not selected:
        print(f"  No modules selected.")
        return 0

    if args.clean:
        print(f"\n  {color('Cleaning build artifacts...', Colors.YELLOW)}")
        for module in selected:
            clean_module(module, args.verbose)
        logd = ROOT / "build.logd"
        if logd.exists():
            if logd.is_dir():
                shutil.rmtree(logd)
            else:
                logd.unlink()
            print(f"  {color('▸', Colors.YELLOW)} Removed build.logd")
        print(f"\n  {color('Clean complete.', Colors.GREEN)}")
        return 0

    print(f"\n  {color(f'Building {len(selected)} module(s) | release={args.release}', Colors.GRAY)}")

    results: list[tuple[str, bool, float, str, Optional[str]]] = []

    for module in selected:
        success, elapsed, output = build_module(module, args.release, args.verbose)
        binary = verify_binary(module) if success else None
        results.append((module.name, success, elapsed, output, binary))

    print_summary(results)

    if args.module == "all":
        generate_logd(results, args.verbose)

    return 0 if all(r[1] for r in results) else 1

if __name__ == "__main__":
    sys.exit(main())
