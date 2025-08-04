import serial
import matplotlib.pyplot as plt
from collections import deque

# あなたのArduinoのポートに変更してください
# Macの場合：/dev/cu.usbmodemXXXX など
# ser = serial.Serial("/dev/cu.usbmodem141301", 9600) #usb-micro
ser = serial.Serial("/dev/cu.usbmodem14201", 9600)  # typec-micro

# データバッファ
data = deque([0] * 100, maxlen=1000)

plt.ion()
fig, ax = plt.subplots()
(line,) = ax.plot(data)
ax.set_ylim(0, 20)  # 10bit ADCの範囲 Max1023

while True:
    try:
        line_data = ser.readline().decode().strip()
        value = int(line_data)
        data.append(value)

        line.set_ydata(data)
        line.set_xdata(range(len(data)))
        ax.relim()
        ax.autoscale_view()
        plt.draw()
        plt.pause(0.01)

    except Exception as e:
        print(f"Error: {e}")
