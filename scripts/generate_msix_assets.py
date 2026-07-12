from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
source = Image.open(ROOT / "assets" / "fileflow.png").convert("RGBA")
destination = ROOT / "packaging" / "msix" / "Assets"
destination.mkdir(parents=True, exist_ok=True)

for name, size in {
    "Square44x44Logo.png": (44, 44),
    "Square150x150Logo.png": (150, 150),
    "StoreLogo.png": (50, 50),
}.items():
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    inset = max(2, int(min(size) * 0.08))
    icon = source.resize((size[0] - inset * 2, size[1] - inset * 2), Image.Resampling.LANCZOS)
    canvas.alpha_composite(icon, (inset, inset))
    canvas.save(destination / name)
