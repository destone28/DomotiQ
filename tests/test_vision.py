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
from domotiq.vision.engine import ANALYSIS, NOISE_FILE, Engine  # noqa: E402
from domotiq.vision.geometry import BASE_CORNERS_MM, Calibration  # noqa: E402
from domotiq.vision.pipeline import Observation, Segmenter  # noqa: E402
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


def bring(engine, renderer, things, t0=0.0):
    """Put the figurines into the empty house one by one, by hand, as a visitor does; returns the tracks
    once they stand still and the house is sure of them. Takes 4 s for the start and 4 s per figurine."""
    run(engine, renderer, [([], {})] * 40, t0=t0)               # the start: the house is empty
    placed, t = [], t0 + 4.0
    for thing in things:
        hand = {"hands": [Hand(thing.x, thing.y)]}
        run(engine, renderer, [(placed, hand)] * 3 + [(placed + [thing], hand)] * 2, t0=t)
        placed.append(thing)
        run(engine, renderer, [(placed, {})] * 35, t0=t + 0.5)
        t += 4.0
    return engine.tracks


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
def test_the_analysed_area_is_the_house_with_real_calibrations(layout):
    # the corners tapped on casa1 on 4 October: the pole, raised to the camera, used to cover everything
    for corners in ([[72.0, 434.7], [560.0, 430.7], [584.0, 72.7], [58.0, 96.7]],
                    [[44.0, 419.8], [590.0, 413.8], [608.0, 35.8], [42.0, 45.8]]):
        cal = Calibration.from_corners([[u / 640, v / 480] for u, v in corners], 640, 480, layout.camera)
        seg = Segmenter(layout, cal)
        share = np.count_nonzero(seg.mask) / np.count_nonzero(seg.view_mask)
        assert share > 0.6, share


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


def flickering(renderer, seed, amp):
    """Frames where a patch of the living-room floor flickers as a whole, in brightness and colour (the glow of a lamp
    on a glossy floor), `amp` levels on each channel. Returns the patch and a function that renders a frame."""
    rng = np.random.default_rng(seed)
    cx, cy = renderer.calib.image_of(np.array([[360.0, 170.0]])).astype(int)[0]
    box = (cx - 25, cy - 15, cx + 25, cy + 15)

    def frame(things=(), shift=None):
        img = renderer.render(list(things)).astype(np.float32)
        x0, y0, x1, y1 = box
        img[y0:y1, x0:x1] += rng.normal(0, amp, 3) if shift is None else shift
        return np.clip(img, 0, 255).astype(np.uint8)
    return box, frame


def test_a_flickering_patch_is_no_blob_and_a_figurine_on_it_keeps_its_shape(layout):
    renderer = Renderer(layout, seed=11)
    box, frame = flickering(renderer, 5, 10.0)
    empty = [frame() for _ in range(20)]
    seg = Segmenter(layout, renderer.calib)
    seg.set_reference(empty)                       # as "Empty house" does: the noise comes with it
    fixed = Segmenter(layout, renderer.calib)
    fixed.set_reference(empty)
    fixed.set_noise(None)                          # the fixed thresholds alone
    x0, y0, x1, y1 = box
    inside = seg.noise[y0:y1, x0:x1].reshape(-1, 2)
    elsewhere = seg.noise[(seg.mask > 0) & (seg.scene.z < 0.5)].reshape(-1, 2)
    assert np.median(inside[:, 0]) > 3 * max(np.median(elsewhere[:, 0]), 1.0)
    assert np.median(inside[:, 1]) > 3 * np.median(elsewhere[:, 1])
    seen_fixed = seen = 0
    for i in range(30):
        f = frame()
        seen_fixed += bool(fixed.process(f, 0.1 + i * 0.1)[0])
        seen += bool(seg.process(f, 0.1 + i * 0.1)[0])
    assert seen_fixed >= 8 and seen == 0, (seen_fixed, seen)
    # figurines on the patch and away from it: found as they are with the fixed thresholds, whole
    for thing in (Thing(360, 170, "#d03030"), Thing(360, 170, "#3050d0"), Thing(120, 160, "#20a0a0")):
        f = frame([thing], shift=np.zeros(3))
        a = [o.pixels for o in fixed.process(f, 10.0)[0]]
        b = [o.pixels for o in seg.process(f, 10.0)[0]]
        assert len(a) == 1 and a == b, (thing, a, b)


def test_the_noise_follows_the_house_slowly_where_nothing_stands(layout):
    renderer = Renderer(layout, seed=12)
    box, frame = flickering(renderer, 6, 4.0)
    seg = Segmenter(layout, renderer.calib)
    seg.set_reference([frame(shift=np.zeros(3)) for _ in range(20)])    # an empty house with no flicker
    before = seg.noise
    x0, y0, x1, y1 = box
    thing = Thing(120, 160, "#20a0a0")
    for i in range(40):
        obs, _, _ = seg.process(frame([thing]), 0.1 + i * 0.1)
        o = min(obs, key=lambda o: np.hypot(o.centroid_mm[0] - thing.x, o.centroid_mm[1] - thing.y))
        figurine = seg.labels == o.extra["label"]
        seg.learn_noise(figurine)                  # the figurine is a presence
    after = seg.noise
    # the patch flickers now: its noise grows, a bit with every sample. Where the figurine is, nothing is learned
    grown = np.median(after[y0:y1, x0:x1, 1]) / np.median(before[y0:y1, x0:x1, 1])
    assert 1.5 < grown < 4.0, grown
    assert np.allclose(after[figurine], before[figurine])


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
def test_a_figurine_moved_by_hand_through_a_door_changes_room_once(engine, renderer):
    tracks = bring(engine, renderer, [Thing(120.0, 110.0, "#d03030")])
    engine.tracker.assign(tracks[0].id, "id-marco")
    # a hand slides it from the kitchen to the living room: on the map it does not follow the hand, it is
    # where the hand leaves it
    path = [(120.0 + i * 12.0, 110.0) for i in range(1, 16)]
    rooms = []
    for i, (x, y) in enumerate(path):
        tracks = engine.feed(renderer.render([Thing(x, y, "#d03030")], hands=[Hand(x, y)]), 10 + i * 0.1)
        rooms += [t.room for t in tracks if t.identity == "id-marco"]
    for i in range(40):
        tracks = engine.feed(renderer.render([Thing(300.0, 110.0, "#d03030")]), 11.6 + i * 0.1)
        rooms += [t.room for t in tracks if t.identity == "id-marco"]
    assert [t.identity for t in tracks] == ["id-marco"] and tracks[0].room == "living"
    assert np.hypot(tracks[0].x - 300, tracks[0].y - 110) < 12
    assert sum(1 for a, b in zip(rooms, rooms[1:]) if a != b) == 1     # one change of room, no flicker


def test_a_figurine_never_moves_on_the_map_by_itself(engine, renderer):
    red = Thing(300.0, 100.0, "#d03030")
    tracks = bring(engine, renderer, [red])
    x0, y0 = tracks[0].x, tracks[0].y
    # its blob shifts a little with no hand around (a shadow, a light): its place on the map does not
    for i in range(40):
        tracks = engine.feed(renderer.render([Thing(300.0 + i * 0.2, 100.0, "#d03030")]), 10 + i * 0.1)
    assert len(tracks) == 1 and (tracks[0].x, tracks[0].y) == (x0, y0)


def test_registered_identities_are_recognized(engine, renderer):
    red, blue = Thing(300, 100, "#d03030"), Thing(520, 150, "#3050d0")
    bring(engine, renderer, [red, blue])
    by_pos = {round(t.x / 100): t.id for t in engine.tracks}
    sig_red = engine.track_signature(by_pos[3])[0]
    sig_blue = engine.track_signature(by_pos[5])[0]
    engine.set_identities([Identity("id-marco", "Marco", signature=sig_red),
                           Identity("id-sofia", "Sofia", signature=sig_blue)])
    # a fresh start: the house recognizes them by colour alone
    engine.tracker.tracks.clear()
    engine.rescan()
    tracks = run(engine, renderer, [([Thing(100, 60, "#d03030"), Thing(560, 300, "#3050d0")], {})] * 15, t0=20)
    names = {t.identity: t.room for t in tracks}
    assert names.get("id-marco") == "kitchen"
    assert names.get("id-sofia") == "garage"
    assert all(not t.uncertain for t in tracks)


def test_carried_by_hand_keeps_identity(engine, renderer):
    red = Thing(300, 100, "#d03030")
    bring(engine, renderer, [red])
    tid = engine.tracks[0].id
    engine.tracker.assign(tid, "id-marco")
    # a hand comes down on it and takes it away
    frames = [([red], {"hands": [Hand(300, 100)]})] * 3 + [([], {"hands": [Hand(450, 200)]})] * 3
    tracks = run(engine, renderer, frames, t0=12)
    assert any(t.carried and t.identity == "id-marco" for t in tracks)
    # put down in the bedroom
    moved = Thing(520, 150, "#d03030")
    run(engine, renderer, [([], {"hands": [Hand(520, 150)]})] * 3 + [([moved], {"hands": [Hand(520, 150)]})] * 2, t0=13)
    tracks = run(engine, renderer, [([moved], {})] * 10, t0=14)
    mine = [t for t in tracks if t.identity == "id-marco"]
    assert len(mine) == 1 and mine[0].room == "bedroom" and not mine[0].carried


def test_same_colour_twins_are_followed_and_doubted(engine, renderer):
    a, b = Thing(250, 100, "#e0c020"), Thing(560, 100, "#e0c020")
    bring(engine, renderer, [a, b])
    left = min(engine.tracks, key=lambda t: t.x)
    right = max(engine.tracks, key=lambda t: t.x)
    sig = engine.track_signature(left.id)[0]
    engine.set_identities([Identity("id-leo", "Leo", signature=sig), Identity("id-ada", "Ada", signature=sig)])
    engine.tracker.assign(left.id, "id-leo")
    engine.tracker.assign(right.id, "id-ada")
    asked = []
    engine.on_question = lambda tr, cands: asked.append((tr.id, sorted(cands)))
    # they stay where they are: each keeps its name by being followed
    tracks = run(engine, renderer, [([a, b], {})] * 8, t0=15)
    ids = {t.identity: t for t in tracks}
    assert ids["id-leo"].x < ids["id-ada"].x
    # Leo alone is taken and put down: Ada stayed in sight, so it can only be Leo
    frames = [([a, b], {"hands": [Hand(250, 100)]})] * 2 + \
             [([b], {"hands": [Hand(330, 60)]})] * 3 + \
             [([Thing(330, 60, "#e0c020"), b], {"hands": [Hand(330, 60)]})] * 2 + \
             [([Thing(330, 60, "#e0c020"), b], {})] * 12
    tracks = run(engine, renderer, frames, t0=17)
    ids = {t.identity: t for t in tracks}
    assert ids["id-leo"].x == pytest.approx(330, abs=12) and not any(t.uncertain for t in tracks)
    # both are taken at once and put down: now each could be either of them
    frames = [([Thing(330, 60, "#e0c020"), b],
               {"hands": [Hand(330, 60), Hand(560, 100, side="top")]})] * 2 + \
             [([], {"hands": [Hand(90, 60), Hand(560, 120, side="top")]})] * 3 + \
             [([Thing(90, 60, "#e0c020"), Thing(560, 120, "#e0c020")],
               {"hands": [Hand(90, 60), Hand(560, 120, side="top")]})] * 2 + \
             [([Thing(90, 60, "#e0c020"), Thing(560, 120, "#e0c020")], {})] * 12
    tracks = run(engine, renderer, frames, t0=20)
    assert len(tracks) == 2
    assert all(t.uncertain and sorted(t.candidates) == ["id-ada", "id-leo"] for t in tracks)
    assert asked


# ------------------------------------------------------------ images that leave the board
def test_around_the_house_is_blurred_and_the_bathroom_optionally(layout, renderer):
    img = renderer.render([Thing(230, 300, "#20c020")])
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, img.shape, dtype=np.uint8)
    privacy = Privacy(layout, renderer.calib, private=False, outside=True)
    around = privacy.mask > 0                                # the stand, the visitors, their phones
    assert around.any() and not around.all()
    img[around] = noise[around]
    plain = privacy.apply(img)
    assert np.abs(plain[around].astype(float) - img[around]).mean() > 30
    x, y = renderer.calib.image_of(np.array([[230, 300]]), 90)[0].astype(int)
    assert np.array_equal(plain[y - 8:y + 8, x - 8:x + 8], img[y - 8:y + 8, x - 8:x + 8])   # bathroom in focus
    blurred = Privacy(layout, renderer.calib, private=True, outside=True).apply(img)
    assert np.abs(blurred[y - 8:y + 8, x - 8:x + 8].astype(float) - img[y - 8:y + 8, x - 8:x + 8]).mean() > 10


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


def test_the_noise_is_saved_with_the_empty_house_and_learned_again_without_it(layout, tmp_path):
    renderer = Renderer(layout, seed=13)
    box, frame = flickering(renderer, 7, 10.0)
    dirs = (tmp_path / "cal", tmp_path / "ds", tmp_path / "rec")
    e = Engine(layout, *dirs)
    assert e.set_corners([[u / ANALYSIS[0], v / ANALYSIS[1]] for u, v in renderer.calib.corners])["ok"]
    assert e.take_empty([frame() for _ in range(20)])["ok"]                # 20 frames, as from the webcam
    saved = e.segmenter.noise
    assert (e.dir / NOISE_FILE).exists() and not e.segmenter.noise_young
    # at the next start the house knows it at once
    e2 = Engine(layout, *dirs)
    assert np.allclose(e2.segmenter.noise, saved, rtol=0.01, atol=0.01) and not e2.segmenter.noise_young
    # the webcam set again for the light of the hall: another noise, learned again, after a restart too
    e2.light_retuned(100.0)
    assert e2.segmenter.noise is None and e2.segmenter.noise_young
    assert Engine(layout, *dirs).segmenter.noise_young
    # a file cut short by a power cut is no noise either
    (e.dir / NOISE_FILE).write_bytes(b"")
    assert Engine(layout, *dirs).segmenter.noise_young
    # without it (saved by an older version), the first calm frames teach it
    (e.dir / NOISE_FILE).unlink(missing_ok=True)
    e3 = Engine(layout, *dirs)
    assert e3.segmenter.noise is None and e3.segmenter.noise_young
    for i in range(40):
        e3.feed(frame(), i * 0.1)
    assert not e3.segmenter.noise_young
    x0, y0, x1, y1 = box
    learned = np.median(e3.segmenter.noise[y0:y1, x0:x1, 1])
    assert 0.5 < learned / np.median(saved[y0:y1, x0:x1, 1]) < 2.0
    assert e3.tracks == []
    # new corners or a reset: the noise goes with the empty house
    corners = [[u / ANALYSIS[0], v / ANALYSIS[1]] for u, v in renderer.calib.corners]
    assert e.take_empty([frame() for _ in range(20)])["ok"] and (e.dir / NOISE_FILE).exists()
    assert e.set_corners(corners)["ok"] and not (e.dir / NOISE_FILE).exists()
    assert e.take_empty([frame() for _ in range(20)])["ok"] and (e.dir / NOISE_FILE).exists()
    e.reset()
    assert not (e.dir / NOISE_FILE).exists()


def test_the_hall_light_changes_and_the_house_follows(engine, renderer):
    run(engine, renderer, [([], {})] * 3)
    # the hall light turns strongly blue: the house measures every room again and counts nothing
    frames = [([], {"brightness": 0.45, "cast": (1.6, 0.8, 0.6)})] * 70
    seen = [len(engine.feed(renderer.render(things, **kw), 10 + i * 0.1)) for i, (things, kw) in enumerate(frames)]
    assert max(seen) == 0
    assert not engine.status()["flooded"]


def test_a_covered_camera_is_reported(engine, renderer):
    run(engine, renderer, [([], {})] * 3)
    run(engine, renderer, [([], {"brightness": 0.03})] * 70, t0=10)
    assert engine.status()["flooded"]
    assert engine.tracks == []


# ------------------------------------------------------------ hands, and nothing moves by itself
def settle(engine, renderer, things, t0, seconds=4.0):
    return run(engine, renderer, [(things, {})] * int(seconds / 0.1), t0=t0)


def test_a_hand_over_the_house_is_never_a_presence(engine, renderer):
    settle(engine, renderer, [], 0)                         # the start scan finds nothing
    path = [(120, 60), (200, 120), (300, 150), (420, 100), (520, 160), (560, 300), (300, 250)]
    seen = []
    for i, (x, y) in enumerate(path * 3):
        side = "bottom" if i % 2 else "top"
        seen.append(engine.feed(renderer.render([], hands=[Hand(x, y, side=side)]), 5 + i * 0.1))
    assert all(not tracks for tracks in seen)
    assert engine.status()["hand"]
    assert settle(engine, renderer, [], 8) == []            # it left nothing behind


def test_a_figurine_put_down_by_hand_appears_when_the_hand_leaves(engine, renderer):
    settle(engine, renderer, [], 0)
    red = Thing(300, 100, "#d03030")
    tracks = run(engine, renderer, [([], {"hands": [Hand(300, 100)]})] * 4 +
                 [([red], {"hands": [Hand(300, 100)]})] * 4, t0=5)
    assert tracks == []                                     # nothing counted while the hand is there
    first = None
    for i in range(30):
        tracks = engine.feed(renderer.render([red]), 6 + i * 0.1)
        if tracks and first is None:
            first = i * 0.1
    assert len(tracks) == 1 and tracks[0].room == "living"
    assert np.hypot(tracks[0].x - 300, tracks[0].y - 100) < 12
    assert first is not None and first <= 3.0               # told once it stands still and is surely there


def test_a_change_with_no_hand_is_not_a_presence(engine, renderer):
    settle(engine, renderer, [], 0)
    # something appears on its own (a reflection, a light), even looking like a figurine: never a track
    ghost = Thing(390, 60, "#30a0d0", "object", 15, 20)
    seen = [engine.feed(renderer.render([ghost]), 5 + i * 0.1) for i in range(60)]
    assert all(not tracks for tracks in seen)
    # and when a hand takes it away, its place is no presence either
    run(engine, renderer, [([ghost], {"hands": [Hand(390, 60)]})] * 3 + [([], {"hands": [Hand(390, 60)]})] * 3,
        t0=11)
    seen = [engine.feed(renderer.render([]), 11.6 + i * 0.1) for i in range(50)]
    assert all(not tracks for tracks in seen)


def test_the_place_of_a_figurine_taken_into_the_empty_house_is_no_presence(engine, renderer):
    settle(engine, renderer, [], 0)
    # an unrecognized figurine that had joined the empty house (as before this rule, or after the light
    # changed beyond the correction): a hand takes it away, and its place matches the empty house as saved
    red = Thing(300, 100, "#d03030")
    frame = renderer.render([red])
    engine.segmenter.absorb(frame, np.ones(engine.segmenter.mask.shape, bool) & (engine.segmenter.mask > 0))
    run(engine, renderer, [([red], {})] * 10, t0=5)
    run(engine, renderer, [([red], {"hands": [Hand(300, 100)]})] * 3 + [([], {"hands": [Hand(300, 100)]})] * 3,
        t0=6)
    seen = [engine.feed(renderer.render([]), 6.6 + i * 0.1) for i in range(50)]
    assert all(not tracks for tracks in seen)
    assert engine.status()["holes"] >= 1


def test_a_figurine_taken_away_leaves_soon_after_the_hand(engine, renderer):
    red = Thing(300, 100, "#d03030")
    tracks = bring(engine, renderer, [red])
    assert len(tracks) == 1
    run(engine, renderer, [([red], {"hands": [Hand(300, 100)]})] * 3 + [([], {"hands": [Hand(300, 60)]})] * 4,
        t0=10)
    gone_at = None
    for i in range(50):
        if not engine.feed(renderer.render([]), 11 + i * 0.1) and gone_at is None:
            gone_at = i * 0.1
    assert gone_at is not None and gone_at < 3.5
    assert engine.tracks == []


def test_a_followed_figurine_does_not_leave_when_unseen_for_a_moment(engine, renderer):
    red = Thing(300, 100, "#d03030")
    tracks = bring(engine, renderer, [red])
    engine.tracker.assign(tracks[0].id, "id-marco")
    tracks = run(engine, renderer, [([], {})] * 5, t0=10)    # hidden for half a second, no hand around
    assert [t.identity for t in tracks] == ["id-marco"]


def test_an_unknown_figurine_is_asked_about(engine, renderer):
    red, blue = Thing(300, 100, "#d03030"), Thing(520, 150, "#3050d0")
    bring(engine, renderer, [red, blue])
    sigs = {round(t.x / 100): engine.track_signature(t.id)[0] for t in engine.tracks}
    engine.set_identities([Identity("id-marco", "Marco", signature=sigs[3]),
                           Identity("id-sofia", "Sofia", signature=sigs[5]),
                           Identity("id-luca", "Luca")])        # registered, colours not learned yet
    asked = []
    engine.on_question = lambda tr, cands: asked.append((tr.identity, cands))
    green = Thing(120, 80, "#20b040")
    run(engine, renderer, [([red, blue], {"hands": [Hand(120, 80)]})] * 3 +
        [([red, blue, green], {"hands": [Hand(120, 80)]})] * 3, t0=12)
    settle(engine, renderer, [red, blue, green], 13)
    newcomer = [t for t in engine.tracks if t.room == "kitchen"]
    assert len(newcomer) == 1 and newcomer[0].identity is None
    # the red and blue ones are recognized as Marco and Sofia; a new person is asked the name, with no
    # registered one proposed (Luca, said aloud, would be recognized anyway)
    assert asked and asked[0][0] is None and asked[0][1] == []


# ------------------------------------------------------------------ camera settings
class FakeWebcam:
    """Controls and pictures of a webcam like the C270: in automatic mode it reports its last manual values,
    and under a warm, greenish light no colour temperature gives the neutral colours of its automatic mode."""

    def __init__(self, light: float) -> None:
        self.light = light                 # brightness per unit of exposure
        self.values = {"exposure": 48, "wb": 0, "gain": 8}
        self.auto = True

    def automatic(self) -> None:
        self.auto = True

    def manual(self) -> None:
        self.auto = False

    def limits(self, key: str):
        return (0, 10000)

    def set(self, values: dict) -> bool:
        self.values.update(values)
        return True

    def measure(self, balance=(1.0, 1.0, 1.0)):
        if self.auto:
            return 120.0, (118.0, 120.0, 122.0)     # what its automatic modes reach: neutral grey
        e, g, wb = self.values["exposure"], self.values["gain"], self.values["wb"]
        luma = min(255.0, self.light * e * (1 + g / 32))
        t = wb / 10000.0                            # 0: bluest, 1: reddest; green always too strong
        bgr = (luma * (0.55 - 0.45 * t), luma * 1.3, luma * (0.6 + 0.8 * t))
        bgr = tuple(c * k for c, k in zip(bgr, balance))
        return 0.114 * bgr[0] + 0.587 * bgr[1] + 0.299 * bgr[2], bgr


def test_the_webcam_settings_are_found_on_the_pictures():
    from domotiq.vision.camera import tune

    for light, gain_needed in ((1.0, False), (0.05, True)):
        cam = FakeWebcam(light)
        values = tune(cam, cam.measure, settle=0)
        cam.values.update({k: v for k, v in values.items() if k != "balance"})
        luma, (b, g, r) = cam.measure(values["balance"])
        assert 55 <= luma <= 110, (light, values, luma)              # about a quarter darker than 120
        assert abs(b / g - 118 / 120) < 0.05 and abs(r / g - 122 / 120) < 0.05, values   # neutral again
        assert (values["gain"] > 0) == gain_needed
        assert values["exposure"] != 36


def test_pictures_are_measured_on_all_three_channels():
    from domotiq.vision.camera import average_stats

    a = np.full((120, 160, 3), (40, 100, 160), np.uint8)
    b = np.full((120, 160, 3), (60, 120, 180), np.uint8)
    luma, (bl, gr, rd) = average_stats([a, b, None])
    assert (round(bl), round(gr), round(rd)) == (50, 110, 170)
    assert luma == pytest.approx(0.114 * 50 + 0.587 * 110 + 0.299 * 170, abs=0.5)
    with pytest.raises(RuntimeError):
        average_stats([])


def test_a_broken_camera_lock_is_not_applied():
    from domotiq.vision.camera import valid_lock

    assert not valid_lock({"exposure": 36, "wb": 0, "gain": 8})      # saved by the old adjustment
    assert not valid_lock(None) and not valid_lock({})
    assert valid_lock({"exposure": 625, "wb": 0, "gain": 32, "balance": [1.8, 1.0, 1.2]})


def test_the_colour_gains_are_applied_to_every_picture():
    from domotiq.vision.camera import Camera

    cam = Camera("none")
    cam.set_balance([2.0, 1.0, 0.5])
    frame = np.full((4, 4, 3), (50, 100, 200), np.uint8)
    assert cv2.LUT(frame, cam._lut)[0, 0].tolist() == [100, 100, 100]
    cam.set_balance([1.0, 1.0, 1.0])
    assert cam._lut is None


def test_something_lying_on_the_edge_is_not_a_hand_for_ever(engine, renderer):
    settle(engine, renderer, [], 0)
    cable = Hand(300, 20)                                    # something still across the edge, as big as an arm
    red = Thing(300, 100, "#d03030")
    seen = [engine.feed(renderer.render([], hands=[cable]), 5 + i * 0.1) for i in range(40)]
    assert engine.status()["hand"] and not any(seen)        # a hand, at first: the house waits
    tracks = run(engine, renderer, [([red], {"hands": [cable]})] * 120, t0=9)
    assert not engine.status()["hand"]                      # still for 8 s: part of the empty house
    assert len(tracks) == 1 and tracks[0].room == "living"  # and the figurine put down meanwhile is seen


def test_the_glow_of_a_house_light_is_never_taken_late(engine, renderer):
    settle(engine, renderer, [], 0)
    # a hand passes, then the house turns on the living room light: its glow stays on the wall
    run(engine, renderer, [([], {"hands": [Hand(300, 100)]})] * 3, t0=5)
    engine.lights_changed(["living"], 6.0)
    glow = {"lights": {"living": ("#ff40ff", 1.0)}}
    seen = [engine.feed(renderer.render([], **glow), 6 + i * 0.1) for i in range(80)]
    assert not any(seen)


def test_an_arm_reaching_over_the_totem_is_a_hand(layout, renderer):
    seg = Segmenter(layout, renderer.calib)
    seg.set_reference([renderer.render() for _ in range(3)])
    obs, _, _ = seg.process(renderer.render([], hands=[Hand(255, 100)]), now=0.1)   # over the intercom totem
    big = [o for o in obs if o.area_mm2 > 2500]
    assert big and all(o.hand for o in big)
    # a figurine waiting by the totem is no hand
    obs, _, _ = seg.process(renderer.render([Thing(300, -20, "#d03030")]), now=0.2)
    assert obs and not any(o.hand for o in obs)


def test_something_that_keeps_jumping_with_no_hand_is_no_presence(engine, renderer):
    settle(engine, renderer, [], 0)
    # a reflection where a hand has just been: it shakes by a few millimetres many times a second
    run(engine, renderer, [([], {"hands": [Hand(300, 100)]})] * 4, t0=5)
    seen = []
    for i in range(60):
        shaking = Thing(300 + (8 if i % 2 else 0), 100, "#d03030")
        seen.append(engine.feed(renderer.render([shaking]), 5.4 + i * 0.1))
    assert not any(seen)                                    # never on the map, never asked about
    assert engine.status()["jittery"] >= 1


def test_a_figurine_standing_still_or_moved_by_hand_is_never_taken_for_a_jumping_one(engine, renderer):
    red = Thing(300, 100, "#d03030")
    assert len(bring(engine, renderer, [red])) == 1
    # carried across the room by hand, in small steps: the hand explains every move
    for i in range(10):
        moved = Thing(300 + 6 * i, 100, "#d03030")
        engine.feed(renderer.render([moved], hands=[Hand(300 + 6 * i, 100)]), 10 + i * 0.1)
    tracks = settle(engine, renderer, [Thing(354, 100, "#d03030")], 11)
    assert len(tracks) == 1 and np.hypot(tracks[0].x - 354, tracks[0].y - 100) < 12
    assert engine.status()["jittery"] == 0


def test_figurines_may_shake_under_an_animated_light(engine, renderer):
    settle(engine, renderer, [], 0)
    engine.lights_changed(["living"], 4.0, animated=["living"])
    run(engine, renderer, [([], {"hands": [Hand(300, 100)]})] * 4, t0=5)
    tracks = []
    for i in range(40):
        shaking = Thing(300 + (8 if i % 2 else 0), 100, "#d03030")
        tracks = engine.feed(renderer.render([shaking]), 5.4 + i * 0.1)
    assert len(tracks) == 1 and tracks[0].room == "living"


def test_nothing_there_said_by_a_visitor_is_forgotten(engine, renderer):
    red = Thing(300, 100, "#d03030")
    tracks = bring(engine, renderer, [red])
    assert len(tracks) == 1
    engine.dismiss(tracks[0].id, 10.0)
    seen = [engine.feed(renderer.render([red]), 10.1 + i * 0.1) for i in range(30)]
    assert not any(seen)                                    # gone, and not born again there
    assert not engine.observations                          # what it was is part of the empty house now


def test_newcomers_are_proposed_registered_ones_of_their_own_kind_only(engine, renderer):
    from domotiq.vision.tracker import _group
    assert _group("dog") == _group("cat") == "animal" and _group("person") == "person"
    red = Thing(300, 100, "#d03030")
    bring(engine, renderer, [red])
    engine.set_identities([Identity("id-viola", "Viola", category="person"),
                           Identity("id-fido", "Fido", category="dog")])
    asked = []
    engine.on_question = lambda tr, cands: asked.append((tr.category, cands))
    for t in engine.tracker.tracks.values():
        t.asked_new, t.category = float("-inf"), "person"
    engine.tracker._ask_unknown(20.0)
    assert asked and asked[-1] == ("person", [])            # a person is asked the name
    for t in engine.tracker.tracks.values():
        t.asked_new, t.category = float("-inf"), "dog"
    engine.tracker._ask_unknown(21.0)
    assert asked[-1] == ("dog", ["id-fido"])                # an animal: only the animals


def test_a_shadow_appearing_with_no_hand_is_never_a_presence(engine, renderer):
    red = Thing(300, 100, "#d03030")
    assert len(bring(engine, renderer, [red])) == 1
    # a hand passes elsewhere, then, with no hand around, a lamp at the side casts a shadow on the floor
    run(engine, renderer, [([red], {"hands": [Hand(520, 150)]})] * 3, t0=10)
    run(engine, renderer, [([red], {})] * 25, t0=10.3)
    seen = []
    for i in range(60):
        frame = renderer.render([red])
        y0, x0 = 300, 380
        frame[y0:y0 + 40, x0:x0 + 60] = (frame[y0:y0 + 40, x0:x0 + 60] * 0.55).astype(frame.dtype)
        seen.append(engine.feed(frame, 12.8 + i * 0.1))
    assert all(len(t) == 1 for t in seen)                   # the figurine stays, nothing is added


def test_the_webcam_is_set_again_when_the_hall_gets_dark_and_nothing_moves(engine, renderer):
    red = Thing(300, 100, "#d03030")
    tracks = bring(engine, renderer, [red])
    engine.tracker.assign(tracks[0].id, "id-marco")
    engine.light_ok = True
    t, wanted = 10.0, None
    for i in range(80):                                     # the hall light goes down, no hand around
        tracks = engine.feed(renderer.render([red], brightness=0.45), t + i * 0.1)
        if wanted is None and engine.retune_wanted(t + i * 0.1):
            wanted = i * 0.1
    assert wanted is not None and 5.0 <= wanted <= 6.5      # after five seconds of a darker hall
    assert [x.identity for x in tracks] == ["id-marco"]     # nobody left meanwhile
    engine.light_retuned(18.0)                              # the webcam found its light again
    assert not engine.retune_wanted(18.1)
    tracks = run(engine, renderer, [([red], {})] * 60, t0=18.0)
    assert [x.identity for x in tracks] == ["id-marco"] and engine.status()["retunes"] == 1


def test_a_figurine_on_the_bed_is_seen_on_the_bed(engine, renderer):
    # on the bed (46.5 mm high, x 487-567, y 122-219.5): drawn from the floor up, the bed hides the part below
    viola = Thing(527, 170, "#7030c0", height=46.5 + 90.0)
    tracks = bring(engine, renderer, [viola])
    assert len(tracks) == 1 and tracks[0].room == "bedroom"
    assert np.hypot(tracks[0].x - 527, tracks[0].y - 170) < 6


def test_the_car_and_a_figurine_of_the_same_colour_are_never_mixed_up(engine, renderer):
    blue = Thing(300, 100, "#3050d0")
    tracks = bring(engine, renderer, [blue])
    sig = engine.track_signature(tracks[0].id)[0]
    # the car registered with exactly the colours of the figurine: the size tells them apart
    engine.set_identities([Identity("id-civic", "Honda Civic", category="car", signature=sig, size=9000.0)])
    tracks = run(engine, renderer, [([blue], {})] * 20, t0=10)
    assert [t.identity for t in tracks] == [None]


def test_a_figurine_lying_on_the_bed_is_seen_and_followed(engine, renderer):
    # lying down it is more than three times longer than wide, but its colour is vivid
    lying = Thing(527, 165, "#7030c0", kind="animal", length=70.0, width=16.0, height=46.5 + 12.0)
    tracks = bring(engine, renderer, [lying])
    assert len(tracks) == 1 and tracks[0].room == "bedroom"
    tracks = run(engine, renderer, [([lying], {})] * 30, t0=10)
    assert len(tracks) == 1 and tracks[0].on == "bed"


def test_who_stood_there_before_gets_its_name_back_without_asking(engine, renderer):
    red = Thing(300, 100, "#d03030")
    tracks = bring(engine, renderer, [red])
    engine.set_identities([Identity("id-marco", "Marco")])
    tr = engine.tracker
    t = tr.tracks[tracks[0].id]
    tr.places["id-marco"] = (t.x + 10, t.y, 9.0)     # Marco stood right there, and no hand came since
    asked = []
    engine.on_question = lambda track, cands: asked.append(track.id)
    t.identity, t.asked_new = None, float("-inf")
    tr._ask_unknown(20.0)
    assert t.identity == "id-marco" and asked == []
    # a hand has been over that place since: it may be someone else, and the house asks
    t.identity, t.asked_new = None, float("-inf")
    tr._touched.add("id-marco")
    tr._ask_unknown(21.0)
    assert t.identity is None and asked == [t.id]


def test_a_new_pose_is_learned_and_then_recognized(engine, renderer):
    standing = Thing(300, 100, "#7030c0")
    tracks = bring(engine, renderer, [standing])
    sig = engine.track_signature(tracks[0].id)[0]
    engine.set_identities([Identity("id-viola", "Viola", signature=sig)])
    tracks = run(engine, renderer, [([standing], {})] * 10, t0=10)
    assert [t.identity for t in tracks] == ["id-viola"]
    viola = engine.tracker.identities["id-viola"]
    # somebody lays her down and says who she is: this look becomes one of her poses
    lying = Thing(300, 100, "#7030c0", kind="animal", length=70.0, width=16.0, height=45.0)
    run(engine, renderer, [([standing], {"hands": [Hand(300, 100)]})] * 3 + [([lying], {"hands": [Hand(300, 100)]})] * 3,
        t0=12)
    tracks = run(engine, renderer, [([lying], {})] * 30, t0=12.6)
    engine.tracker.assign(tracks[0].id, "id-viola")
    vt = engine.tracker.track(tracks[0].id)
    engine.tracker.add_pose(viola, vt.sig, vt.obs.area_mm2, vt.obs.elongation)
    assert len(viola.poses) == 1 and engine.learned_poses() == {"id-viola": viola.poses}
    # a hand takes her out of the house...
    run(engine, renderer, [([lying], {"hands": [Hand(300, 100)]})] * 3 + [([], {"hands": [Hand(300, 100)]})] * 3,
        t0=16)
    assert run(engine, renderer, [([], {})] * 40, t0=16.6) == []
    # ...and later, lying again somewhere else, she is recognized from that pose, with no question
    asked = []
    engine.on_question = lambda tr, c: asked.append(tr.id)
    other = Thing(120, 80, "#7030c0", kind="animal", length=70.0, width=16.0, height=45.0)
    run(engine, renderer, [([], {"hands": [Hand(120, 80)]})] * 3 + [([other], {"hands": [Hand(120, 80)]})] * 3, t0=21)
    tracks = run(engine, renderer, [([other], {})] * 35, t0=21.6)
    assert [t.identity for t in tracks] == ["id-viola"] and not asked


def test_the_closest_pose_counts(layout, renderer):
    from domotiq.vision.tracker import Tracker
    seg = Segmenter(layout, renderer.calib)
    seg.set_reference([renderer.render() for _ in range(3)])

    def look(color):
        obs, _, _ = seg.process(renderer.render([Thing(300, 100, color)]), now=0.1)
        return max(obs, key=lambda o: o.area_mm2)
    red, pink = look("#d03030"), look("#e070b0")
    marco = Identity("id-marco", "Marco", signature=list(red.sig))
    far = Tracker._unlike(pink.sig, pink.area_mm2, marco, pink.elongation)
    marco.poses = [{"sig": list(pink.sig), "size": pink.area_mm2, "elong": pink.elongation}]
    near = Tracker._unlike(pink.sig, pink.area_mm2, marco, pink.elongation)
    assert far > 0.45 and near < 0.05            # seen like that before: it is Marco


# ------------------------------------------------------------ names move only with a hand
def _look(L, a, b):
    rng = np.random.default_rng(0)
    px = np.column_stack([np.full(400, L), np.full(400, a), np.full(400, b)]) + rng.normal(0, 3.0, (400, 3))
    return signature(px.astype(np.float32))


def _blob(x, y, sig, area=700.0, hand=False):
    o = Observation((0.0, 0.0), (0, 0, 640, 480) if hand else (0, 0, 1, 1), (x, y), (x, y), (x, y), area, 20.0, 1.2,
                    sig, hand=hand, category_guess="person")
    o.extra.update(contrast=(40.0, -20.0), floor=1.0, label=1)
    return o


def _tracker(layout, identities):
    from domotiq.vision.tracker import Tracker
    tr = Tracker(layout, Calibration.synthetic(640, 480, layout.camera))
    tr.tops = []
    tr.set_identities(identities)
    return tr


def test_names_do_not_swap_with_no_hand(layout):
    a, b = _look(45, 50, 30), _look(45, 40, 40)
    tr = _tracker(layout, [Identity("id-a", "A", signature=list(a)), Identity("id-b", "B", signature=list(b))])
    for k in range(6):
        tr.update([_blob(200, 60, a), _blob(450, 60, b)], now=100 + 0.1 * k, quiet_s=100)
    names = {round(t.x): t.identity for t in tr.tracks.values()}
    assert sorted(names.values()) == ["id-a", "id-b"]
    # a change of light: each now looks a little more like the other one (still close to its own), and no hand
    # came by: nobody swapped them, the names stay where they are
    a2, b2 = _look(45, 44, 36), _look(45, 46, 34)
    for k in range(20):
        tr.update([_blob(200, 60, a2), _blob(450, 60, b2)], now=101 + 0.1 * k, quiet_s=100)
    assert {round(t.x): t.identity for t in tr.tracks.values()} == names


def test_a_name_does_not_jump_far_without_a_hand(layout):
    a = _look(45, 50, 30)
    tr = _tracker(layout, [Identity("id-a", "A", signature=list(a))])
    for k in range(6):
        tr.update([_blob(200, 60, a)], now=100 + 0.1 * k, quiet_s=100)
    assert [t.identity for t in tr.tracks.values()] == ["id-a"]
    # lost for good where it stood (it joined the empty house); something like it far away, and no hand anywhere:
    # nothing moves by itself, so that is not A
    tr.tracks.clear()
    for k in range(20):
        tr.update([_blob(450, 60, a)], now=101 + 0.1 * k, quiet_s=100)
    assert [t.identity for t in tr.tracks.values()] == [None]
    # a hand has been over the place where A stood: now that one may well be A, carried there
    tr.update([_blob(200, 60, a, area=6000.0, hand=True), _blob(450, 60, a)], now=103.5, quiet_s=0.0)
    for k in range(10):
        tr.update([_blob(450, 60, a)], now=104 + 0.1 * k, quiet_s=5.0)
    assert [t.identity for t in tr.tracks.values()] == ["id-a"]


def test_poses_of_another_colour_are_forgotten(layout):
    red, green, red_lying = _look(45, 50, 30), _look(60, -40, 30), _look(48, 46, 30)
    a = Identity("id-a", "A", signature=list(red), poses=[{"sig": list(green), "size": 700.0, "elong": 1.2},
                                                           {"sig": list(red_lying), "size": 900.0, "elong": 4.0}])
    tr = _tracker(layout, [a, Identity("id-b", "B", signature=list(green))])
    assert [p["elong"] for p in tr.identities["id-a"].poses] == [4.0] and "id-a" in tr.posed
    # a look of another colour is never learned as a pose either
    assert not tr.add_pose(tr.identities["id-a"], green, 700.0, 1.2)
    assert tr.add_pose(tr.identities["id-a"], _look(46, 48, 31), 650.0, 1.5)


def test_two_figurines_touching_are_both_there(layout):
    a, b = _look(45, 50, 30), _look(60, -40, 30)
    tr = _tracker(layout, [Identity("id-a", "A", signature=list(a)), Identity("id-b", "B", signature=list(b))])
    blob = _look(50, 10, 30)                     # one blob, coloured partly like each of them
    for k in range(4):
        tr.update([_blob(300, 60, blob, area=1400.0)], now=100 + 0.1 * k, quiet_s=100)
    [t] = tr.tracks.values()
    tr.together(t.id, ["id-b", "id-a"], 100.5)
    out = tr.update([_blob(300, 60, blob, area=1400.0)], now=102, quiet_s=100)
    assert sorted(x.identity for x in out) == ["id-a", "id-b"]
    assert {round(x.x) for x in out} == {round(t.x)}          # in the same place, one hidden behind the other
    assert sum(x.hidden for x in out) == 1


def test_tracks_go_out_as_plain_json(layout):
    import json
    a = _look(45, 50, 30)
    tr = _tracker(layout, [])
    out = []
    for k in range(40):
        out = tr.update([_blob(300, 60, a)], now=100 + 0.2 * k, quiet_s=100, frozen=False)
    assert out and json.dumps([t.to_dict() for t in out])        # no numpy type left in a track
    assert all(type(t.sure) is bool for t in out)


def test_nothing_there_forgets_where_the_name_was_and_doubts_the_room(layout):
    from domotiq.vision.tracker import PRESENCE_DOUBTED
    a = _look(45, 50, 30)
    tr = _tracker(layout, [Identity("id-a", "A", signature=list(a))])
    for k in range(6):
        tr.update([_blob(300, 60, a)], now=100 + 0.1 * k, quiet_s=100)
    [t] = tr.tracks.values()
    assert t.identity == "id-a" and "id-a" in tr.places
    tr.dismiss(t.id, 101.0)
    # the name was on something that is not there: its place no longer ties the character to that spot
    assert "id-a" not in tr.places
    room = layout.locate(t.x, t.y)
    assert tr._doubted.get(room, 0) > 101.0 and PRESENCE_DOUBTED > 0.9


def test_a_car_is_asked_about_out_of_the_garage_only_when_certain(layout):
    blue = _look(40, 10, -40)
    tr = _tracker(layout, [])
    asked = []
    tr.on_question = lambda t, cands: asked.append(layout.locate(t.x, t.y))
    # something car-sized in the living room: a light, a shadow, figurines together; no question for 10 s
    living = _blob(300, 100, blue, area=9000.0)
    for k in range(40):
        tr.update([living], now=100 + 0.2 * k, quiet_s=100)
    assert asked == []
    # still there, still, clearly seen for longer: now the house is certain and asks
    for k in range(30):
        tr.update([_blob(300, 100, blue, area=9000.0)], now=108 + 0.2 * k, quiet_s=100)
    assert asked == ["living"]
    # car-sized, out of the garage, with a jump every four seconds (a light, a shadow): never still for 10 s,
    # never asked about
    tr3 = _tracker(layout, [])
    asked3 = []
    tr3.on_question = lambda t, cands: asked3.append(layout.locate(t.x, t.y))
    for k in range(150):
        tr3.update([_blob(312 if k % 20 == 5 else 300, 100, blue, area=9000.0)], now=300 + 0.2 * k, quiet_s=100)
    assert asked3 == []
    # in the garage it asks at once
    tr2 = _tracker(layout, [])
    asked2 = []
    tr2.on_question = lambda t, cands: asked2.append(layout.locate(t.x, t.y))
    for k in range(15):
        tr2.update([_blob(540, 300, blue, area=9000.0)], now=200 + 0.2 * k, quiet_s=100)
    assert asked2 == ["garage"]
