import csv
import subprocess
import pathlib
import threading
import time
import yaml
import os
from concurrent.futures import ThreadPoolExecutor, as_completed


def normalize_path(path) -> str:
    return str(pathlib.Path(path).as_posix())


def run(cmd, log_file: pathlib.Path, check=True, timeout=7200):
    with log_file.open("a") as f:
        f.write("\n> " + " ".join(cmd) + "\n")

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            f.write("\nERROR: Command timed out\n")
            raise

        f.write(result.stdout)

        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd)


def load_manifest(root: pathlib.Path):
    with open(root / "build_manifest.yaml") as f:
        return yaml.safe_load(f)["apps"]


def image_exists(tag: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


_CSV_LOCK = threading.Lock()


def record_build(csv_path: pathlib.Path, repo: str, config: str, success: bool, duration: float):
    with _CSV_LOCK:
        write_header = not csv_path.exists()
        with csv_path.open("a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["repo", "config", "success", "duration_seconds"])
            writer.writerow([repo, config, success, round(duration, 1)])


def run_builds(build_fn, apps, output_dir: pathlib.Path):
    output_dir.mkdir(exist_ok=True)
    max_parallel = max(1, (os.cpu_count() or 2) // 2)

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = [pool.submit(build_fn, app) for app in apps]

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"[executor error] {e}")
