# Raspberry Pi hardware integration plan

Raspberry Pi targeted, desktop simulation tested. No Pi, real sensor, electrical power, camera timing, motor or physical safety validation was performed. This is an AI-assisted personal engineering project; it does not establish professional seniority or independent authorship.

## Bench components and instruments

Raspberry Pi 4 or 5, USB camera and fixed illumination, small bench servo, distance sensor for fill, load cell with a calibrated USB serial bridge, position/limit switch and jam input, separate regulated servo supply.

Required bench tools: digital multimeter for rails and continuity, logic analyzer for GPIO/event timing, USB power meter for approximate input consumption, and a suitable regulated supply. Use an oscilloscope for supply transients and servo noise when progressing beyond a basic bench demonstration. No measurement from these instruments is claimed. Parts prices and exact modules were not selected or purchased.

## Proposed wiring

Example BCM allocation: fill trigger GPIO23 and echo GPIO24 through suitable level conversion; servo signal GPIO18; jam input GPIO17; position acknowledgement GPIO27. Weight readings arrive on a USB serial bridge at 115200 baud as one calibrated gram value per line. Direct HX711 support is not implemented.

Pi GPIO is a 3.3 V interface. Never connect a 5 V ultrasonic echo directly. The gpiozero HC-SR04 guide describes its divider requirement. A bench servo needs a suitable external power rail; do not power it from a GPIO pin. Use a common signal ground and verify voltage and polarity. Demonstrate lighting with an LED; no mains lighting circuit is designed here. Demonstrate gates with an unloaded bench mechanism; the simulation is not suitable for a real gate without independent safety engineering.

## Interface contract

| Interface | Simulation implementation | Target adapter and remaining work |
|---|---|---|
| Camera read | Recorded file and uploaded image | Explicitly authorized OpenCV USB camera; capture cadence and disconnect tests pending |
| Clock now | VirtualClock, explicit advance | MonotonicClock exists; bind scheduling to it and measure deadlines |
| Sensor read | VirtualSensor / RecordedSensor returns value, valid, at | PiMotionSensor, PiDistanceSensor and SerialWeightSensor exist; electrical faults and calibration pending |
| Output write | VirtualOutput retains bounded history | PiDigitalOutput for LED; PiServo takes angle, not a state string; application mapping required |
| Acknowledgement | One-second virtual acknowledgement or manual button | Wire and debounce physical limit/position input; a servo command is not acknowledgement |
| State and log | SQLite event/state transaction | Same database interface; power-loss tests and bounded retention pending |

The shipped app remains in simulation mode. Hardware adapters are explicit optional building blocks, not a plug-and-play Pi deployment. The next integration step is a dedicated runner that timestamps real sensor acquisitions, maps state outputs to pin/angle commands, disables synthetic acknowledgement, and never renews timestamps on cached readings. Keep control outside the inference critical path. The current runtime serializes inference/control requests and uses a virtual clock; do not drive a real mechanism directly from it.

Optional target dependencies: gpiozero and pyserial, installed only on the selected Pi OS with a supported pin factory. Verify compatible package versions on that target. Development and model conversion were tested on Python 3.12 macOS arm64 only.

## Physical validation sequence

1. Check supply voltage and signal levels with outputs disconnected; verify every pin against the board documentation.
2. Log raw sensor values against known distances, weights and transitions; calibrate and inject open/short/disconnect conditions.
3. Run LED-only or unloaded servo commands with explicit limit acknowledgement; measure command, stop and recovery timing.
4. Measure capture-to-decision latency, CPU, memory and thermal behavior during at least an hour of representative load.
5. Test power interruption during database writes and actuator movement; reconcile incomplete items before resuming.
6. Collect consented deployment data, label physical presence/space occupancy/material purity, and split by scene/recording before model tuning.

References: https://www.raspberrypi.com/documentation/computers/raspberry-pi.html ; https://gpiozero.readthedocs.io/en/stable/api_input.html ; https://gpiozero.readthedocs.io/en/stable/api_output.html
