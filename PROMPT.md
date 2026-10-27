# The AI Installation Prompt for Hisense & VIDAA OS

> **Copy and paste this prompt into Claude Code, Gemini CLI, ChatGPT, Cursor, or Antigravity to automatically install Aura TV onto your Hisense VIDAA TV.**

---

```markdown
I want to install Aura TV on my Hisense Smart TV (running VIDAA OS) and replace the cluttered, ad-filled home screen with a clean, 60FPS minimalist launcher.

My TV's IP address on my local Wi-Fi is: <YOUR_TV_IP_HERE>

Work step by step:
1. Check that Python 3 and the `paho-mqtt` package are available in my environment. If `paho-mqtt` is missing, install it (`pip install paho-mqtt`).
2. Verify network connectivity to my TV on port 36669 (the TV's local companion protocol).
3. Clone the Aura TV repository if not already in your working directory:
   git clone https://github.com/cralex11/aura-tv.git
   cd aura-tv
4. Run the injection tool:
   python3 tools/inject.py <YOUR_TV_IP_HERE>
5. When the 4-digit pairing PIN pops up on my TV screen, ask me for it, then submit it to complete mutual TLS authorization.
6. Verify that the Aura TV launcher tile is permanently registered in the TV's application database and send the signal to launch it on my screen.
7. Tell me once it is launched and guide me through the quick remote control steps to pin it to position #1 on my home row and set auto-boot on power-on.
```

---

## Tips Before You Run

- **Network**: Ensure your computer and your Smart TV are connected to the same home Wi-Fi network or router subnet.
- **TV Powered On**: Keep your TV powered on during the 60-second pairing window.
- **Finding Your TV IP**: On your TV remote, go to **Settings (⚙️)** $\rightarrow$ **Network** $\rightarrow$ **Network Configuration** (or Network Status). You will see an IP like `192.168.1.XX`.
