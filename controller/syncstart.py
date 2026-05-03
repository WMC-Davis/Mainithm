import time
from pynput.keyboard import Controller, Key
# syncstart.py generates inputs that will start Maimai and Chunithm game with a time difference. The inputs should be
# mirrored to both machines through Input Director.

key_mai = 'c'
key_chu = 'z'

t_mai = 400 # should always be less than t_chu
t_chu = 3333

keyboard = Controller()

def busy_wait(ms):
    target = time.perf_counter() + ms / 1000
    while time.perf_counter() < target:
        pass

def start():
        keyboard.press(key_chu)
        busy_wait(20)
        keyboard.release(key_chu)

        busy_wait(t_chu - t_mai-20)
        print("waited for " + str(t_chu - t_mai) + " ms")

        keyboard.press(key_mai)
        keyboard.release(key_mai)

# time.sleep(3)
start()
