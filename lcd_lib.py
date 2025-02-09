from machine import Pin, SPI, I2C
import framebuf
import time

LCD_WIDTH = 320
LCD_HEIGHT = 480

I2C_SDA = 6
I2C_SDL = 7
I2C_IRQ = 8
I2C_RST = 5

LCD_DC = 14
LCD_CS = 9
SCK = 10
MOSI = 11
MISO = 12
LCD_RST = 13
LCD_BL = 15


class touch_ft6336u:
    def __init__(
        self,
        device_addr=0x38,
        mode=0,
        i2c_num=1,
        i2c_sda=I2C_SDA,
        i2c_scl=I2C_SDL,
        irq_pin=I2C_IRQ,
        rst_pin=I2C_RST,
        max_touch=5,
    ):
        self.bus = I2C(id=i2c_num, scl=Pin(i2c_scl), sda=Pin(i2c_sda), freq=400_000)
        self.device_addr = device_addr
        self.int = Pin(irq_pin, Pin.IN, Pin.PULL_UP)
        self.rst = Pin(rst_pin, Pin.OUT)

        self.max_touch = max_touch
        self.coordinates = []
        self.reset()
        self.read_flag = True

        self.int.irq(handler=self.int_cb, trigger=Pin.IRQ_FALLING)

    def int_cb(self, pin):
        self.read_touch_data()

    def reset(self):
        self.rst(1)
        time.sleep(0.2)
        self.rst(0)
        time.sleep(0.2)
        self.rst(1)
        time.sleep(0.2)

    def read_bytes(self, reg_addr, length):
        try:
            self.bus.writeto(int(self.device_addr), bytes([reg_addr]))
            rec = self.bus.readfrom(int(self.device_addr), length)
            return rec
        except Exception as e:
            print(f"Error reading bytes: {e}")
            return None

    def clear(self):
        self.coordinates = []

    def read_touch_data(self):
        TOUCH_NUM_REG = 0x02
        TOUCH_XY_REG = 0x03
        buf = self.read_bytes(TOUCH_NUM_REG, 1)
        if buf is not None and buf[0] != 0:
            point_count = buf[0]
            start = 0
            if point_count > self.max_touch:
                self.clear()
                start = point_count - self.max_touch
            elif (overfow := len(self.coordinates) + point_count - self.max_touch) > 0:
                self.coordinates = self.coordinates[overfow:]

            buf = self.read_bytes(TOUCH_XY_REG, 6 * point_count)
            if buf is not None:
                for i in range(start, point_count):
                    self.coordinates.append(
                        (
                            ((buf[(i * 6) + 0] & 0x0F) << 8) + (buf[(i * 6) + 1]),
                            ((buf[(i * 6) + 2] & 0x0F) << 8) + (buf[(i * 6) + 3]),
                        )
                    )

    def get_touch_xy(self):
        coordinates = self.coordinates
        self.clear()
        return coordinates


class lcd_st7796:
    def __init__(self, horizontal=True, reverse=False):
        self.horizontal = horizontal
        self.reverse = reverse

        if self.horizontal:
            self.width = LCD_HEIGHT
            self.height = LCD_WIDTH
        else:
            self.width = LCD_WIDTH
            self.height = LCD_HEIGHT

        self.cs = Pin(LCD_CS, Pin.OUT)
        self.rst = Pin(LCD_RST, Pin.OUT)
        self.bl = Pin(LCD_BL, Pin.OUT)
        self.bl(1)
        self.cs(1)
        self.bus = SPI(1)
        self.bus = SPI(1, 1000_000)
        self.bus = SPI(
            1, 10000_000, polarity=0, phase=0, sck=Pin(SCK), mosi=Pin(MOSI), miso=MISO
        )
        self.dc = Pin(LCD_DC, Pin.OUT)
        self.dc(1)
        self.lcd_init()

        self.touch = touch_ft6336u()

    def clear_display(
        self, color=0xA33F, init_color0=0x00FF, init_color1=0xF00F, sleep=1
    ):
        self.lcd_fill(init_color0)
        time.sleep(sleep)
        self.lcd_fill(init_color1)
        time.sleep(sleep)
        self.lcd_fill(init_color0)
        time.sleep(sleep)
        self.lcd_fill(color)

    def write_cmd(self, cmd):
        self.dc(0)
        self.cs(0)
        self.bus.write(bytearray([cmd]))

    def write_data(self, buf):
        self.dc(1)
        self.cs(0)
        self.bus.write(bytearray([buf]))
        self.cs(1)

    def lcd_init(self):
        self.rst(0)
        time.sleep_ms(100)
        self.rst(1)
        time.sleep_ms(10)

        self.write_cmd(0x11)

        time.sleep_ms(120)

        self.write_cmd(0x36)
        if self.reverse:
            if self.horizontal:
                self.write_data(0x28)
            else:
                self.write_data(0x88)
        else:
            if self.horizontal:
                self.write_data(0xE8)
            else:
                self.write_data(0x48)

        self.write_cmd(0x3A)
        self.write_data(0x05)

        self.write_cmd(0xF0)
        self.write_data(0xC3)

        self.write_cmd(0xF0)
        self.write_data(0x96)

        self.write_cmd(0xB4)
        self.write_data(0x01)

        self.write_cmd(0xB7)
        self.write_data(0xC6)

        self.write_cmd(0xC0)
        self.write_data(0x80)
        self.write_data(0x45)

        self.write_cmd(0xC1)
        self.write_data(0x13)

        self.write_cmd(0xC2)
        self.write_data(0xA7)

        self.write_cmd(0xC5)
        self.write_data(0x0A)

        self.write_cmd(0xE8)
        self.write_data(0x40)
        self.write_data(0x8A)
        self.write_data(0x00)
        self.write_data(0x00)
        self.write_data(0x29)
        self.write_data(0x19)
        self.write_data(0xA5)
        self.write_data(0x33)

        self.write_cmd(0xE0)
        self.write_data(0xD0)
        self.write_data(0x08)
        self.write_data(0x0F)
        self.write_data(0x06)
        self.write_data(0x06)
        self.write_data(0x33)
        self.write_data(0x30)
        self.write_data(0x33)
        self.write_data(0x47)
        self.write_data(0x17)
        self.write_data(0x13)
        self.write_data(0x13)
        self.write_data(0x2B)
        self.write_data(0x31)

        self.write_cmd(0xE1)
        self.write_data(0xD0)
        self.write_data(0x0A)
        self.write_data(0x11)
        self.write_data(0x0B)
        self.write_data(0x09)
        self.write_data(0x07)
        self.write_data(0x2F)
        self.write_data(0x33)
        self.write_data(0x47)
        self.write_data(0x38)
        self.write_data(0x15)
        self.write_data(0x16)
        self.write_data(0x2C)
        self.write_data(0x32)

        self.write_cmd(0xF0)
        self.write_data(0x3C)

        self.write_cmd(0xF0)
        self.write_data(0x69)

        time.sleep_ms(120)

        self.write_cmd(0x21)

        self.write_cmd(0x29)

    def set_windows(self, Xstart, Ystart, Xend, Yend):
        self.write_cmd(0x2A)
        self.write_data(Xstart >> 8)
        self.write_data(Xstart)
        self.write_data((Xend - 0) >> 8)
        self.write_data(Xend - 0)

        self.write_cmd(0x2B)
        self.write_data((Ystart) >> 8)
        self.write_data(Ystart)
        self.write_data(((Yend) - 0) >> 8)
        self.write_data((Yend) - 0)
        self.write_cmd(0x2C)

    def draw_point(self, x, y, color):
        self.set_windows(x, y, x, y)
        self.dc(1)
        self.cs(0)
        self.bus.write(bytearray([color >> 8, color & 0x00FF]))
        self.cs(1)

    def draw_square(self, x, y, s, color):
        x_start = x
        y_start = y
        x_end = x + s
        y_end = y + s

        self.set_windows(x_start, y_start, x_end, y_end)
        self.dc(1)
        self.cs(0)
        for i in range((s + 1) * (s + 1)):
            self.bus.write(bytearray([color >> 8, color & 0x00FF]))
        self.cs(1)

    def lcd_fill(self, color):
        buffer = bytearray([color >> 8, color & 0x00FF] * self.width)
        self.set_windows(0, 0, self.width, self.height)
        self.dc(1)
        self.cs(0)
        for i in range(self.height):
            self.bus.write(buffer)
        self.cs(1)

    def fix_xy(self, x, y):
        if self.reverse:
            if self.horizontal:
                x_touch = y
                y_touch = self.height - x
            else:
                x_touch = self.width - x
                y_touch = self.height - y
        else:
            if self.horizontal:
                x_touch = self.width - y
                y_touch = x
            else:
                x_touch = x
                y_touch = y
        return x_touch, y_touch

    def get_touch_xy(self):
        return [(self.fix_xy(x, y)) for x, y in self.touch.get_touch_xy()]

    def clear_touch(self):
        self.touch.clear()


def hex_to_rgb565(hex_color):
    if hex_color.startswith("#"):
        hex_color = hex_color[1:]

    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def rgb888_to_rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def draw_button(lcd, button, bg_color, label="", text_color=0xFFFF):
    x, y, w, h = button

    # RGB565 requires 2 bytes per pixel
    buf = bytearray(w * h * 2)
    fb = framebuf.FrameBuffer(buf, w, h, framebuf.RGB565)
    fb.fill(bg_color)

    if label:
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
