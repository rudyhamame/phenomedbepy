import sys
from collections import Counter
from PIL import Image

def extract_colors(image_path, num_colors=10):
    image = Image.open(image_path)
    image = image.convert('RGB')
    pixels = list(image.getdata())
    counter = Counter(pixels)
    most_common = counter.most_common(num_colors)
    return [color for color, count in most_common]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_colors.py <image_path> [num_colors]")
        sys.exit(1)
    image_path = sys.argv[1]
    num_colors = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    colors = extract_colors(image_path, num_colors)
    for color in colors:
        print(color)