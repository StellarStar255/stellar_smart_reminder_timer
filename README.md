# StellarPulse - 星际脉动

A smart task timer and reminder app for macOS.

## Features

- **Preset Timers** - Quick-start with preset time cards, or create custom timers
- **Category Management** - Organize tasks by categories (study, work, exercise, etc.)
- **Statistics Dashboard** - View time distribution charts and task analytics
- **Dark Mode** - Full light/dark theme support
- **System Tray** - Runs in background with macOS menu bar icon
- **Notifications** - In-app and system notifications with alarm sounds
- **Drag & Drop** - Reorder active timer cards
- **Task Notes** - Attach notes to tasks via notebook dialog

## Requirements

- macOS 12.0+
- Python 3.10+

## Installation

1. Clone the repository:

```bash
git clone 
cd stellar_smart_reminder_timer
```

2. Create a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Start the application:

```bash
python main.py
```

### Basic Operations

- **Start a timer** - Click a preset button at the top, or click "+ Custom" to create your own
- **Pause / Resume** - Click the pause button on a running timer card
- **Category filter** - Use the left sidebar to filter tasks by category
- **Search presets** - Type in the search box to filter preset timers
- **Dark mode** - Click the theme toggle button in the top-right corner
- **Alarm mode** - Toggle between continuous alarm and 3-beep mode

### Background Mode

Closing the main window minimizes the app to the macOS menu bar. Click the tray icon to reopen, or right-click for options:

- **Show Window** - Bring the main window back
- **Quit** - Exit the application completely

### Statistics

The dashboard at the bottom shows:

- **Running timers** - Number of active timers
- **Today's focus** - Total focus time today
- **Streak** - Consecutive active days
- **Time distribution** - Weekly time breakdown chart
- **Task stats** - Time per task with date range filters

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
