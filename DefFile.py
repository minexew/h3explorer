import numpy as np
import struct

class DefFile:
    def __init__(self, f):
        self.f = f

        unk1, image_width, image_height, num_images = struct.unpack('<IIII', f.read(16))
        #print((unk1, image_width, image_height, num_images))

        self.w = image_width
        self.h = image_height
        self.unk1 = unk1

        # Main palette
        palette_bytes = f.read(256 * 3)
        palette = np.frombuffer(palette_bytes, dtype=np.uint8).reshape((256, 3))
        self.palette = palette

        #print('end of palette at', f.tell())

        self.images = []

        for i in range(num_images):
            entry = struct.unpack('<IIII', f.read(16))
            num_frames = entry[1]
            #print(i, '%d, %d, %08X, %08X' % entry)

            image = dict(frames=[], unk_index=entry[0], unk2=entry[2], unk3=entry[3])

            for frame in range(num_frames):
                filename, unk1 = struct.unpack('<12sB', f.read(13))
                #print('\t ', subentry)
                image['frames'] += [dict(filename=filename.decode(), unk1=unk1)]

            for frame in range(num_frames):
                start = struct.unpack('<I', f.read(4))[0]
                #print('\t@', start)
                image['frames'][frame]['start'] = start

            self.images += [image]

    def describe(self):
        return dict(w=self.w, h=self.h, images=self.images, unk1=self.unk1)

    def describe_frame(self, image_index, frame_index):
        f = self.f

        start = self.images[image_index]['frames'][frame_index]['start']
        f.seek(start)

        size, format, full_width, full_height, width, height, xoff, yoff = struct.unpack('<IIIIIIII', f.read(32))
        return dict(size=size, format=format, full_width=full_width, full_height=full_height, w=width, h=height, xoff=xoff, yoff=yoff)

    def get_frame_rgb(self, image_index, frame_index):
        f = self.f
        palette = self.palette

        start = self.images[image_index]['frames'][frame_index]['start']
        f.seek(start)

        size, format, full_width, full_height, width, height, xoff, yoff = struct.unpack('<IIIIIIII', f.read(32))
        #print('frame header', (size, format, full_width, full_height, width, height, xoff, yoff))

        # https://forum.vcmi.eu/t/creating-def-files/799/5
        # https://github.com/josch/lodextract/blob/master/makedef.py
        # http://download.vcmi.eu/tools/
        # https://wiki.vcmi.eu/User:Viader#Archive_formats

        assert full_width == self.w
        assert full_height == self.h

        if format == 1:
            offset_table = f.read(height * 4)

            y = 0
            x = 0
            pixels = np.zeros((height, width, 3), dtype=np.uint8)

            while y < height:
                color = ord(f.read(1))

                if color == 0xff:
                    count = ord(f.read(1)) + 1
                    for j in range(count):
                        color = ord(f.read(1))
                        pixels[y, x, :] = palette[color]
                        x += 1
                else:
                    count = ord(f.read(1)) + 1
                    for j in range(count):
                        pixels[y, x, :] = palette[color]
                        x += 1

                if x == width:
                    x = 0
                    y += 1
        elif format == 3:
            assert width % 32 == 0

            segments_per_line = width // 32

            offset_table = f.read(segments_per_line * height * 2)

            y = 0
            x = 0
            pixels = np.zeros((height, width, 3), dtype=np.uint8)

            while y < height:
                b = ord(f.read(1))
                color = b >> 5
                count = (b & 0x1F) + 1

                if color == 7:
                    for j in range(count):
                        color = ord(f.read(1))
                        pixels[y, x, :] = palette[color]
                        x += 1
                else:
                    for j in range(count):
                        pixels[y, x, :] = palette[color]
                        x += 1

                if x == width:
                    x = 0
                    y += 1
        else:
            raise Exception('Unsupported format %d' % format)

        return dict(size=size, format=format, full_width=full_width, full_height=full_height, w=width, h=height, xoff=xoff, yoff=yoff, pixels=pixels)

    def get_palette(self):
        return self.palette
