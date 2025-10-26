#!/usr/bin/env python3
"""
Image to ASCII Converter
Converts a 64x64 image to monochrome and prints it as ASCII art.
Uses '.' for 0 (black) and '#' for 1 (white).
"""

from PIL import Image
import sys


def image_to_ascii(image_path, target_size=(64, 64), threshold=128):
    """
    Convert an image to ASCII art representation.
    
    Args:
        image_path: Path to the input image file
        target_size: Tuple of (width, height) to resize image to
        threshold: Brightness threshold for monochrome conversion (0-255)
    
    Returns:
        String representation of the image in ASCII
    """
    try:
        # Open and load the image
        img = Image.open(image_path)
        
        # Resize to target size
        img = img.resize(target_size, Image.Resampling.LANCZOS)
        
        # Convert to grayscale
        img = img.convert('L')
        
        # Convert to monochrome (1-bit)
        # Pixels above threshold become white (1), below become black (0)
        img = img.point(lambda x: 255 if x > threshold else 0, mode='1')
        
        # Build ASCII representation
        ascii_art = []
        width, height = img.size
        
        for y in range(height):
            row = []
            for x in range(width):
                pixel = img.getpixel((x, y))
                # pixel is either 0 (black) or 255/True (white) in mode '1'
                row.append('#' if pixel else '.')
            ascii_art.append(''.join(row))
        
        return '\n'.join(ascii_art)
    
    except FileNotFoundError:
        print(f"Error: Image file '{image_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing image: {e}")
        sys.exit(1)


def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) < 2:
        print("Usage: python image_to_ascii.py <image_path> [threshold]")
        print("  image_path: Path to the image file")
        print("  threshold: Optional brightness threshold (0-255, default: 128)")
        print("\nExample: python image_to_ascii.py myimage.png 150")
        sys.exit(1)
    
    image_path = sys.argv[1]
    threshold = int(sys.argv[2]) if len(sys.argv) > 2 else 128
    
    # Validate threshold
    if not 0 <= threshold <= 255:
        print("Error: Threshold must be between 0 and 255")
        sys.exit(1)
    
    print(f"Converting image: {image_path}")
    print(f"Target size: 64x64")
    print(f"Threshold: {threshold}")
    print("-" * 64)
    
    ascii_art = image_to_ascii(image_path, target_size=(32, 32), threshold=threshold)
    print(ascii_art)
    
    # Optional: Save to file
    output_file = image_path.rsplit('.', 1)[0] + '_ascii.txt'
    with open(output_file, 'w') as f:
        f.write(ascii_art)
    print("-" * 64)
    print(f"ASCII art saved to: {output_file}")


if __name__ == "__main__":
    main()

