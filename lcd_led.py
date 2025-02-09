from lcd_lib import lcd_st7796
import machine
import time
import framebuf


HORIZONTAL = True
REVERSE = False
BUTTON_ON = (10, 10, 100, 50)
BUTTON_OFF = (130, 10, 100, 50)


def draw_button_with_text(lcd, button, bg_color, label, text_color) -> None:
    x, y, w, h = button

    # RGB565 requires 2 bytes per pixel
    buf = bytearray(w * h * 2)
    fb = framebuf.FrameBuffer(buf, w, h, framebuf.RGB565)
    fb.fill(bg_color)

    # built in font is 8x8 pixel
    text_width = len(label) * 8
    text_height = 8
    text_x = (w - text_width) // 2
    text_y = (h - text_height) // 2
    fb.text(label, text_x, text_y, text_color)

    # draw
    lcd.set_windows(x, y, x + w - 1, y + h - 1)
    lcd.dc(1)
    lcd.cs(0)
    lcd.bus.write(buf)
    lcd.cs(1)


lcd = lcd_st7796(horizontal=HORIZONTAL, reverse=REVERSE)
lcd.clear_display()

draw_button_with_text(lcd, BUTTON_ON, 0x07E0, "On", 0xFFFF)
draw_button_with_text(lcd, BUTTON_OFF, 0xF800, "Off", 0xFFFF)

led = machine.Pin("LED", machine.Pin.OUT)

while True:
    for x, y in lcd.get_touch_xy():
        bx, by, bw, bh = BUTTON_ON
        if (bx <= x < bx + bw) and (by <= y < by + bh):
            led.on()
            print("LED ON")
            time.sleep_ms(300)
        bx, by, bw, bh = BUTTON_OFF
        if (bx <= x < bx + bw) and (by <= y < by + bh):
            led.off()
            print("LED OFF")
            time.sleep_ms(300)
    time.sleep_ms(10)
