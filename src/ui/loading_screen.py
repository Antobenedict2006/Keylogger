"""
loading_screen.py
=================
Animated loading screen shown during application initialization.

Features:
  - Concentric rotating rings (based on the stitch design)
  - Progress counter and status messages
  - Non-blocking - runs in a separate thread
  - Automatically closes when initialization completes
"""

import math
import threading
import time
import tkinter as tk
from tkinter import ttk


class LoadingScreen:
    """
    Animated loading screen with rotating concentric rings.
    
    Usage::
        loading = LoadingScreen()
        loading.show()
        loading.update_progress(50, "Loading components...")
        # ... do initialization work ...
        loading.close()
    """
    
    def __init__(self):
        self.root = None
        self.canvas = None
        self.progress_label = None
        self.status_label = None
        self.animation_running = False
        self.current_progress = 0
        self.current_status = "Initializing..."
        
        # Ring animation angles
        self.outer_angle = 0
        self.middle_angle = 0
        self.inner_angle = 0
        
        # Colors (from the stitch design)
        self.bg_color = "#131317"
        self.cyan_color = "#00f5ff"
        self.magenta_color = "#ff007a"
        self.blue_color = "#3b82f5"
        self.text_color = "#e4e1e8"
        self.text_dim = "#94a3b8"
    
    def show(self):
        """Create and show the loading window in a separate thread."""
        thread = threading.Thread(target=self._create_window, daemon=True)
        thread.start()
        time.sleep(0.1)  # Give window time to appear
    
    def _create_window(self):
        """Create the loading window (runs in separate thread)."""
        self.root = tk.Tk()
        self.root.title("Loading...")
        self.root.configure(bg=self.bg_color)
        
        # Window setup
        window_width = 500
        window_height = 600
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.overrideredirect(True)  # No window decorations
        self.root.attributes("-topmost", True)
        
        # Main container
        container = tk.Frame(self.root, bg=self.bg_color)
        container.pack(fill=tk.BOTH, expand=True, padx=40, pady=60)
        
        # Title
        title = tk.Label(
            container,
            text="KEYLOGGER DETECTOR",
            font=("Segoe UI", 24, "bold"),
            fg=self.text_color,
            bg=self.bg_color
        )
        title.pack(pady=(0, 20))
        
        # Canvas for rotating rings
        self.canvas = tk.Canvas(
            container,
            width=320,
            height=320,
            bg=self.bg_color,
            highlightthickness=0
        )
        self.canvas.pack(pady=20)
        
        # Progress percentage
        self.progress_label = tk.Label(
            container,
            text="0%",
            font=("Consolas", 48, "bold"),
            fg=self.cyan_color,
            bg=self.bg_color
        )
        self.progress_label.pack(pady=10)
        
        # Status message
        self.status_label = tk.Label(
            container,
            text="Initializing...",
            font=("Segoe UI", 11),
            fg=self.text_dim,
            bg=self.bg_color
        )
        self.status_label.pack(pady=5)
        
        # Progress bar
        style = ttk.Style()
        style.theme_use('default')
        style.configure(
            "Loading.Horizontal.TProgressbar",
            troughcolor=self.bg_color,
            background=self.cyan_color,
            borderwidth=0,
            thickness=3
        )
        
        self.progress_bar = ttk.Progressbar(
            container,
            style="Loading.Horizontal.TProgressbar",
            length=300,
            mode='determinate'
        )
        self.progress_bar.pack(pady=20)
        
        # Start animations
        self.animation_running = True
        self._animate_rings()
        self._update_ui()
        
        self.root.mainloop()
    
    def _animate_rings(self):
        """Animate the rotating concentric rings."""
        if not self.animation_running or not self.canvas:
            return
        
        # Clear canvas
        self.canvas.delete("all")
        
        center_x = 160
        center_y = 160
        
        # Draw outer ring (clockwise, cyan)
        self._draw_ring(
            center_x, center_y, 140, 12, self.outer_angle,
            self.cyan_color, 3
        )
        
        # Draw middle ring (counter-clockwise, magenta)
        self._draw_ring(
            center_x, center_y, 100, 16, -self.middle_angle,
            self.magenta_color, 3
        )
        
        # Draw inner ring (clockwise, blue)
        self._draw_ring(
            center_x, center_y, 60, 20, self.inner_angle,
            self.blue_color, 3
        )
        
        # Center dot
        self.canvas.create_oval(
            center_x - 5, center_y - 5,
            center_x + 5, center_y + 5,
            fill="#ffffff",
            outline=""
        )
        
        # Update angles
        self.outer_angle += 1
        self.middle_angle += 1.5
        self.inner_angle += 2
        
        # Schedule next frame
        if self.root:
            self.root.after(30, self._animate_rings)
    
    def _draw_ring(self, cx, cy, radius, points, rotation, color, width):
        """Draw a star-shaped ring."""
        coords = []
        for i in range(points):
            angle = (rotation + i * (360 / points)) * math.pi / 180
            # Alternate between outer and inner radius for star shape
            r = radius if i % 2 == 0 else radius * 0.85
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            coords.extend([x, y])
        
        # Close the polygon
        coords.extend([coords[0], coords[1]])
        
        self.canvas.create_line(
            *coords,
            fill=color,
            width=width,
            smooth=True
        )
    
    def _update_ui(self):
        """Update progress display."""
        if not self.animation_running or not self.root:
            return
        
        try:
            self.progress_label.config(text=f"{self.current_progress}%")
            self.status_label.config(text=self.current_status)
            self.progress_bar['value'] = self.current_progress
            
            # Schedule next update
            self.root.after(100, self._update_ui)
        except:
            pass
    
    def update_progress(self, percent, status=None):
        """Update the progress display (thread-safe)."""
        self.current_progress = int(percent)
        if status:
            self.current_status = status
    
    def close(self):
        """Close the loading screen."""
        self.animation_running = False
        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except:
                pass
