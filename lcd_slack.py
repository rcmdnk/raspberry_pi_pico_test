from lcd_lib import lcd_st7796, draw_button, hex_to_rgb565
import time
import requests
import machine


WEBHOOK_URL = "<YOUR_SLACK_WEBHOOK_URL>"
HORIZONTAL = True
REVERSE = False
BUTTON = (10, 10, 100, 50)


lcd = lcd_st7796(horizontal=HORIZONTAL, reverse=REVERSE)
lcd.clear_display()

draw_button(lcd, BUTTON, hex_to_rgb565("#36C5F0"), "Notify", 0xFFFF)


def slack_notify():
    rtc = machine.RTC()
    datetime = rtc.datetime()
    t = f"{datetime[0]}-{datetime[1]:02d}-{datetime[2]:02d} {datetime[4]:02d}:{datetime[5]:02d}:{datetime[6]:02d}"

    response = requests.post(
        WEBHOOK_URL,
        json={"text": f"From Raspberry Pi Pico ({t})"},
        timeout=60,
    )
    print("Status code:", +response.status_code)
    print(response.text)


while True:
    for x, y in lcd.get_touch_xy():
        bx, by, bw, bh = BUTTON
        if (bx <= x < bx + bw) and (by <= y < by + bh):
            print("Slack notify")
            slack_notify()
            time.sleep(1)
            lcd.clear_touch()
            break
    time.sleep_ms(10)
