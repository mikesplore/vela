# Vela Sample User Questions

This document shows example questions you can ask the Vela assistant and the type of response you can expect.

## 1. Location and IP

### Question
- "Where am I?"
- "What is my current public IP and location?"
- "Tell me my local and external IP addresses."

### Example assistant response
- "Your local IP is `192.168.1.10`, your public IP is `1.2.3.4`, and your location appears to be San Francisco, California, United States (`America/Los_Angeles`)."

## 2. Network status

### Question
- "What WiFi network am I connected to?"
- "Show me available WiFi networks."
- "Is WiFi enabled?"

### Example assistant response
- "You are connected to `MyWifi` with a strong signal. Available networks include `OtherNetwork` and `GuestWifi`."

## 3. Bluetooth management

### Question
- "Show me nearby Bluetooth devices."
- "Turn Bluetooth on."
- "Turn Bluetooth off."
- "Is Bluetooth enabled?"

### Example assistant response
- "Bluetooth devices found: `Test Device` (`AA:BB:CC:DD:EE:FF`)."
- "Bluetooth has been turned on."
- "Bluetooth has been turned off."

## 4. Ping and connection checks

### Question
- "Ping `8.8.8.8`."
- "Check if the network can reach google.com."

### Example assistant response
- "Ping to `8.8.8.8` completed: 4 packets transmitted, 4 received, 0% packet loss, average RTT 15.0 ms."

## 5. System info

### Question
- "What is the CPU model and how much RAM do I have?"
- "What is the OS version and hostname?"
- "List connected USB devices."

### Example assistant response
- "Your CPU is an Intel Core i7-1165G7 with 4 physical cores and 8 logical cores."
- "The OS is Linux with kernel 5.15.0-79-generic. Hostname is `mylaptop` and current user is `mike`."
- "Connected USB devices include `Logitech USB Receiver` and `Kingston DataTraveler`."

## 6. Media and audio controls

### Question
- "What is currently playing?"
- "Increase the volume by 10%."
- "Mute the audio."

### Example assistant response
- "Now playing: `Test Song` by `Test Artist`."
- "Volume increased to 70%."
- "Audio is now muted."

## 7. Power controls

### Question
- "Restart the machine."
- "Put the PC to sleep."

### Example assistant response
- "Restart initiated."
- "The machine is going to sleep."

## Notes
- The assistant decides whether to call the appropriate tool based on the question.
- For location questions, the agent uses your public IP to resolve approximate geo-location.
- For Bluetooth actions, the agent uses `rfkill` and `bluetoothctl` on the host system.
- The assistant requires valid authentication and the configured DashScope integration to process chat prompts.
