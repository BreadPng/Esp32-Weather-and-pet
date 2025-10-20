# ssd1306.py
# Source: MicroPython-style SSD1306 driver (MIT)
# Minimal I2C variant for 128x64 displays

import framebuf

class SSD1306:
    def __init__(self, width, height, external_vcc):
        self.width = width
        self.height = height
        self.external_vcc = external_vcc
        self.pages = self.height // 8
        self.buffer = bytearray(self.pages * self.width)
        self.framebuf = framebuf.FrameBuffer(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self.poweron()
        self.init_display()

    def init_display(self):
        for cmd in (
            0xAE,         # display off
            0x20, 0x00,   # horizontal addressing
            0xB0,         # page addr base
            0xC8,         # COM scan dir remap
            0x00,         # low col start
            0x10,         # hi col start
            0x40,         # start line
            0x81, 0xCF,   # contrast
            0xA1,         # segment remap
            0xA6,         # normal display
            0xA8, self.height - 1,    # multiplex
            0xA4,         # display follows RAM
            0xD3, 0x00,   # display offset
            0xD5, 0x80,   # clock div
            0xD9, 0xF1,   # precharge
            0xDA, 0x12,   # COM pins
            0xDB, 0x40,   # vcomh
            0x8D, 0x14 if not self.external_vcc else 0x10,  # charge pump
            0xAF):        # display on
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def poweron(self):
        pass

    def poweroff(self):
        self.write_cmd(0xAE)

    def contrast(self, contrast):
        self.write_cmd(0x81)
        self.write_cmd(contrast)

    def invert(self, invert):
        self.write_cmd(0xA7 if invert else 0xA6)

    def show(self):
        for page in range(0, self.pages):
            self.write_cmd(0xB0 | page)
            self.write_cmd(0x02)        # low col
            self.write_cmd(0x10)        # hi col
            start = page * self.width
            end = start + self.width
            self.write_data(self.buffer[start:end])

    def fill(self, c):
        self.framebuf.fill(c)

    def pixel(self, x, y, c):
        self.framebuf.pixel(x, y, c)

    def scroll(self, dx, dy):
        self.framebuf.scroll(dx, dy)

    def text(self, s, x, y, c=1):
        self.framebuf.text(s, x, y, c)

    def rect(self, x, y, w, h, c=1):
        self.framebuf.rect(x, y, w, h, c)

    def fill_rect(self, x, y, w, h, c=1):
        self.framebuf.fill_rect(x, y, w, h, c)

    # I2C/SPI specific in subclasses
    def write_cmd(self, cmd):
        raise NotImplementedError

    def write_data(self, buf):
        raise NotImplementedError


class SSD1306_I2C(SSD1306):
    def __init__(self, width, height, i2c, addr=0x3c, external_vcc=False):
        self.i2c = i2c
        self.addr = addr
        super().__init__(width, height, external_vcc)

    def write_cmd(self, cmd):
        self.i2c.writeto(self.addr, b'\x00' + bytearray([cmd]))

    def write_data(self, buf):
        self.i2c.writeto(self.addr, b'\x40' + buf)
