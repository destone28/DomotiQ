# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Vision on synthetic frames: geometry, segmentation, tracking, identities, privacy."""

import itertools

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from domotiq.layout import Layout  # noqa: E402
from domotiq.model import Identity  # noqa: E402
from domotiq.vision.assignment import linear_sum_assignment  # noqa: E402
from domotiq.vision.engine import ANALYSIS, Engine  # noqa: E402
from domotiq.vision.geometry import BASE_CORNERS_MM, Calibration  # noqa: E402
from domotiq.vision.pipeline import Segmenter  # noqa: E402
from domotiq.vision.privacy import Privacy  # noqa: E402
from domotiq.vision.signature import distance, signature  # noqa: E402
from domotiq.vision.synthetic import Hand, Renderer, Thing  # noqa: E402


@pytest.fixture(scope="module")
def layout():
    return Layout.load()


@pytest.fixture(scope="module")
def renderer(layout):
    return Renderer(layout, seed=3)


@pytest.fixture
def engine(layout, renderer, tmp_path):
    e = Engine(layout, tmp_path / "cal", tmp_path / "ds", tmp_path / "rec")
    fr = [[u / ANALYSIS[0], v / ANALYSIS[1]] for u, v in renderer.calib.corners]
    assert e.set_corners(fr)["ok"]
    assert e.take_empty([renderer.render() for _ in range(5)])["ok"]
    return e


def run(engine, renderer, frames, t0=0.0, dt=0.1):
    """Feed a list of (things, kwargs) and return the tracks of the last frame."""
    tracks = []
    for i, (things, kw) in enumerate(frames):
        tracks = engine.feed(renderer.render(things, **kw), t0 + i * dt)
    return tracks


# ------------------------------------------------------------ geometry
def test_assignment_matches_brute_force():
    rng = np.random.default_rng(1)
    for _ in range(100):
        n, m = (int(v) for v in rng.integers(1, 6, 2))
        c = rng.random((n, m))
        r, k = linear_sum_assignment(c)
        if n <= m:
            best = min(sum(c[i, p[i]] for i in range(n)) for p in itertools.permutations(range(m), n))
        else:
            best = min(sum(c[p[j], j] for j in range(m)) for p in itertools.permutations(range(n), m))
        assert abs(c[r, k].sum() - best) < 1e-9


def test_homography_and_parallax_round_trip():
    cal = Calibration.synthetic()
    pts = np.array([[0, -80], [650, 370], [325, 145], [100, 300]], float)
    assert np.allclose(cal.to_floor(cal.to_image(pts)), pts, atol=1e-6)
    assert np.allclose(cal.to_image(np.array(BASE_CORNERS_MM)), cal.corners, atol=1e-6)
    up = cal.raised(pts, 90)
    assert np.allclose(cal.lowered(up, 90), pts, atol=1e-6)
    # a point far from the centre moves outward when raised; the one under the camera does not
    assert np.hypot(*(up[0] - [325, 145])) > np.hypot(*(pts[0] - [325, 145]))
    assert np.allclose(up[2], pts[2])


def test_calibration_from_fractions_and_file(tmp_path):
    cal = Calibration.synthetic(1280, 960)
    frac = [[u / 1280, v / 960] for u, v in cal.corners]
    c2 = Calibration.from_corners(frac, 640, 480, cal.camera)
    p = np.array([[200.0, 100.0]])
    assert np.allclose(c2.to_image(p) * 2, cal.to_image(p), atol=1e-6)
    c2.save(tmp_path / "c.json")
    c3 = Calibration.load(tmp_path / "c.json")
    assert c3.valid and np.allclose(c3.to_image(p), c2.to_image(p))


def test_signature_distance():
    rng = np.random.default_rng(0)

    def lab(bgr, n=400):
        px = np.full((1, n, 3), bgr, np.uint8)
        px = np.clip(px.astype(np.float32) + rng.normal(0, 3, px.shape), 0, 255).astype(np.uint8)
        return cv2.cvtColor(px.astype(np.float32) / 255, cv2.COLOR_BGR2LAB)[0]

    red, red2, blue = signature(lab((40, 40, 200))), signature(lab((45, 38, 190))), signature(lab((200, 60, 40)))
    darker_red, orange = signature(lab((28, 28, 140))), signature(lab((40, 120, 220)))
    white, grey = signature(lab((230, 230, 230))), signature(lab((150, 150, 150)))
    assert distance(red, red2) < 0.2
    assert distance(red, darker_red) < distance(red, orange)
    assert distance(red, blue) > 0.6
    assert distance(white, grey) > 0.3                 # neutral colours: lightness tells them apart


# ------------------------------------------------------------ segmentation
def test_segmenter_finds_figurines_under_changing_light(layout, renderer):
    seg = Segmenter(layout, renderer.calib)
    seg.set_reference([renderer.render() for _ in range(3)])
    things = [Thing(300, 100, "#d03030"), Thing(80, 160, "#3050d0"), Thing(520, 60, "#20a0a0")]
    cases = [({}, 1.0, (1, 1, 1)),
             ({"living": ("#ffaa5a", 0.8), "kitchen": ("#3060ff", 0.8)}, 1.0, (1, 1, 1)),
             ({}, 0.8, (1.04, 1.0, 0.95))]
    for k, (lights, bri, cast) in enumerate(cases):
        seg.light_changed(list(lights), k * 10.0)
        for rep in range(2):
            obs, fg, _ = seg.process(renderer.render(things, lights=lights, brightness=bri, cast=cast),
                                     now=k * 10.0 + 0.1 + rep * 0.1)
        found = [o.position(renderer.calib, "person") for o in obs]
        assert len(obs) == len(things), (k, [o.centroid_mm for o in obs])
        for t in things:
            d = min(np.hypot(x - t.x, y - t.y) for x, y in found)
            assert d < 12, (k, t, found)


def test_no_false_blobs_from_room_lights_or_shadows(layout, renderer):
    seg = Segmenter(layout, renderer.calib)
    seg.set_reference([renderer.render() for _ in range(3)])
    lights = {"living": ("#ffaa5a", 1.0), "kitchen": ("#3060ff", 1.0), "bedroom": ("#ff0000", 1.0),
              "garage": ("#00ff00", 1.0), "bathroom": ("#ff00ff", 1.0)}
    seg.light_changed(list(lights), 0.0)
    obs, _, _ = seg.process(renderer.render([], lights=lights, brightness=0.85, cast=(1.05, 1.0, 0.93)), now=0.1)
    assert obs == []


def test_car_and_hand_are_told_apart(layout, renderer):
    seg = Segmenter(layout, renderer.calib)
    seg.set_reference([renderer.render() for _ in range(3)])
    car = Thing(540, 300, "#c02020", "car", 70, 0, 170, 75)
    obs, _, _ = seg.process(renderer.render([car]), now=0.1)
    cars = [o for o in obs if o.category_guess == "car"]
    assert len(cars) == 1 and not cars[0].hand
    x, y = cars[0].position(renderer.calib, "car")
    assert np.hypot(x - 540, y - 300) < 20
    obs, _, _ = seg.process(renderer.render([], hands=[Hand(300, 100)]), now=0.2)
    assert any(o.hand for o in obs)


# ------------------------------------------------------------ tracking and identities
def test_track_follows_a_figurine_through_a_door(engine, renderer):
    path = [(120.0, 110.0)] + [(120.0 + i * 12.0, 110.0) for i in range(1, 16)]
    rooms = []
    for i, (x, y) in enumerate(path):
        tracks = engine.feed(renderer.render([Thing(x, y, "#d03030")]), i * 0.1)
        if tracks:
            rooms.append((tracks[0].id, tracks[0].room))
    ids = {tid for tid, _ in rooms}
    assert len(ids) == 1                         # one track all the way
    assert rooms[0][1] == "kitchen" and rooms[-1][1] == "living"
    changes = sum(1 for a, b in zip(rooms, rooms[1:]) if a[1] != b[1])
    assert changes == 1                          # no flicker on the threshold


def test_registered_identities_are_recognized(engine, renderer):
    red, blue = Thing(300, 100, "#d03030"), Thing(520, 150, "#3050d0")
    run(engine, renderer, [([red, blue], {})] * 3)
    by_pos = {round(t.x / 100): t.id for t in engine.tracks}
    sig_red = engine.track_signature(by_pos[3])[0]
    sig_blue = engine.track_signature(by_pos[5])[0]
    engine.set_identities([Identity("id-marco", "Marco", signature=sig_red),
                           Identity("id-sofia", "Sofia", signature=sig_blue)])
    # a fresh start: the house recognizes them by colour alone
    engine.tracker.tracks.clear()
    tracks = run(engine, renderer, [([Thing(100, 60, "#d03030"), Thing(560, 300, "#3050d0")], {})] * 8, t0=10)
    names = {t.identity: t.room for t in tracks}
    assert names.get("id-marco") == "kitchen"
    assert names.get("id-sofia") == "garage"
    assert all(not t.uncertain for t in tracks)


def test_carried_by_hand_keeps_identity(engine, renderer):
    red = Thing(300, 100, "#d03030")
    run(engine, renderer, [([red], {})] * 3)
    tid = engine.tracks[0].id
    engine.tracker.assign(tid, "id-marco")
    # a hand comes down on it and takes it away
    frames = [([red], {"hands": [Hand(300, 100)]})] * 3 + [([], {"hands": [Hand(450, 200)]})] * 3
    tracks = run(engine, renderer, frames, t0=1)
    assert any(t.carried and t.identity == "id-marco" for t in tracks)
    # put down in the bedroom
    tracks = run(engine, renderer, [([Thing(520, 150, "#d03030")], {})] * 4, t0=2)
    mine = [t for t in tracks if t.identity == "id-marco"]
    assert len(mine) == 1 and mine[0].room == "bedroom" and not mine[0].carried


def test_same_colour_twins_are_followed_and_doubted(engine, renderer):
    a, b = Thing(250, 100, "#e0c020"), Thing(560, 100, "#e0c020")
    run(engine, renderer, [([a, b], {})] * 3)
    left = min(engine.tracks, key=lambda t: t.x)
    right = max(engine.tracks, key=lambda t: t.x)
    sig = engine.track_signature(left.id)[0]
    engine.set_identities([Identity("id-leo", "Leo", signature=sig), Identity("id-ada", "Ada", signature=sig)])
    engine.tracker.assign(left.id, "id-leo")
    engine.tracker.assign(right.id, "id-ada")
    asked = []
    engine.on_question = lambda tr, cands: asked.append((tr.id, sorted(cands)))
    # they walk apart: each keeps its name by being followed
    frames = [([Thing(250 - i * 8, 100, "#e0c020"), Thing(560 - i * 3, 100 + i * 8, "#e0c020")], {})
              for i in range(8)]
    tracks = run(engine, renderer, frames, t0=5)
    ids = {t.identity: t for t in tracks}
    assert ids["id-leo"].x < ids["id-ada"].x
    # Leo alone is taken and put down: Ada stayed in sight, so it can only be Leo
    frames = [([Thing(186, 100, "#e0c020"), Thing(536, 164, "#e0c020")], {"hands": [Hand(186, 100)]})] * 2 + \
             [([Thing(536, 164, "#e0c020")], {"hands": [Hand(300, 60)]})] * 3 + \
             [([Thing(330, 60, "#e0c020"), Thing(536, 164, "#e0c020")], {})] * 4
    tracks = run(engine, renderer, frames, t0=7)
    ids = {t.identity: t for t in tracks}
    assert ids["id-leo"].x == pytest.approx(330, abs=12) and not any(t.uncertain for t in tracks)
    # both are taken at once and put down: now each could be either of them
    frames = [([Thing(330, 60, "#e0c020"), Thing(536, 164, "#e0c020")],
               {"hands": [Hand(330, 60), Hand(536, 164, side="top")]})] * 2 + \
             [([], {"hands": [Hand(300, 150), Hand(500, 250, side="top")]})] * 3 + \
             [([Thing(90, 60, "#e0c020"), Thing(560, 120, "#e0c020")], {})] * 5
    tracks = run(engine, renderer, frames, t0=9)
    assert len(tracks) == 2
    assert all(t.uncertain and sorted(t.candidates) == ["id-ada", "id-leo"] for t in tracks)
    assert asked


# ------------------------------------------------------------ images that leave the board
def test_bathroom_is_blurred(layout, renderer):
    img = renderer.render([Thing(230, 300, "#20c020")])
    out = Privacy(layout, renderer.calib).apply(img)
    x, y = renderer.calib.image_of(np.array([[230, 300]]), 90)[0].astype(int)
    patch_in = img[y - 8:y + 8, x - 8:x + 8].astype(float)
    patch_out = out[y - 8:y + 8, x - 8:x + 8].astype(float)
    assert np.abs(patch_in - patch_out).mean() > 10
    # the living room is untouched
    x, y = renderer.calib.image_of(np.array([[300, 100]])).astype(int)[0]
    assert np.array_equal(img[y - 5:y + 5, x - 5:x + 5], out[y - 5:y + 5, x - 5:x + 5])


def test_engine_commands_and_dataset(engine, renderer, tmp_path):
    run(engine, renderer, [([Thing(300, 100, "#d03030")], {})] * 3)
    assert engine.jpeg(overlay=True)[:2] == b"\xff\xd8"
    assert engine.jpeg(calibration=True)[:2] == b"\xff\xd8"
    assert engine.capture(1)["ok"]
    res = engine.export()
    assert res["ok"]
    import zipfile
    with zipfile.ZipFile(res["path"]) as z:
        names = z.namelist()
    assert "coco/annotations.json" in names and "yolo/classes.txt" in names
    assert any(n.startswith("images/") for n in names)
    st = engine.status()
    assert st["calibrated"] and st["reference"] and not st["moved"]
    assert engine.set_corners([[0, 0], [0.1, 0], [0.1, 0.1], [0, 0.1]])["ok"] is False


def test_whole_house_changed_is_reported(engine, renderer):
    run(engine, renderer, [([], {})] * 3)
    assert not engine.status()["flooded"]
    # the hall light turns strongly blue and nobody measured it again
    engine.segmenter.gain_period = 1e9
    frames = [([], {"brightness": 0.45, "cast": (1.6, 0.8, 0.6)})] * 70
    run(engine, renderer, frames, t0=10)
    assert engine.status()["flooded"]
