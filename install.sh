#!/usr/bin/env bash
set -e

echo "=========================================="
echo "    EmergencyMesh Installation Script     "
echo "=========================================="

# 1. Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "[!] Python 3 is not installed."
    if command -v pkg &> /dev/null; then
        echo "[*] Installing Python 3 in Termux..."
        pkg update && pkg install -y python
    else
        echo "[!] Please install Python 3 manually."
        exit 1
    fi
else
    echo "[✓] Python 3 detected: $(python3 --version)"
fi

# 2. Check/Install Termux API package if in Termux
if command -v pkg &> /dev/null; then
    echo "[*] Checking Termux API package..."
    if ! command -v termux-location &> /dev/null; then
        echo "[*] Installing termux-api for GPS support..."
        pkg install -y termux-api || true
    else
        echo "[✓] termux-location utility detected."
    fi
fi

# 3. Create config directory
CONFIG_DIR="$HOME/.emergency_mesh"
mkdir -p "$CONFIG_DIR"
echo "[✓] Configuration directory created at: $CONFIG_DIR"

# 4. Instructions for Termux Permissions
echo ""
echo "------------------------------------------"
echo "        Termux Setup & Permissions        "
echo "------------------------------------------"
echo "To ensure GPS features work properly on Android:"
echo " 1. Install 'Termux:API' app from F-Droid or Play Store."
echo " 2. Run: termux-setup-storage"
echo " 3. Grant Location permissions when prompted by Android."
echo ""
echo "------------------------------------------"
echo "           How to Run Node                "
echo "------------------------------------------"
echo "Run the application on your Android phone using:"
echo "  python3 -m emergency_mesh"
echo "=========================================="
