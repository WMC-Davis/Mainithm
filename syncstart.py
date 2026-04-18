import time
from pynput.keyboard import Controller, Key

key_mai = Key.f1
key_chu = 'a'

t_mai = 800
t_chu = 500

keyboard = Controller()

def busy_wait(ms):
    target = time.perf_counter() + ms / 1000
    while time.perf_counter() < target:
        pass

def start():
    if t_mai - t_chu > 0:
        keyboard.press(key_mai)
        keyboard.release(key_mai)

        busy_wait(t_mai - t_chu)
        print("waited for " + str(t_mai - t_chu) + " ms")

        keyboard.press(key_chu)
        keyboard.release(key_chu)

    else:
        keyboard.press(key_chu)
        keyboard.release(key_chu)

        busy_wait(t_chu - t_mai)
        print("waited for " + str(t_chu - t_mai) + " ms")

        keyboard.press(key_mai)
        keyboard.release(key_mai)

# time.sleep(3)
# start()
