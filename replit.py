import tkinter as tk
from tkinter import ttk
import math
import random
import time
from datetime import datetime

class JarvisHUD(tk.Tk):
    def __init__(self):
        super().__init__()

        # Window Setup
        self.title("J.A.R.V.I.S. MARK 85")
        self.attributes('-fullscreen', True)
        self.configure(bg='black')
        
        # Colors
        self.colors = {
            'bg': '#000000',
            'primary': '#FF0000',     # Red
            'secondary': '#00FFFF',   # Cyan
            'text': '#FFFFFF',        # White
            'dim': '#330000'          # Dim Red
        }

        # Main Canvas
        self.width = self.winfo_screenwidth()
        self.height = self.winfo_screenheight()
        self.canvas = tk.Canvas(self, width=self.width, height=self.height, 
                              bg=self.colors['bg'], highlightthickness=0)
        self.canvas.pack()

        # Exit binding (Escape key)
        self.bind('<Escape>', lambda e: self.destroy())

        # Initialize Components
        self.setup_ui()
        self.animate()

    def setup_ui(self):
        # 1. Top Bar
        self.draw_top_bar()
        
        # 2. Central Arc Reactor
        self.draw_arc_reactor(self.width//2, self.height//2 + 100)
        
        # 3. Side Panels
        self.draw_sidebar_left()
        self.draw_sidebar_right()
        
        # 4. Graphs
        self.cpu_data = [0] * 20
        self.draw_cpu_graph()

    def draw_top_bar(self):
        # Time Display
        self.time_text = self.canvas.create_text(self.width//2, 50, 
                                               text="00:00:00", 
                                               font=("Courier", 40, "bold"), 
                                               fill=self.colors['primary'])
        
        # Status Label
        self.canvas.create_text(self.width//2, 80, 
                              text="SYSTEM ONLINE", 
                              font=("Arial", 10), 
                              fill=self.colors['secondary'])

        # Top Borders
        self.canvas.create_line(0, 20, self.width, 20, fill=self.colors['primary'], width=2)
        self.canvas.create_line(self.width//2 - 150, 20, self.width//2 - 100, 100, 
                              fill=self.colors['primary'], width=2)
        self.canvas.create_line(self.width//2 + 150, 20, self.width//2 + 100, 100, 
                              fill=self.colors['primary'], width=2)

    def draw_arc_reactor(self, x, y):
        # Outer Ring
        self.canvas.create_oval(x-100, y-100, x+100, y+100, 
                              outline=self.colors['secondary'], width=2)
        self.canvas.create_oval(x-90, y-90, x+90, y+90, 
                              outline=self.colors['secondary'], width=1)
        
        # Inner Core
        self.canvas.create_oval(x-30, y-30, x+30, y+30, 
                              fill=self.colors['text'], outline=self.colors['secondary'])
        
        # Rotating parts (stored for animation)
        self.reactor_rings = []
        for i in range(3):
            ring = self.canvas.create_arc(x-70, y-70, x+70, y+70, 
                                        start=i*120, extent=60, 
                                        style=tk.ARC, outline=self.colors['secondary'], width=5)
            self.reactor_rings.append(ring)

    def draw_sidebar_left(self):
        # Left Info Panel
        x = 50
        y = self.height // 2 - 100
        
        labels = ["ASUS SYSTEM", "MAINTENANCE", "DIAGNOSTIC", "PROTOCOL"]
        for i, label in enumerate(labels):
            self.canvas.create_text(x, y + i*60, text=label, anchor="w",
                                  font=("Arial", 12), fill=self.colors['primary'])
            self.canvas.create_rectangle(x-10, y + i*60 - 15, x+200, y + i*60 + 15,
                                       outline=self.colors['dim'])

    def draw_sidebar_right(self):
        # Right Info Panel
        x = self.width - 250
        y = self.height // 2 - 100
        
        labels = ["OFFICE", "MEDIA", "NETWORK", "SETTINGS"]
        for i, label in enumerate(labels):
            self.canvas.create_text(x, y + i*60, text=label, anchor="e",
                                  font=("Arial", 12), fill=self.colors['primary'])
            self.canvas.create_rectangle(x-20, y + i*60 - 15, x+200, y + i*60 + 15,
                                       outline=self.colors['dim'])

    def draw_cpu_graph(self):
        x = self.width - 350
        y = 100
        w = 300
        h = 150
        
        self.canvas.create_rectangle(x, y, x+w, y+h, outline=self.colors['primary'])
        self.canvas.create_text(x, y-15, text="[CPU HISTORY]", fill=self.colors['primary'], anchor="w")
        
        self.graph_lines = []
        step = w / len(self.cpu_data)
        for i in range(len(self.cpu_data)-1):
            line = self.canvas.create_line(x + i*step, y + h - self.cpu_data[i],
                                         x + (i+1)*step, y + h - self.cpu_data[i+1],
                                         fill=self.colors['secondary'])
            self.graph_lines.append(line)

    def update_cpu_graph(self):
        # Shift data
        self.cpu_data.pop(0)
        self.cpu_data.append(random.randint(20, 140))
        
        # Redraw lines
        x = self.width - 350
        y = 100
        w = 300
        h = 150
        step = w / len(self.cpu_data)
        
        # Delete old lines
        for line in self.graph_lines:
            self.canvas.delete(line)
        self.graph_lines = []
        
        # Draw new lines
        for i in range(len(self.cpu_data)-1):
            line = self.canvas.create_line(x + i*step, y + h - self.cpu_data[i],
                                         x + (i+1)*step, y + h - self.cpu_data[i+1],
                                         fill=self.colors['secondary'])
            self.graph_lines.append(line)

    def animate(self):
        # 1. Update Time
        now = datetime.now().strftime("%H:%M:%S")
        self.canvas.itemconfig(self.time_text, text=now)
        
        # 2. Update Graph
        self.update_cpu_graph()
        
        # 3. Rotate Reactor (Simulation)
        # In pure tkinter, rotation is hard without PIL, so we pulse colors instead
        pulse = random.choice([self.colors['secondary'], self.colors['text']])
        for ring in self.reactor_rings:
            self.canvas.itemconfig(ring, outline=pulse)

        # Loop
        self.after(100, self.animate)

if __name__ == "__main__":
    app = JarvisHUD()
    app.mainloop()
