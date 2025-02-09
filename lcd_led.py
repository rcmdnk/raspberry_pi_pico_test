from lcd_lib import lcd_st7796, draw_button
import machine
import time


HORIZONTAL = True
REVERSE = False
BUTTON_ON = (10, 10, 100, 50)
BUTTON_OFF = (130, 10, 100, 50)


lcd = lcd_st7796(horizontal=HORIZONTAL, reverse=REVERSE)
lcd.clear_display()

draw_button(lcd, BUTTON_ON, 0x07E0, "On", 0xFFFF)
draw_button(lcd, BUTTON_OFF, 0xF800, "Off", 0xFFFF)

led = machine.Pin("LED", machine.Pin.OUT)

while True:
    for x, y in lcd.get_touch_xy():
        bx, by, bw, bh = BUTTON_ON
        if (bx <= x < bx + bw) and (by <= y < by + bh):
            led.on()
            print("LED ON")
            time.sleep_ms(100)
            lcd.clear_touch()
            break
        bx, by, bw, bh = BUTTON_OFF
        if (bx <= x < bx + bw) and (by <= y < by + bh):
            led.off()
            print("LED OFF")
            time.sleep_ms(100)
            lcd.clear_touch()
            break
    time.sleep_ms(10)
