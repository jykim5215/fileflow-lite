from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
assets = ROOT / "assets"
assets.mkdir(exist_ok=True)
size = 512
image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((38, 96, 474, 452), radius=48, fill="#17313A")
draw.rounded_rectangle((38, 158, 474, 452), radius=48, fill="#087E72")
draw.rounded_rectangle((48, 68, 236, 178), radius=30, fill="#17313A")
draw.polygon([(174, 226), (302, 226), (302, 188), (404, 276), (302, 364), (302, 326), (174, 326)], fill="white")
draw.rounded_rectangle((128, 380, 390, 416), radius=18, fill="white")
png = assets / "fileflow.png"
ico = assets / "fileflow.ico"
image.save(png)
image.save(ico, format="ICO", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print(ico)

