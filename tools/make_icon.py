"""
Генерирует иконки приложения: app_icon.ico (для exe) и app_icon.png (для окна на Linux/Wine).

Запуск: python tools/make_icon.py
Иконки всегда пишутся в корень проекта, независимо от текущей директории.
Требуется Pillow: pip install -r requirements-dev.txt
"""

import os

from PIL import Image, ImageDraw

SIZE = 256

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def draw_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # Вертикальный градиент фона
    top = (47, 138, 215)
    bottom = (21, 74, 133)
    d = ImageDraw.Draw(img)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        color = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (
            255,
        )
        d.line([(0, y), (SIZE - 1, y)], fill=color)

    # Скруглённые углы
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, SIZE - 1, SIZE - 1], radius=52, fill=255
    )
    img.putalpha(mask)

    d = ImageDraw.Draw(img)

    # Фронтон (треугольник)
    d.polygon([(128, 48), (214, 106), (42, 106)], fill="white")
    # Колонны
    for x in (58, 112, 166):
        d.rounded_rectangle([x, 118, x + 30, 182], radius=7, fill="white")
    # Основание
    d.rounded_rectangle([42, 194, 214, 214], radius=9, fill="white")

    return img


def main():
    png_path = os.path.join(PROJECT_DIR, 'app_icon.png')
    ico_path = os.path.join(PROJECT_DIR, 'app_icon.ico')

    img = draw_icon()
    img.save(png_path, format='PNG')
    img.save(
        ico_path,
        format='ICO',
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )
    print(f"✅ Созданы: {png_path}, {ico_path}")


if __name__ == "__main__":
    main()
