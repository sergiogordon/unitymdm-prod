# Screenshots Directory

This directory contains screenshots for the main README documentation.

## Required Screenshots

To complete the documentation, add the following screenshot files to this directory:

### 1. `dashboard.png`
- **Page**: Main Dashboard (`/demo` or authenticated `/`)
- **What to show**: 
  - KPI cards (Total Devices, Online, Offline stats)
  - Device table with multiple enrolled devices
  - Sidebar navigation
  - Real-time status indicators

### 2. `apk-management.png`
- **Page**: APK Management (`/demo/apk-management` or authenticated `/apk-management`)
- **What to show**:
  - APK list with version numbers
  - Upload APK button
  - Deploy controls
  - Installation progress indicators (if available)

### 3. `adb-setup.png`
- **Page**: ADB Setup (`/demo/adb-setup` or authenticated `/adb-setup`)
- **What to show**:
  - Device alias input field
  - Generated ADB script display
  - Copy and Download buttons
  - Script content showing enrollment commands

### 4. `remote-control.png`
- **Page**: Remote Control (`/demo/remote-control` or authenticated `/remote-control`)
- **What to show**:
  - Live device screen stream (if available)
  - Interactive control panel
  - Navigation buttons
  - FPS/latency metrics
  - Feature list

## How to Capture Screenshots

### Using Demo Mode (Recommended)
1. Navigate to `http://localhost:5000/login` (or your deployed URL)
2. Click **"Access Demo"** button
3. Navigate to each page listed above
4. Take screenshots using your browser's screenshot tool or:
   - **macOS**: `Cmd + Shift + 4` (select area)
   - **Windows**: `Win + Shift + S` (Snipping Tool)
   - **Linux**: `PrtScn` or Spectacle/Flameshot

### Using Authenticated Access
1. Log in with your admin credentials
2. Navigate to each page
3. Ensure you have devices enrolled for realistic screenshots
4. Capture screenshots as described above

## Image Specifications

- **Format**: PNG (for transparency and quality)
- **Resolution**: 1920x1080 or higher recommended
- **Naming**: Use exact filenames listed above
- **Size**: Keep under 1MB per file (optimize if needed)

## Browser Screenshot Tools

- **Chrome DevTools**: F12 → Cmd/Ctrl+Shift+P → "Capture full size screenshot"
- **Firefox**: Right-click → "Take Screenshot" → "Save full page"
- **Arc Browser**: Cmd+Shift+4 built-in
