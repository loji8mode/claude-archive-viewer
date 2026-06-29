# Claude Archive Smart Viewer

A Python utility to convert standard Claude AI chat exports (`conversations.json`) into a local, interactive web interface.

## Features
* **Thinking Visualization:** Collapses long model reasoning blocks into clickable, expandable sections.
* **Artifact Support:** Renders HTML/SVG artifacts inside isolated `iframe` elements with options to view raw code and download.
* **Dark Theme:** Interface optimized for comfortable nighttime reading.
* **Standalone:** The entire output is saved into a single HTML file that works completely offline.

## Usage

1. Place your exported `conversations.json` file in the same directory as the script.
2. Run the script:
   ```bash
   python extractor.py
3. Open the generated viewer.html file in any web browser.