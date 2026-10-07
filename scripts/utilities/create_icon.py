"""
create_icon.py
==============
Generates a simple shield icon for the application.
Creates both a PNG and ICO file.

Usage:
    python create_icon.py
    
Output:
    icon.png (256x256 PNG)
    icon.ico (multi-resolution ICO file)
"""

from PIL import Image, ImageDraw

def create_shield_icon(size=256):
    """
    Create a modern shield icon with a checkmark.
    
    Parameters
    ----------
    size : int
        Icon size in pixels (default: 256)
    
    Returns
    -------
    PIL.Image
        Generated icon image
    """
    # Create transparent background
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Calculate proportions
    margin = size // 8
    shield_top = margin
    shield_bottom = size - margin
    shield_width = size - 2 * margin
    center_x = size // 2
    
    # Shield outline coordinates (classic shield shape)
    shield_points = [
        (center_x, shield_top),                      # Top center
        (center_x + shield_width // 2, shield_top + shield_width // 6),  # Top right
        (center_x + shield_width // 2, shield_bottom - shield_width // 3),  # Bottom right
        (center_x, shield_bottom),                   # Bottom point
        (center_x - shield_width // 2, shield_bottom - shield_width // 3),  # Bottom left
        (center_x - shield_width // 2, shield_top + shield_width // 6),  # Top left
    ]
    
    # Draw shield shadow (for depth)
    shadow_offset = size // 40
    shadow_points = [(x + shadow_offset, y + shadow_offset) for x, y in shield_points]
    draw.polygon(shadow_points, fill=(0, 0, 0, 50))
    
    # Draw main shield (blue gradient effect with two layers)
    # Outer shield (darker blue)
    draw.polygon(shield_points, fill=(41, 128, 185, 255))
    
    # Inner shield (lighter blue, smaller)
    inner_margin = size // 12
    inner_points = [
        (center_x, shield_top + inner_margin),
        (center_x + shield_width // 2 - inner_margin, shield_top + shield_width // 6 + inner_margin // 2),
        (center_x + shield_width // 2 - inner_margin, shield_bottom - shield_width // 3 - inner_margin),
        (center_x, shield_bottom - inner_margin * 2),
        (center_x - shield_width // 2 + inner_margin, shield_bottom - shield_width // 3 - inner_margin),
        (center_x - shield_width // 2 + inner_margin, shield_top + shield_width // 6 + inner_margin // 2),
    ]
    draw.polygon(inner_points, fill=(52, 152, 219, 255))
    
    # Draw checkmark (white)
    check_size = size // 3
    check_start_x = center_x - check_size // 3
    check_start_y = center_x
    check_mid_x = center_x - check_size // 8
    check_mid_y = center_x + check_size // 4
    check_end_x = center_x + check_size // 2
    check_end_y = center_x - check_size // 6
    
    line_width = max(size // 20, 3)
    
    # Draw checkmark with thick lines
    draw.line(
        [(check_start_x, check_start_y), (check_mid_x, check_mid_y)],
        fill=(255, 255, 255, 255),
        width=line_width
    )
    draw.line(
        [(check_mid_x, check_mid_y), (check_end_x, check_end_y)],
        fill=(255, 255, 255, 255),
        width=line_width
    )
    
    # Add subtle highlight for 3D effect
    highlight_points = [
        (center_x - shield_width // 4, shield_top + shield_width // 4),
        (center_x, shield_top + shield_width // 5),
        (center_x, shield_top + shield_width // 3),
        (center_x - shield_width // 4, shield_top + shield_width // 2.5),
    ]
    draw.polygon(highlight_points, fill=(255, 255, 255, 40))
    
    return img


def main():
    """Generate icon files."""
    print("Generating application icon...")
    
    # Create 256x256 icon
    icon_256 = create_shield_icon(256)
    
    # Save PNG
    icon_256.save("icon.png", "PNG")
    print("✓ Created icon.png (256x256)")
    
    # Create multi-resolution ICO file
    # Windows uses different sizes for different contexts
    sizes = [16, 32, 48, 64, 128, 256]
    icons = [create_shield_icon(size) for size in sizes]
    
    # Save ICO with multiple resolutions
    icon_256.save(
        "icon.ico",
        format="ICO",
        sizes=[(size, size) for size in sizes],
        append_images=icons[:-1]  # Exclude the last one (256) as it's the base
    )
    print("✓ Created icon.ico (multi-resolution)")
    print("\nIcon files created successfully!")
    print("You can now build the executable with: pyinstaller keylogger_detector.spec")


if __name__ == "__main__":
    main()
