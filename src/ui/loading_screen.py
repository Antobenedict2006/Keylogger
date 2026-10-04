"""
Loading screen with animated concentric rotating rings
Based on the Stitch Concentric Motion design
"""

import tkinter as tk
from tkinter import ttk
import math


class LoadingScreen:
    """
    Animated loading screen with rotating concentric rings
    """
    
    def __init__(self, parent=None):
        """Initialize the loading screen"""
        if parent:
            self.root = tk.Toplevel(parent)
        else:
            self.root = tk.Tk()
        
        self.root.title("Loading...")
        self.root.overrideredirect(True)  # Remove window decorations
        
        # Set window size and center it
        width = 500
        height = 500
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Make window stay on top
        self.root.attributes('-topmost', True)
        
        # Dark background matching the design
        self.root.configure(bg='#0e0e12')
        
        # Create main container
        main_frame = tk.Frame(self.root, bg='#0e0e12')
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas for drawing the rotating rings
        self.canvas = tk.Canvas(
            main_frame,
            width=400,
            height=400,
            bg='#0e0e12',
            highlightthickness=0
        )
        self.canvas.pack(pady=20)
        
        # Progress label
        self.progress_label = tk.Label(
            main_frame,
            text="0%",
            font=('Segoe UI', 24, 'bold'),
            bg='#0e0e12',
            fg='#e4e1e8'
        )
        self.progress_label.pack(pady=5)
        
        # Status label
        self.status_label = tk.Label(
            main_frame,
            text="Initializing...",
            font=('Segoe UI', 10),
            bg='#0e0e12',
            fg='#94a3b8'
        )
        self.status_label.pack(pady=5)
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(
            main_frame,
            mode='determinate',
            length=300
        )
        self.progress_bar.pack(pady=10)
        
        # Animation state
        self.angle1 = 0  # Outer ring (clockwise)
        self.angle2 = 0  # Middle ring (counter-clockwise)
        self.angle3 = 0  # Inner ring (clockwise)
        self.animation_running = False
        
        # Ring parameters
        self.center_x = 200
        self.center_y = 200
        self.ring_colors = ['#00f0ff', '#ff007a', '#3b82f5']  # Cyan, Magenta, Blue
        
    def draw_star_ring(self, radius, points, angle, color, width=3):
        """Draw a star-shaped ring with the given parameters"""
        coords = []
        
        # Create star points
        for i in range(points * 2):
            current_angle = (angle + i * 180 / points) * math.pi / 180
            if i % 2 == 0:
                # Outer point
                r = radius
            else:
                # Inner point (creates the star effect)
                r = radius * 0.85
            
            x = self.center_x + r * math.cos(current_angle)
            y = self.center_y + r * math.sin(current_angle)
            coords.extend([x, y])
        
        # Draw the polygon
        if len(coords) >= 6:
            return self.canvas.create_polygon(
                coords,
                outline=color,
                fill='',
                width=width,
                smooth=True
            )
        return None
    
    def animate_rings(self):
        """Animate the concentric rings"""
        if not self.animation_running:
            return
            
        # Clear canvas
        self.canvas.delete('all')
        
        # Draw ambient glow in center
        for i in range(10, 0, -1):
            opacity = int(255 * (i / 20))
            color = f'#{opacity:02x}{opacity:02x}{opacity:02x}'
            self.canvas.create_oval(
                self.center_x - i * 10,
                self.center_y - i * 10,
                self.center_x + i * 10,
                self.center_y + i * 10,
                outline=color,
                width=1
            )
        
        # Draw outer ring (24 points, clockwise, cyan)
        self.draw_star_ring(150, 24, self.angle1, self.ring_colors[0], width=3)
        
        # Draw middle ring (18 points, counter-clockwise, magenta)
        self.draw_star_ring(110, 18, self.angle2, self.ring_colors[1], width=3)
        
        # Draw inner ring (12 points, clockwise, blue)
        self.draw_star_ring(70, 12, self.angle3, self.ring_colors[2], width=2)
        
        # Draw center dot
        self.canvas.create_oval(
            self.center_x - 5,
            self.center_y - 5,
            self.center_x + 5,
            self.center_y + 5,
            fill='#ffffff',
            outline='#ffffff'
        )
        
        # Update angles
        self.angle1 = (self.angle1 + 1) % 360  # Slow clockwise
        self.angle2 = (self.angle2 - 1.5) % 360  # Faster counter-clockwise
        self.angle3 = (self.angle3 + 2) % 360  # Fastest clockwise
        
        # Schedule next animation frame
        if self.animation_running:
            self.root.after(30, self.animate_rings)  # ~33 FPS
    
    def start_animation(self):
        """Start the ring animation"""
        if not self.animation_running:
            self.animation_running = True
            self.animate_rings()  # Start the animation loop
    
    def stop_animation(self):
        """Stop the ring animation"""
        self.animation_running = False
    
    def update_progress(self, value, status=None):
        """
        Update progress bar and percentage
        
        Args:
            value: Progress value (0-100)
            status: Optional status message
        """
        self.progress_bar['value'] = value
        self.progress_label.config(text=f"{int(value)}%")
        
        if status:
            self.status_label.config(text=status)
        
        self.root.update()
    
    def show(self):
        """Show the loading screen"""
        self.start_animation()
        self.root.deiconify()
        self.root.update()
    
    def close(self):
        """Close the loading screen"""
        self.stop_animation()
        self.root.destroy()


def test_loading_screen():
    """Test function for the loading screen"""
    import time
    
    loader = LoadingScreen()
    loader.show()
    
    # Simulate loading progress
    for i in range(0, 101, 5):
        time.sleep(0.2)
        status_messages = [
            "Initializing system...",
            "Loading configuration...",
            "Starting monitor...",
            "Loading ML model...",
            "Preparing analyzer...",
            "Setting up database...",
            "Configuring alerts...",
            "Almost ready...",
            "Finalizing...",
            "Ready!"
        ]
        status = status_messages[min(i // 10, len(status_messages) - 1)]
        loader.update_progress(i, status)
    
    time.sleep(1)
    loader.close()


if __name__ == '__main__':
    test_loading_screen()
