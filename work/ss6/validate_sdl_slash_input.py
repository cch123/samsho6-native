#!/usr/bin/env python3
"""Compare normal SDL keyboard processing against the packaged game's scripted renderer."""
import hashlib
import json
import os
import shlex
import struct
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = HERE / "build-native"
OUTPUT = ROOT / "outputs/ss6-feasibility"
PACKAGE = OUTPUT / "native-viewer"
ASSETS = PACKAGE / "assets"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bmp_pixels(path):
    data = path.read_bytes()
    offset = struct.unpack_from("<I", data, 10)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    depth = struct.unpack_from("<H", data, 28)[0]
    assert (width, abs(height), depth) == (960, 672, 32)
    stride = width * 4
    pixels = data[offset : offset + abs(height) * stride]
    assert len(pixels) == abs(height) * stride
    # BMP height may invert the scanline order depending on SDL's surface.
    if height > 0:
        return b"".join(pixels[y * stride : (y + 1) * stride] for y in reversed(range(height)))
    return pixels


def check_case(work, name, initial, keys, expected, boxes=False):
    initial_script = work / "initial.txt"
    expected_script = work / "expected.txt"
    actual_bmp = work / "keyboard.bmp"
    expected_bmp = work / "direct.bmp"
    initial_script.write_text(initial + "\n")
    expected_script.write_text(initial + "\n" + expected + "\n")
    dummy = {**os.environ, "SDL_VIDEO_DRIVER": "dummy", "SDL_RENDER_DRIVER": "software"}
    subprocess.run([work / "key-loop", ASSETS, initial_script, actual_bmp, *keys],
                   cwd=work, env=dummy, check=True, timeout=30)
    subprocess.run([PACKAGE / "ss6-viewer", "--mode", "trial", "--assets", ASSETS,
                    "--trial-script", expected_script, "--boxes", str(int(boxes)),
                    "--snapshot", expected_bmp], cwd=work, env=dummy, check=True, timeout=30)
    pixels = bmp_pixels(actual_bmp)
    assert pixels == bmp_pixels(expected_bmp), (name, "keyboard versus scripted frame mismatch")
    rows = subprocess.run([BUILD / "ss6-contact-trial-probe", ASSETS], input=expected_script.read_text(),
                          cwd=work, text=True, capture_output=True, check=True, timeout=30).stdout.splitlines()
    row = list(map(float, rows[-1].split()))
    return dict(name=name, keys=keys, actions=[int(row[5]), int(row[16])],
                life=[int(row[2]), int(row[13])], hits=[int(row[11]), int(row[22])],
                wins=[int(row[74]), int(row[84])], pixels_sha256=hashlib.sha256(pixels).hexdigest())


def validate(work):
    cases = []

    def case(*args):
        result = check_case(work, *args)
        cases.append(result)
        return result

    near = "place 280 344"
    far = "place 280 380"
    for player, (light, heavy) in enumerate([("J", "L"), ("O", "I")]):
        prefix = f"p{player + 1}-"
        press = f"command {player} 6\n"
        for position, action, damage in [(near, 189, 38), (far, 190, 43)]:
            start = case(prefix + f"start-{action}", position, [heavy, "N1"], press + "tick 1")
            assert start["actions"][player] == action
            hit = case(prefix + f"hit-{action}", position, [heavy, "N40"], press + "tick 40")
            assert hit["life"][1 - player] == 200 - damage and hit["hits"][player] == 1

        blocked = case(prefix + "repeat", near, [heavy + "+", "N200", heavy + "~", "N1"],
                       press + "tick 201")
        assert blocked["actions"] == [0, 0] and blocked["hits"][player] == 1
        fresh = case(prefix + "release-and-press", near,
                     [heavy + "+", "N200", heavy + "-", heavy + "+", "N1"],
                     press + "tick 200\n" + press + "tick 1")
        assert fresh["actions"][player] in [189, 190]
        # The ground selection table gives the light press priority regardless
        # of which key-down event SDL enqueues first inside a simulation tick.
        for first, second in [(light, heavy), (heavy, light)]:
            chord = case(prefix + f"chord-{first}{second}", near, [first + "+", second + "+", "N1"],
                         f"command {player} 5\ntick 1")
            assert chord["actions"][player] == 185

        # The focus-loss fixture initially pauses the loop. A hit pressed
        # during that pause must not execute on the first resumed tick.
        resumed = case(prefix + "resume-discard", near, [heavy, "Space", "N1"], "tick 1")
        assert resumed["actions"] == [0, 0]
        paused = case(prefix + "pause-discard", near, ["Space", heavy, "Space", "N1"], "tick 1")
        assert paused["actions"] == [0, 0]

    trade = case("trade", near, ["L", "I", "N38"], "command 0 6\ncommand 1 6\ntick 38")
    assert trade["life"] == [162, 162]
    case("hitboxes", near, ["L", "H", "N15"], "command 0 6\ntick 15", True)
    intro = case("opening-lock", "match", ["L", "I", "N1"], "tick 1")
    assert intro["actions"] == [492, 492] and intro["life"] == [200, 200]
    complete = (HERE / "scenarios/heavy-match-010.txt").read_text()
    reset = case("restart-after-match", complete, ["R", "N1"], "reset\nmatch\ntick 1")
    assert reset["wins"] == [0, 0] and reset["actions"] == [492, 492] and reset["life"] == [200, 200]
    return cases


def main():
    harness_source = HERE / "sdl_slash_input_test.cpp"
    archive = BUILD / "libss6-runtime.a"
    viewer = PACKAGE / "ss6-viewer"
    assert sha256(viewer) == sha256(BUILD / "ss6-viewer"), "Rebuild and repackage the current viewer"
    sdl = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "sdl3"], text=True))
    with tempfile.TemporaryDirectory(prefix="ss6-sdl-slash-") as name:
        work = Path(name)
        harness = work / "key-loop"
        subprocess.run([*shlex.split(os.environ.get("CXX", "c++")), "-std=c++20", "-O2",
                        "-I", ROOT / "src", harness_source, archive, *sdl, "-o", harness],
                       cwd=work, check=True, timeout=120)
        cases = validate(work)
        evidence = dict(status="passed", count=len(cases), viewer_sha256=sha256(viewer),
                        harness_sha256=sha256(harness), archive_sha256=sha256(archive),
                        probe_sha256=sha256(BUILD / "ss6-contact-trial-probe"),
                        source_sha256={str(path.relative_to(ROOT)): sha256(path) for path in [
                            ROOT / "src/viewer.cpp", ROOT / "src/contact_trial.cpp", ROOT / "src/contact_trial.hpp",
                            harness_source, Path(__file__).resolve()]},
                        scope="Normal viewer SDL_PollEvent path in a separate test executable using the dummy "
                              "video driver and software renderer. Every full 960x672 framebuffer matches the installed "
                              "viewer's scripted snapshot with packaged assets. Attack edges are SDL_PushEvent events. "
                              "Physical keyboard state and held crouch are outside this comparison.", cases=cases)
    (OUTPUT / "sdl_slash_input_validation.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"{len(cases)} SDL keyboard scenes passed against {evidence['viewer_sha256']}")


if __name__ == "__main__":
    main()
