import pyaudio

p = pyaudio.PyAudio()
print("Available audio devices:")
print("-" * 60)
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    print(f"{i}: {info['name']}")
    print(f"   Input channels: {info['maxInputChannels']}, Output channels: {info['maxOutputChannels']}")
print("-" * 60)
print(f"Default input device: {p.get_default_input_device_info()['name']}")
print(f"Default output device: {p.get_default_output_device_info()['name']}")
p.terminate()
