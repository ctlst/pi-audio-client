#!/usr/bin/env python3
"""Quick test script for Pi Audio Client."""

import sys
import time
from gpiozero import LED, Button
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Test GPIO
print("\n" + "="*50)
print("Testing GPIO LEDs and Buttons")
print("="*50)

try:
    # Initialize LEDs
    led_idle = LED(17)
    led_listening = LED(18)
    print("✓ LEDs initialized (GPIO 17, 18)")
    
    # Test LEDs
    print("\nTesting LEDs...")
    led_idle.on()
    print("  - Green LED ON")
    time.sleep(1)
    led_idle.off()
    led_listening.on()
    print("  - Red LED ON")
    time.sleep(1)
    led_listening.off()
    print("✓ LEDs working")
    
    # Initialize Buttons
    btn_ptt = Button(20, pull_up=True)
    btn_cancel = Button(21, pull_up=True)
    print("✓ Buttons initialized (GPIO 20, 21)")
    
    # Test buttons
    print("\nTesting Buttons...")
    print("  - Press PTT button...")
    start = time.time()
    while time.time() - start < 5:
        if btn_ptt.is_pressed:
            print("  ✓ PTT button detected!")
            break
        time.sleep(0.1)
    else:
        print("  ⚠ PTT button not detected (check wiring)")
    
    print("  - Press Cancel button...")
    start = time.time()
    while time.time() - start < 5:
        if btn_cancel.is_pressed:
            print("  ✓ Cancel button detected!")
            break
        time.sleep(0.1)
    else:
        print("  ⚠ Cancel button not detected (check wiring)")
    
    # Cleanup
    led_idle.close()
    led_listening.close()
    btn_ptt.close()
    btn_cancel.close()
    
    print("\n✓ GPIO Test Complete!")
    
except Exception as e:
    print(f"\n✗ GPIO Test Failed: {e}")
    sys.exit(1)

# Test Audio
print("\n" + "="*50)
print("Testing Audio Input/Output")
print("="*50)

try:
    import pyaudio
    
    p = pyaudio.PyAudio()
    
    # Test input
    print("\nTesting Audio Input...")
    input_device = None
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            if 'USB' in info['name'].upper() or 'Headset' in info['name'].upper():
                input_device = info['name']
                print(f"  ✓ Found USB/Headset input: {input_device}")
                break
    
    if not input_device:
        # Use default
        input_device = "default"
        print("  ✓ Using default input device")
    
    # Test output
    print("\nTesting Audio Output...")
    output_device = None
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxOutputChannels'] > 0:
            if 'USB' in info['name'].upper() or 'Headset' in info['name'].upper():
                output_device = info['name']
                print(f"  ✓ Found USB/Headset output: {output_device}")
                break
    
    if not output_device:
        output_device = "default"
        print("  ✓ Using default output device")
    
    p.terminate()
    print("\n✓ Audio Test Complete!")
    
except Exception as e:
    print(f"\n✗ Audio Test Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test hermes-agent connection
print("\n" + "="*50)
print("Testing hermes-agent Connection")
print("="*50)

try:
    import requests
    
    # Default URL (Mac hermes-agent)
    url = "http://100.96.134.76:8081/v1"
    print(f"Checking connection to: {url}")
    
    response = requests.get(f"{url}/health", timeout=5)
    
    if response.status_code == 200:
        print("✓ hermes-agent is reachable!")
        print(f"  Response: {response.json()}")
    else:
        print(f"✗ hermes-agent returned status: {response.status_code}")
        print("  (This might be expected if /health endpoint doesn't exist)")
        
except Exception as e:
    print(f"✗ Connection Test Failed: {e}")
    print("\n  This is OK if:")
    print("  - hermes-agent is not running on the Mac")
    print("  - The IP address is wrong")
    print("  - Firewall is blocking the connection")

print("\n" + "="*50)
print("All Tests Complete!")
print("="*50)