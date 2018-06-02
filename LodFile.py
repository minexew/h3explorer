import struct
import zlib

class LodFile:
    def __init__(self, f):
        self.f = f

        header = struct.unpack('<4sII', f.read(12))
        magic = header[0]
        num_files = header[1]
        #print('LOD header', header)

        if magic != b'LOD\x00':
            raise Exception('Not a LOD file')

        for i in range(20):
            val, = struct.unpack('<I', f.read(4))

        file_table_size = 10000

        file_table = []

        for i in range(file_table_size):
            name, start, uncompressed_size, unk2, compressed_size = struct.unpack('<16sIIII', f.read(32))

            name_end = name.find(b'\x00')
            if name_end == 0:
                continue
            elif name_end == -1:
                name_end = 16

            name = name[:name_end].decode()
            file_table += [dict(name=name, start=start, uncompressed_size=uncompressed_size, unk2=unk2, compressed_size=compressed_size)]

        self.file_table = file_table

    def get_file_bytes(self, filename):
        f = self.f

        for entry in self.file_table:
            if entry['name'] == filename:
                f.seek(entry['start'])
                data = f.read(entry['compressed_size'])

                # FIXME: this assumes compression, which is not always present
                return zlib.decompress(data)

        raise Exception('No such file')

    def get_file_table(self):
        return self.file_table
