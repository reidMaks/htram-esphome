import subprocess
import sys
from pathlib import Path

from PIL import Image

from tools.images.generate_weather_icons import (
    SIZE,
    make_cloudy,
    make_fog,
    make_lightning,
    make_lightning_layers,
    make_partlycloudy,
    make_partlycloudy_layers,
    make_rainy,
    make_rainy_layers,
    make_snowy,
    make_snowy_layers,
    make_sunny,
    make_windy,
    process_and_save,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_single_layer_icon_generators():
    for name, gen_fn in [
        ("sunny", make_sunny),
        ("partlycloudy", make_partlycloudy),
        ("cloudy", make_cloudy),
        ("rainy", make_rainy),
        ("lightning", make_lightning),
        ("snowy", make_snowy),
        ("fog", make_fog),
        ("windy", make_windy),
    ]:
        im = gen_fn()
        assert isinstance(im, Image.Image), f"{name} should return a PIL Image"
        assert im.size == (SIZE, SIZE), f"{name} size should match ({SIZE}, {SIZE})"
        assert im.mode == "L", f"{name} mode should be grayscale 'L'"

        # Verify pixels contain non-zero content
        data = getattr(im, "get_flattened_data", im.getdata)()
        unique_vals = set(data)
        assert 255 in unique_vals, f"{name} image should contain white pixels"
        assert 0 in unique_vals, f"{name} image should contain black background pixels"


def test_multilayer_icon_generators():
    generators = [
        ("partlycloudy", make_partlycloudy_layers, ["sun", "cloud"]),
        ("rainy", make_rainy_layers, ["cloud", "drops"]),
        ("lightning", make_lightning_layers, ["cloud", "bolt"]),
        ("snowy", make_snowy_layers, ["cloud", "flakes"]),
    ]

    for name, gen_fn, layer_keys in generators:
        layers = gen_fn()
        assert isinstance(layers, dict), f"{name} should return a dict of layers"

        # Check that combined mask exists alongside separate layer masks
        comb_key = f"weather_{name}_mask.png"
        assert comb_key in layers, f"Missing combined mask {comb_key}"

        comb_im, shared_bbox = layers[comb_key]
        assert shared_bbox is not None, f"{name} bounding box must not be None"
        assert len(shared_bbox) == 4

        # Check each layer
        for key in layer_keys:
            full_key = f"weather_{name}_{key}_mask.png"
            assert full_key in layers, f"Missing layer {full_key}"
            layer_im, bbox = layers[full_key]
            assert bbox == shared_bbox, (
                f"Layer {full_key} must share identical bbox with combined mask"
            )

            # Check that layer contains drawn content
            data = getattr(layer_im, "get_flattened_data", layer_im.getdata)()
            assert 255 in set(data), f"Layer {full_key} should have drawn pixels"


def test_process_and_save_binary_output(tmp_path, monkeypatch):
    import tools.images.generate_weather_icons as gen_mod

    monkeypatch.setattr(gen_mod, "OUTPUT_DIR", str(tmp_path))

    # Test saving single layer
    sunny_im = make_sunny()
    process_and_save(sunny_im, target_h=36, filename="test_sunny.png")

    out_file = tmp_path / "test_sunny.png"
    assert out_file.exists()

    saved_img = Image.open(out_file)
    assert saved_img.size[1] == 36, "Output height must be 36px"
    assert saved_img.size[0] > 0

    # Ensure strictly 1-bit binary values {0, 255}
    pixel_values = set(getattr(saved_img, "get_flattened_data", saved_img.getdata)())
    assert pixel_values.issubset({0, 255})
    assert 0 in pixel_values and 255 in pixel_values


def test_multilayer_dimension_alignment(tmp_path, monkeypatch):
    """Verify that multi-layer masks processed with shared bbox have exactly identical dimensions."""
    import tools.images.generate_weather_icons as gen_mod

    monkeypatch.setattr(gen_mod, "OUTPUT_DIR", str(tmp_path))

    layers = make_partlycloudy_layers()
    for filename, (im, bbox) in layers.items():
        process_and_save(im, target_h=36, filename=filename, bbox=bbox)

    sun_img = Image.open(tmp_path / "weather_partlycloudy_sun_mask.png")
    cloud_img = Image.open(tmp_path / "weather_partlycloudy_cloud_mask.png")
    comb_img = Image.open(tmp_path / "weather_partlycloudy_mask.png")

    assert sun_img.size == cloud_img.size == comb_img.size, (
        f"Layers must have identical dimensions for alignment: "
        f"sun={sun_img.size}, cloud={cloud_img.size}, comb={comb_img.size}"
    )


def test_generate_weather_icons_cli():
    cmd = [
        sys.executable,
        str(REPO_ROOT / "tools" / "images" / "generate_weather_icons.py"),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "Saved weather_sunny_mask.png" in res.stdout
    assert "Saved weather_partlycloudy_sun_mask.png" in res.stdout
    assert "Saved weather_partlycloudy_cloud_mask.png" in res.stdout
