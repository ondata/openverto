"""The `grid` command: lattice, respect for the service, and PROJ/GDAL output.

`fixtures/grid_4265_6706.json` holds real IGM responses, recorded once, so that
this suite never calls the service. PROJ and GDAL are skipped when absent, except
in CI.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from openverto import base
from openverto import grid as g
from openverto.base import VertoError
from openverto.cli import app

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "grid_4265_6706.json").read_text())
BBOX = (11.0, 43.5, 12.0, 44.0)
NODES = [tuple(c) for c in FIXTURE["nodes"]]
NODES_OUT = dict(zip(NODES, [tuple(c) for c in FIXTURE["nodes_out"]]))
runner = CliRunner()


def need(tool: str) -> None:
    if shutil.which(tool) is None:
        if os.environ.get("CI"):
            pytest.fail(f"{tool} is required in CI")
        pytest.skip(f"{tool} not installed")


class Service:
    """Replays the fixture; `failures` are raised in order before answering."""

    def __init__(self, failures=()):
        self.failures = list(failures)
        self.batches: list[list] = []
        self.retries: list[int] = []

    def __call__(self, in_epsg, out_epsg, batch, *, retries=2):
        self.batches.append(list(batch))
        self.retries.append(retries)
        if self.failures:
            failure = self.failures.pop(0)
            if failure is not None:
                raise failure
        return [NODES_OUT[c] for c in batch]


@pytest.fixture
def run(monkeypatch, tmp_path):
    """Return a `build_grid` wrapper over a fake service, recording the sleeps."""

    def _run(service, max_coord=20, pause=2.0):
        sleeps: list[float] = []
        monkeypatch.setattr(g, "_convert_chunk", service)
        report = g.build_grid(
            g.build_lattice(BBOX), 4265, 6706, tmp_path / "g.tif",
            max_coord=max_coord, pause=pause, cache_dir=tmp_path / "cache", sleep=sleeps.append,
        )
        return report, sleeps

    return _run


@pytest.fixture
def no_network(monkeypatch):
    def refuse(**kwargs):
        raise AssertionError("the service must not be called")

    monkeypatch.setattr(base.httpx, "Client", refuse)


def report_of(tmp_path) -> dict:
    return json.loads((tmp_path / "g.tif.report.json").read_text())


# --------------------------------------------------------------------------- #
# lattice and systems
# --------------------------------------------------------------------------- #
def test_default_step_over_italy():
    lattice = g.build_lattice((6.0, 35.0, 19.0, 47.5))
    assert (lattice.nx, lattice.ny, lattice.size) == (104, 151, 15704)
    assert lattice.lon(0) == pytest.approx(6.0773333333) and lattice.lat(150) == 47.5


def test_igm_step_lands_on_the_igm_nodes():
    lattice = g.build_lattice((11.3, 43.9, 11.5, 44.1))
    assert lattice.lon(0) == pytest.approx(11.3273333333)  # first node of the official file
    assert lattice.lat(1) == 44.0


def test_other_steps_start_from_the_bbox_corner():
    lattice = g.build_lattice((11.2, 43.9, 11.5, 44.1), step_lon=180, step_lat=180)
    assert (lattice.lon(0), lattice.lat(0)) == (11.2, 43.9)


def test_step_that_does_not_divide_stops_inside_the_bbox():
    lattice = g.build_lattice((11.0, 43.5, 11.3, 43.6), origin_lon=11.0, origin_lat=43.5)
    assert lattice.nx == 3 and lattice.lon(2) == 11.25
    assert lattice.ny == 2 and lattice.lat(1) == pytest.approx(43.5833333333)


def test_origin_aligns_the_lattice():
    lattice = g.build_lattice((11.01, 43.51, 11.5, 43.8), origin_lon=11.0, origin_lat=43.5)
    assert lattice.lon(0) == 11.125 and lattice.lat(0) == pytest.approx(43.5833333333)


@pytest.mark.parametrize("bbox", [(12, 43, 11, 44), (11, 44, 12, 43), (11, 43, 11.01, 43.01)])
def test_bad_bbox_rejected(bbox):
    with pytest.raises(g.GridError):
        g.build_lattice(bbox)


@pytest.mark.parametrize(
    "a,b,message",
    [
        (3003, 6706, "projected"),
        (6707, 6706, "no longer accepted"),
        (9999, 6706, "not IGM-supported"),
        (4806, 6706, "Rome meridian"),
        (4670, 4670, "same datum"),
    ],
)
def test_unusable_systems_rejected(a, b, message):
    with pytest.raises(g.GridError, match=message):
        g.check_systems(a, b)


# --------------------------------------------------------------------------- #
# respect for the service
# --------------------------------------------------------------------------- #
def test_batches_follow_max_coord_with_pause_between(run):
    service = Service()
    report, sleeps = run(service, max_coord=20)
    assert [len(b) for b in service.batches] == [20, 20, 16]
    assert sleeps == [2.0, 2.0]
    assert set(service.retries) == {0}  # base.post must not add its own retries
    assert (report["status"], report["requests"], report["nodes_valid"], report["nodes_error"]) == ("ok", 3, 56, 0)


def test_resume_only_sends_what_is_missing(run, tmp_path):
    with pytest.raises(VertoError):
        run(Service([None, VertoError("boom", "Proj")]))
    assert report_of(tmp_path)["nodes_valid"] == 20
    assert not (tmp_path / "g.tif").exists()

    resumed = Service()
    report, _ = run(resumed)
    assert len(resumed.batches) == 2 and report["cached_batches"] == 1

    again = Service()
    report, sleeps = run(again)
    assert again.batches == [] and sleeps == [] and report["requests"] == 0


def test_service_error_is_not_retried(run, tmp_path):
    service = Service([VertoError("Coordinate to transform falls outside grid", "Proj")])
    with pytest.raises(VertoError):
        run(service)
    assert len(service.batches) == 1
    saved = report_of(tmp_path)
    assert saved["status"] == "error" and "outside grid" in saved["error"] and saved["requests"] == 1


def test_network_errors_back_off_then_stop(run, tmp_path):
    service = Service([httpx.ConnectError("down")] * 5)
    with pytest.raises(httpx.ConnectError):
        run(service, max_coord=100)
    assert len(service.batches) == g.MAX_CONSECUTIVE_ERRORS
    assert not (tmp_path / "g.tif").exists()


def test_backoff_doubles_and_success_resets_it(run):
    service = Service([httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow"), None, httpx.ReadTimeout("slow")])
    report, sleeps = run(service, max_coord=40, pause=0.5)
    assert report["status"] == "ok"
    assert sleeps == [2.0, 0.5, 4.0, 0.5, 0.5, 2.0, 0.5]


def test_user_agent_names_project_and_version(monkeypatch):
    seen = []
    real = httpx.Client

    def client(**kwargs):
        def handler(request):
            seen.append(request.headers["User-Agent"])
            return httpx.Response(200, json={"stato": "successo"})

        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(base.httpx, "Client", client)
    base.post({"richiesta": "info"}, retries=0)
    assert seen[0].startswith("openverto/") and "github.com/ondata/openverto" in seen[0]


def test_requests_never_overlap_across_threads(monkeypatch):
    state = {"now": 0, "peak": 0}
    guard = threading.Lock()
    real = httpx.Client

    def client(**kwargs):
        def handler(request):
            with guard:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.02)
            with guard:
                state["now"] -= 1
            return httpx.Response(200, json={"stato": "successo"})

        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(base.httpx, "Client", client)
    threads = [threading.Thread(target=base.post, args=({"richiesta": "info"},), kwargs={"retries": 0}) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert state["peak"] == 1


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
GRID = ["grid", "--from", "4265", "--to", "6706", "--bbox", "11", "43.5", "12", "44"]


def test_dry_run_prints_the_plan_without_calling_the_service(no_network, tmp_path):
    result = runner.invoke(app, ["-o", "json", *GRID, "--dry-run", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "nodes": 56, "nx": 8, "ny": 7, "max_coord": 32000, "batches": 1,
        "cached_batches": 0, "requests": 1, "estimated_seconds": 1,
    }


def test_large_job_needs_yes(no_network, tmp_path):
    big = ["grid", "--from", "4265", "--to", "6706", "--bbox", "6", "35", "19", "47.5", "--step-lon", "60", "--step-lat", "60"]
    result = runner.invoke(app, [*big, "--out", str(tmp_path / "g.tif"), "--cache-dir", str(tmp_path)])
    assert result.exit_code == 2 and "--yes" in result.output
    assert not (tmp_path / "g.tif").exists()


def test_max_coord_comes_from_the_service(monkeypatch, tmp_path):
    service = Service()
    monkeypatch.setattr(g, "_convert_chunk", service)
    monkeypatch.setattr("openverto.cli.lib_info", lambda: {"maxCoord": 30})
    result = runner.invoke(app, ["--output", "json", *GRID, "--out", str(tmp_path / "g.tif"), "--cache-dir", str(tmp_path / "c"), "--pause", "0"])
    assert result.exit_code == 0, result.output
    assert [len(b) for b in service.batches] == [30, 26]
    assert json.loads(result.output)["requests"] == 3  # info + 2 batches


def test_cli_outside_coverage_writes_no_grid(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "_convert_chunk", Service([VertoError("Coordinate to transform falls outside grid", "Proj")]))
    monkeypatch.setattr("openverto.cli.lib_info", lambda: {"maxCoord": 32000})
    result = runner.invoke(app, [*GRID, "--out", str(tmp_path / "g.tif"), "--cache-dir", str(tmp_path / "c")])
    assert result.exit_code == 2 and "smaller" in result.output
    assert not (tmp_path / "g.tif").exists()
    assert report_of(tmp_path)["status"] == "error"


def test_out_is_required(tmp_path):
    assert runner.invoke(app, GRID).exit_code == 2


# --------------------------------------------------------------------------- #
# real PROJ and GDAL on the recorded responses
# --------------------------------------------------------------------------- #
@pytest.fixture
def tif(tmp_path) -> Path:
    path = tmp_path / "grid.tif"
    g.write_gtiff(path, g.build_lattice(BBOX), NODES, [NODES_OUT[c] for c in NODES], 4265, 6706)
    return path


def cct(tif: Path, points) -> list[tuple[float, float]]:
    need("cct")
    text = "".join(f"{e} {n} 0 0\n" for e, n in points)
    done = subprocess.run(["cct", "-d", "11", "+proj=hgridshift", f"+grids={tif}"], input=text, capture_output=True, text=True, check=True)
    return [tuple(float(v) for v in line.split()[:2]) for line in done.stdout.splitlines()]


def metres(a, b) -> float:
    return math.hypot((a[0] - b[0]) * 111320 * math.cos(math.radians(a[1])), (a[1] - b[1]) * 110950)


def test_output_follows_the_umask(tif):
    umask = os.umask(0)
    os.umask(umask)
    assert tif.stat().st_mode & 0o777 == 0o666 & ~umask


def test_gdalinfo_sees_a_proj_grid(tif):
    need("gdalinfo")
    info = json.loads(subprocess.run(["gdalinfo", "-json", str(tif)], capture_output=True, text=True, check=True).stdout)
    assert info["size"] == [8, 7]
    assert [b["description"] for b in info["bands"]] == ["latitude_offset", "longitude_offset"]
    assert {b["unit"] for b in info["bands"]} == {"arc-second"}
    assert all(b["type"] == "Float32" for b in info["bands"])
    meta = info["metadata"][""]
    assert meta["TYPE"] == "HORIZONTAL_OFFSET" and meta["target_crs_epsg_code"] == "6706"
    assert meta["source"] == "IGM Verto Online" and "TIFFTAG_DATETIME" in meta
    assert info["bands"][1]["metadata"][""]["positive_value"] == "east"
    assert 'ID["EPSG",4265]' in info["coordinateSystem"]["wkt"]
    # PixelIsPoint: GDAL shows the node half a step away from the raster corner.
    assert info["geoTransform"][0] == pytest.approx(11.0773333333 - 0.0625)
    assert info["geoTransform"][3] == pytest.approx(44.0 + 2.5 / 60)


def test_proj_matches_verto_on_the_nodes(tif):
    assert max(metres(a, NODES_OUT[n]) for a, n in zip(cct(tif, NODES), NODES)) < 0.001


def test_proj_matches_verto_between_the_nodes(tif):
    expected = [tuple(c) for c in FIXTURE["controls_out"]]
    got = cct(tif, [tuple(c) for c in FIXTURE["controls"]])
    assert len(got) == len(expected) and max(metres(a, b) for a, b in zip(got, expected)) < 0.01


def test_longitude_shift_keeps_its_sign(tif):
    node = NODES[0]
    assert NODES_OUT[node][0] < node[0]  # the recorded shift is westward
    assert cct(tif, [node])[0][0] < node[0]


def test_points_outside_the_grid_are_not_transformed(tif):
    need("cct")
    done = subprocess.run(["cct", "+proj=hgridshift", f"+grids={tif}"], input="13.5 45 0 0\n", capture_output=True, text=True)
    assert "outside grid" in done.stdout + done.stderr


def test_gdalwarp_moves_a_raster_like_proj(tif, tmp_path):
    need("gdalwarp")
    need("gdal_translate")
    need("gdalinfo")
    cell = 0.0001
    asc = tmp_path / "in.asc"
    asc.write_text(f"ncols 10\nnrows 10\nxllcorner 11.5\nyllcorner 43.7\ncellsize {cell}\n" + "1 2 3 4 5 6 7 8 9 0\n" * 10)
    src, dst = tmp_path / "in.tif", tmp_path / "out.tif"
    subprocess.run(["gdal_translate", "-q", "-a_srs", "EPSG:4265", str(asc), str(src)], check=True)
    source = f"+proj=longlat +ellps=intl +nadgrids={tif} +no_defs +type=crs"
    subprocess.run(["gdalwarp", "-q", "-s_srs", source, "-t_srs", "EPSG:6706", str(src), str(dst)], check=True)
    transform = json.loads(subprocess.run(["gdalinfo", "-json", str(dst)], capture_output=True, text=True, check=True).stdout)["geoTransform"]
    expected = cct(tif, [(11.5, 43.701)])[0]
    assert abs(expected[0] - 11.5) > cell  # the shift is visible at this resolution
    assert transform[0] == pytest.approx(expected[0], abs=cell / 2)
    assert transform[3] == pytest.approx(expected[1], abs=cell / 2)


def test_grid_applied_to_a_projected_system(tif):
    need("gdaltransform")
    # Verto Online, 3003 -> 7791, recorded 2026-11-09.
    verto = (689969.242, 4839983.696)
    source = f"+proj=tmerc +lat_0=0 +lon_0=9 +k=0.9996 +x_0=1500000 +y_0=0 +ellps=intl +nadgrids={tif} +units=m +no_defs +type=crs"
    done = subprocess.run(["gdaltransform", "-s_srs", source, "-t_srs", "EPSG:7791", "-output_xy"], input="1690000 4840000\n", capture_output=True, text=True, check=True)
    e, n = (float(v) for v in done.stdout.split()[:2])
    assert math.hypot(e - verto[0], n - verto[1]) < 0.05
